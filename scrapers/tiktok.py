import requests
import time
import threading
import concurrent.futures
from datetime import datetime, timezone

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}

# tikwm free API: 1 request/second. Saari requests ek line me, 1.2 sec ke gap se.
_lock = threading.Lock()
_last = [0.0]


def format_number(num):
    try: return f"{int(num):,}"
    except Exception: return "0"


def format_duration(sec):
    try:
        sec = int(sec)
        h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception: return "-"


def _tikwm_get(url, timeout=12):
    with _lock:
        wait = 1.2 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
    return requests.get(url, headers=UA, timeout=timeout).json()


def _row(status, url, title="-", author="-", views="0", likes="0", duration="-", date="-", subs="-"):
    return {"status": status, "url": url, "title": title, "author": author, "views": views,
            "likes": likes, "duration": duration, "date": date, "subs": subs}


def fetch_tiktok_data(url, full=True):
    clean_url = url.split('?')[0]
    transient = None  # network / rate-limit / block ka sanket (Dead nahi)

    for _ in range(2):
        try:
            res = _tikwm_get(f'https://www.tikwm.com/api/?url={clean_url}')
        except Exception as e:
            transient = f"tikwm: {str(e)[:40]}"
            continue

        d = res.get('data') if isinstance(res, dict) else None
        if isinstance(d, dict) and d.get('id'):
            author = d.get('author') or {}
            username = author.get('unique_id', '')
            date_str = "-"
            if d.get('create_time'):
                date_str = datetime.fromtimestamp(d['create_time'], tz=timezone.utc).strftime('%Y-%m-%d')
            subs = "0"
            if full and username:  # follower count sirf Full Scrape me
                try:
                    u_res = _tikwm_get(f'https://www.tikwm.com/api/user/info?unique_id={username}', timeout=8)
                    stats = ((u_res.get('data') or {}).get('stats') or {})
                    subs = format_number(stats.get('followerCount', 0))
                except Exception:
                    pass
            return _row(
                "Active", url, title=d.get('title', ''), author=author.get('nickname', username),
                views=format_number(d.get('play_count', 0)), likes=format_number(d.get('digg_count', 0)),
                duration=format_duration(d.get('duration', 0)), date=date_str, subs=subs,
            )

        msg = str(res.get('msg', '')).lower() if isinstance(res, dict) else ''
        if 'limit' in msg:
            transient = "rate limit"
            time.sleep(1.5)
            continue
        transient = None
        break

    # Fallback: TikTok oEmbed
    try:
        r = requests.get(f'https://www.tiktok.com/oembed?url={clean_url}', headers=UA, timeout=10)
        if r.status_code == 200:
            o = r.json()
            if o.get('html') or o.get('author_name'):
                return _row("Active", url, title=o.get('title', ''), author=o.get('author_name', '-'))
        elif r.status_code in (403, 429) or r.status_code >= 500:
            transient = transient or f"oembed HTTP {r.status_code}"
    except Exception as e:
        transient = transient or f"oembed: {str(e)[:40]}"

    if transient:
        return _row("Error: Blocked/Retry", url, title=f"Check failed ({transient})")
    return _row("Dead/Error", url, title="Video Unavailable", views="0", likes="0")


def scrape_data(urls_str, full=True):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        return list(executor.map(lambda u: fetch_tiktok_data(u, full), url_list))


def check_status(urls_str):
    results = scrape_data(urls_str, full=False)
    return [{"status": r["status"], "url": r["url"]} for r in results]