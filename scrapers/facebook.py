import yt_dlp
import concurrent.futures

def check_fb_status(url):
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
                    "title": info.get('title', 'Facebook Video') or 'Facebook Video',
                    "author": info.get('uploader', 'Unknown') or 'Unknown',
                    "views": f"{int(info.get('view_count', 0)):,}" if info.get('view_count') else "-",
                    "likes": f"{int(info.get('like_count', 0)):,}" if info.get('like_count') else "-",
                    "duration": str(info.get('duration', '-')) if info.get('duration') else "-",
                    "date": info.get('upload_date', '-') or '-',
                    "subs": "N/A"
                }
    except Exception as e:
        error_msg = str(e).lower()
        
        # Agar video waqai delete/private hai
        if any(x in error_msg for x in ["private", "unavailable", "removed", "not found", "unsupported url", "does not exist", "content isn't available"]):
            return {"status": "Dead / Private", "url": url, "title": "-", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}
        
        # Agar Facebook ne bot block lagaya hai (IP block)
        elif any(x in error_msg for x in ["login", "cookie", "bot", "403", "blocked", "cannot parse", "http error", "empty media response"]):
            return {"status": "Blocked by FB", "url": url, "title": "IP Blocked", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}
            
        return {"status": "Check Failed", "url": url, "title": str(e)[:50], "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}
        
    return {"status": "Dead / Private", "url": url, "title": "-", "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}

def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        return list(executor.map(check_fb_status, url_list))

def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]
