import requests
import re
import html
import concurrent.futures

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
    'Accept-Language': 'ru-RU,ru;q=0.9'
}


def seconds_to_hms(sec):
    try:
        sec = int(sec)
        h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception: return "00:00:00"


def extract_field(text, patterns):
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match: return match.group(1).strip()
    return "N/A"


def _empty(status, url, title="-"):
    return {"status": status, "url": url, "title": title, "author": "-", "views": "0", "likes": "0", "duration": "-", "date": "-", "subs": "-"}


def fetch_okru_data(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code in (404, 410):
            return _empty("Dead", url, "HTTP " + str(res.status_code))
        if res.status_code != 200:
            # 403 / 429 / 5xx = block ya server issue, Dead nahi
            return _empty("Error: Blocked/Retry", url, f"HTTP {res.status_code}")
        if "captcha" in res.url.lower():
            return _empty("Error: Captcha/Blocked", url, "Captcha page")

        html_text = res.text
        title = extract_field(html_text, [r'<meta property="og:title" content="([^"]*)"', r'<title>([^<]*)<\/title>'])
        duration_sec = extract_field(html_text, [r'<meta property="og:video:duration" content="(\d+)"', r'"duration"\s*:\s*"?(\d+)"?'])
        date_raw = extract_field(html_text, [r'<meta property="ya:ovs:upload_date" content="([^"]*)"', r'"uploadDate"\s*:\s*"([^"]*)"'])
        views = extract_field(html_text, [r'"videoViewCount"\s*:\s*"?(\d+)"?', r'<meta property="ya:ovs:views_total" content="(\d+)"'])
        likes = extract_field(html_text, [r'"likeCount"\s*:\s*"?(\d+)"?', r'"reactions?Count"\s*:\s*"?(\d+)"?'])
        channel_name = extract_field(html_text, [r'<meta property="ya:ovs:login" content="([^"]*)"', r'"author"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"'])

        return {
            "status": "Active", "url": url, "title": html.unescape(title) if title != 'N/A' else "-",
            "author": html.unescape(channel_name) if channel_name != 'N/A' else "-",
            "views": f"{int(views):,}" if views.isdigit() else "0", "likes": f"{int(likes):,}" if likes.isdigit() else "0",
            "duration": seconds_to_hms(duration_sec) if duration_sec.isdigit() else "-",
            "date": date_raw.split('T')[0] if date_raw != 'N/A' else "-", "subs": "N/A"
        }
    except Exception as e:
        return {"status": "Error", "url": url, "title": str(e)[:80], "author": "-", "views": "-", "likes": "-", "duration": "-", "date": "-", "subs": "-"}


def scrape_data(urls_str):
    url_list = [u.strip() for u in urls_str.split('\n') if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        return list(executor.map(fetch_okru_data, url_list))


def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]