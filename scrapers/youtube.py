import requests
import re
import os
import concurrent.futures

API_KEY = os.getenv("YOUTUBE_API_KEY", "")

def get_youtube_type(url_or_id):
    url_or_id = url_or_id.strip()
    
    if re.match(r'^[0-9A-Za-z_-]{11}$', url_or_id): return 'video', url_or_id
    if re.match(r'^UC[0-9A-Za-z_-]{22}$', url_or_id): return 'channel_id', url_or_id
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|$)', url_or_id)
    if match: return 'video', match.group(1)
    match = re.search(r'youtube\.com\/channel\/([0-9A-Za-z_-]{24})', url_or_id)
    if match: return 'channel_id', match.group(1)
    match = re.search(r'youtube\.com\/(@[0-9A-Za-z_.-]+)', url_or_id)
    if match: return 'channel_handle', match.group(1)
    return 'unknown', url_or_id

def parse_duration(duration):
    match = re.match(r'PT(\d+H)?(\d+M)?(\d+S)?', duration)
    if not match: return "-"
    hours = int(match.group(1)[:-1]) if match.group(1) else 0
    minutes = int(match.group(2)[:-1]) if match.group(2) else 0
    seconds = int(match.group(3)[:-1]) if match.group(3) else 0
    if hours > 0: return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def format_date(date_str):
    return date_str[:10] if date_str else "-"

def fetch_videos_batch(video_ids):
    ids_str = ",".join(video_ids)
    api_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics,contentDetails&id={ids_str}&key={API_KEY}"
    try:
        res = requests.get(api_url, timeout=10).json()
        
        # API Error check
        if "error" in res:
            return [{"type": "Video", "status": "API Error", "id": vid, "title": "API Key Issue", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"} for vid in video_ids]

        items = {item['id']: item for item in res.get('items', [])}
        results = []
        for vid in video_ids:
            if vid in items:
                item = items[vid]
                stats = item['statistics']
                results.append({
                    "type": "Video", "status": "Active", "id": vid,
                    "title": item['snippet']['title'], "author": item['snippet']['channelTitle'],
                    "views": f"{int(stats.get('viewCount', 0)):,}",
                    "likes": f"{int(stats.get('likeCount', 0)):,}",
                    # Live stream crash fix
                    "duration": parse_duration(item['contentDetails'].get('duration', '')),
                    "date": format_date(item['snippet']['publishedAt']),
                    "subs": "N/A"
                })
            else:
                results.append({"type": "Video", "status": "Dead/Private", "id": vid, "title": "Not Found", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"})
        return results
    except Exception:
        return [{"type": "Video", "status": "API Error", "id": vid, "title": "Error", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"} for vid in video_ids]

def fetch_channels_batch(channel_ids):
    ids_str = ",".join(channel_ids)
    api_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id={ids_str}&key={API_KEY}"
    try:
        res = requests.get(api_url, timeout=10).json()
        
        if "error" in res:
            return [{"type": "Channel", "status": "API Error", "id": cid, "title": "API Key Issue", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"} for cid in channel_ids]

        items = {item['id']: item for item in res.get('items', [])}
        results = []
        for cid in channel_ids:
            if cid in items:
                item = items[cid]
                stats = item['statistics']
                results.append({
                    "type": "Channel", "status": "Active", "id": cid,
                    "title": item['snippet']['title'], "author": item['snippet']['title'],
                    "views": f"{int(stats.get('viewCount', 0)):,}",
                    "likes": "-", "duration": "-", "date": format_date(item['snippet']['publishedAt']),
                    "subs": f"{int(stats.get('subscriberCount', 0)):,}"
                })
            else:
                results.append({"type": "Channel", "status": "Dead/Banned", "id": cid, "title": "Not Found", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"})
        return results
    except Exception:
        return [{"type": "Channel", "status": "API Error", "id": cid, "title": "Error", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"} for cid in channel_ids]

def fetch_handle(handle):
    api_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&forHandle={handle}&key={API_KEY}"
    try:
        res = requests.get(api_url, timeout=10).json()
        
        if "error" in res:
            return {"lookup_key": handle, "type": "Channel", "status": "API Error", "id": handle, "title": "API Key Issue", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}

        if res.get('items'):
            item = res['items'][0]
            stats = item['statistics']
            return {
                "lookup_key": handle, # <--- FIX 1 APPLIED HERE
                "type": "Channel", "status": "Active", "id": item['id'],
                "title": item['snippet']['title'], "author": item['snippet']['title'],
                "views": f"{int(stats.get('viewCount', 0)):,}",
                "likes": "-", "duration": "-", "date": format_date(item['snippet']['publishedAt']),
                "subs": f"{int(stats.get('subscriberCount', 0)):,}"
            }
        else:
            return {"lookup_key": handle, "type": "Channel", "status": "Dead/Banned", "id": handle, "title": "Not Found", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}
    except Exception:
        return {"lookup_key": handle, "type": "Channel", "status": "API Error", "id": handle, "title": "Error", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}

def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    video_ids, channel_ids, channel_handles = [], [], []
    mapping = {} 
    
    for url in url_list:
        yt_type, yt_id = get_youtube_type(url)
        mapping[url] = yt_id
        if yt_type == 'video': video_ids.append(yt_id)
        elif yt_type == 'channel_id': channel_ids.append(yt_id)
        elif yt_type == 'channel_handle': channel_handles.append(yt_id)
        
    results_dict = {}
    
    if video_ids:
        for i in range(0, len(video_ids), 50):
            res = fetch_videos_batch(video_ids[i:i+50])
            for item in res: results_dict[item['id']] = item

    if channel_ids:
        for i in range(0, len(channel_ids), 50):
            res = fetch_channels_batch(channel_ids[i:i+50])
            for item in res: results_dict[item['id']] = item

    if channel_handles:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            res_list = list(executor.map(fetch_handle, channel_handles))
            for item in res_list:
                # <--- FIX 1 APPLIED HERE
                key = item.pop("lookup_key", item["id"]) 
                results_dict[key] = item

    final_results = []
    for url in url_list:
        yt_id = mapping[url]
        if yt_id in results_dict:
            final_results.append(results_dict[yt_id])
        else:
            final_results.append({"type": "Unknown", "status": "Invalid Link", "id": url, "title": "Invalid Input", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"})
    return final_results