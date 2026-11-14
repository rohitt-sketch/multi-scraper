import yt_dlp
import concurrent.futures

def check_ig_status(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'simulate': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return {
                    "status": "Active",
                    "url": url,
                    "title": info.get('title', 'Instagram Reel/Post') or 'Instagram Reel/Post',
                    "author": info.get('uploader', 'Unknown') or 'Unknown',
                    "views": f"{int(info.get('view_count', 0)):,}" if info.get('view_count') else "-",
                    "likes": f"{int(info.get('like_count', 0)):,}" if info.get('like_count') else "-",
                    "duration": str(info.get('duration', '-')) if info.get('duration') else "-",
                    "date": info.get('upload_date', '-') or '-',
                    "subs": "N/A"
                }
    except Exception as e:
        error_msg = str(e).lower()
        if any(x in error_msg for x in ["private", "unavailable", "removed", "not found", "login", "error"]):
            return {"status": "Dead / Private", "url": url, "title": "-", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}
        return {"status": f"Error", "url": url, "title": str(e), "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}
    return {"status": "Dead / Private", "url": url, "title": "-", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}

def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        return list(executor.map(check_ig_status, url_list))

def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]
