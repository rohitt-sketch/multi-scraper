import os
import shutil
import tempfile
import functools
import time
import concurrent.futures
import yt_dlp

DEAD_MARKERS = ("http error 404", "not found", "has been removed", "no longer available", "page isn't available")
# Instagram ye message deleted/private aur login-needed dono ke liye deta hai
AMBIGUOUS_MARKERS = ("empty media response", "requested content is not available", "not granting access")
BLOCK_MARKERS = (
    "login", "log in", "rate-limit", "rate limit", "429", "403", "forbidden", "cookies",
    "timed out", "timeout", "connection", "unable to download", "bot",
)


@functools.lru_cache(maxsize=1)
def _cookiefile():
    """Optional: Render > Secret Files me 'instagram_cookies.txt' upload karo (Netscape format)."""
    for src in ("/etc/secrets/instagram_cookies.txt", "instagram_cookies.txt"):
        if os.path.isfile(src):
            dst = os.path.join(tempfile.gettempdir(), "ig_cookies.txt")
            try:
                shutil.copyfile(src, dst)
                return dst
            except Exception:
                return None
    return None


def _row(status, url, title="-", author="-", views="-", likes="-", duration="-", date="-"):
    return {"status": status, "url": url, "title": title, "author": author, "views": views,
            "likes": likes, "duration": duration, "date": date, "subs": "N/A"}


def check_ig_status(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'simulate': True,
        'extract_flat': True,
        'socket_timeout': 15,
        'retries': 1,
    }
    cookie = _cookiefile()
    if cookie:
        ydl_opts['cookiefile'] = cookie

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        time.sleep(1)
        if info:
            return _row(
                "Active", url,
                title=info.get('title') or 'Instagram Post',
                author=info.get('uploader') or 'Unknown',
                views=f"{int(info.get('view_count')):,}" if info.get('view_count') else "-",
                likes=f"{int(info.get('like_count')):,}" if info.get('like_count') else "-",
                duration=str(info.get('duration')) if info.get('duration') else "-",
                date=info.get('upload_date') or '-',
            )
        return _row("Error: Check Failed", url, title="Empty response")

    except yt_dlp.utils.DownloadError as e:
        msg = str(e).lower()
        if any(m in msg for m in DEAD_MARKERS):
            return _row("Dead / Private", url)
        if any(m in msg for m in AMBIGUOUS_MARKERS):
            # Login cookies ke saath bhi nahi dikha -> deleted/private maante hain
            return _row("Dead / Private" if cookie else "Error: Blocked (Login needed)", url)
        if any(m in msg for m in BLOCK_MARKERS):
            return _row("Error: Blocked (Login/IP)", url)
        return _row("Error: Check Failed", url, title=str(e)[:60])

    except Exception as e:
        return _row("Error: Check Failed", url, title=str(e)[:60])


def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    # Instagram IP block jaldi karta hai, isliye kam workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(check_ig_status, url_list))


def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]