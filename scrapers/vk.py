import time
import yt_dlp
import concurrent.futures

# Dead sirf tab, jab saaf saboot ho
DEAD_MARKERS = (
    "has been removed", "removed from public access", "no longer available",
    "deleted", "video not found", "http error 404", "does not exist", "private",
)
# Ye sab block / network ke sanket hain (Dead nahi)
BLOCK_MARKERS = (
    "403", "429", "forbidden", "too many requests", "captcha", "login", "sign in",
    "cookies", "timed out", "timeout", "connection", "reset", "aborted",
    "unable to download", "bot", "empty media",
)


def check_vk_status(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'simulate': True,
        'socket_timeout': 15,
        'retries': 1,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        time.sleep(1)  # safety delay (VK ke IP block se bachne ke liye)
        if info:
            return {"status": "Active", "url": url}
        return {"status": "Error: Empty Response", "url": url}

    except yt_dlp.utils.DownloadError as e:
        msg = str(e).lower()
        if any(m in msg for m in DEAD_MARKERS):
            return {"status": "Dead / Private", "url": url}
        if any(m in msg for m in BLOCK_MARKERS):
            return {"status": "Error: Blocked (IP/Login)", "url": url}
        return {"status": "Error: Check Failed", "url": url}

    except Exception as e:
        return {"status": f"Error: {str(e)[:60]}", "url": url}


def check_status(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    # Ek baar me sirf 1 request, taaki VK block na kare
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return list(executor.map(check_vk_status, url_list))


def scrape_data(urls_str):
    return check_status(urls_str)