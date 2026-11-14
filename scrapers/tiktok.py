import requests
import concurrent.futures
from datetime import datetime

def format_number(num):
    try: return f"{int(num):,}"
    except: return "0"

def format_duration(sec):
    try:
        sec = int(sec)
        h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except: return "-"

def fetch_tiktok_data(url):
    clean_url = url.split('?')[0]
    try:
        api_url = f'https://www.tikwm.com/api/?url={clean_url}'
        res = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        if res and res.get('data') and res['data'].get('id'):
            d = res['data']
            username = d.get('author', {}).get('unique_id', '')
            date_str = datetime.fromtimestamp(d['create_time']).strftime('%Y-%m-%d') if d.get('create_time') else "-"
            subs = "0"
            if username:
                try:
                    u_res = requests.get(f'https://www.tikwm.com/api/user/info?unique_id={username}', timeout=5).json()
                    if u_res.get('data') and u_res['data'].get('stats'):
                        subs = format_number(u_res['data']['stats'].get('followerCount', 0))
                except: pass
            return {
                "status": "Active", "url": url, "title": d.get('title', ''), 
                "author": d.get('author', {}).get('nickname', username), 
                "views": format_number(d.get('play_count', 0)), "likes": format_number(d.get('digg_count', 0)), 
                "duration": format_duration(d.get('duration', 0)), "date": date_str, "subs": subs
            }
    except: pass 

    try:
        o_url = f'https://www.tiktok.com/oembed?url={clean_url}'
        o_res = requests.get(o_url, timeout=10).json()
        if o_res and o_res.get('title'):
            username = o_res.get('author_url', '').split('@')[-1] if o_res.get('author_url') else "-"
            return {
                "status": "Active", "url": url, "title": o_res.get('title'), 
                "author": o_res.get('author_name', username), 
                "views": "0", "likes": "0", "duration": "-", "date": "-", "subs": "0"
            }
    except: pass

    return {"status": "Dead/Error", "url": url, "title": "Video Unavailable", "author": "-", "views": "0", "likes": "0", "duration": "-", "date": "-", "subs": "-"}

def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        return list(executor.map(fetch_tiktok_data, url_list))

def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]
