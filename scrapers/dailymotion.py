import requests
import re
import concurrent.futures
from datetime import datetime, timezone


def get_dailymotion_id(url):
    match = re.search(r'(?:dailymotion\.com/(?:video|embed/video)/|dai\.ly/)([a-zA-Z0-9]+)', url, re.IGNORECASE)
    return match.group(1).split('?')[0] if match else None


def format_number(num):
    try: return f"{int(num):,}"
    except Exception: return "0"


def format_duration(sec):
    try:
        sec = int(sec)
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception: return "-"


def _row(status, url, title="-", **kw):
    base = {"status": status, "url": url, "title": title, "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}
    base.update(kw)
    return base


def fetch_dm_data(url):
    video_id = get_dailymotion_id(url)
    if not video_id:
        return _row("Invalid URL", url)

    api_url = f"https://api.dailymotion.com/video/{video_id}?fields=title,views_total,duration,created_time,likes_total,comments_total,owner,owner.screenname,owner.url,access_error"
    try:
        r = requests.get(api_url, timeout=10)
        try:
            res = r.json()
        except ValueError:
            res = {}

        if r.status_code in (404, 410):
            return _row("Dead/Error", url, "Video Not Found")

        if isinstance(res, dict) and res.get("error"):
            err = res["error"] if isinstance(res["error"], dict) else {}
            msg = str(err.get("message", "")).lower()
            code = str(err.get("code", r.status_code))
            if code in ("404", "403") or any(x in msg for x in ("not found", "unknown", "invalid", "does not exist", "no longer")):
                return _row("Dead/Error", url, "Video Not Found")
            return _row("API Error", url, (msg or f"HTTP {r.status_code}")[:60])

        if r.status_code != 200 or not res:
            return _row("API Error", url, f"HTTP {r.status_code}")

        if res.get("access_error"):
            return _row("Dead/Error", url, "Access Error", views="0", likes="0", subs="0")

        owner_id = res.get("owner")
        subs_count = "0"
        if owner_id:
            try:
                user_url = f"https://api.dailymotion.com/user/{owner_id}?fields=followers_total"
                user_res = requests.get(user_url, timeout=5).json()
                subs_count = format_number(user_res.get("followers_total", 0))
            except Exception:
                pass

        date_str = "-"
        if res.get("created_time"):
            date_str = datetime.fromtimestamp(res.get("created_time"), tz=timezone.utc).strftime('%Y-%m-%d')

        return {
            "status": "Active", "url": url, "title": res.get("title", "-"),
            "author": res.get("owner.screenname", "-"), "views": format_number(res.get("views_total", 0)),
            "likes": format_number(res.get("likes_total", 0)), "duration": format_duration(res.get("duration", 0)),
            "date": date_str, "subs": subs_count
        }
    except Exception as e:
        return _row("API Error", url, str(e)[:60])


def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        return list(executor.map(fetch_dm_data, url_list))


def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]