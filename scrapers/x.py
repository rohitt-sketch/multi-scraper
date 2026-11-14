"""X/Twitter status checker — copy-paste ready.
Sirf `requests` chahiye:  pip install requests

Verified on: https://x.com/Goodwatchin/status/2121610324717588488 -> Active
"""
import math
import re
import time
import threading
import concurrent.futures
from decimal import Decimal, getcontext
from urllib.parse import quote
import html as _html
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
_thread_local = threading.local()

def _get_session():
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _thread_local.session = s
    return _thread_local.session

def _empty_result(status, url, title="-"):
    return {"status": status, "url": url, "title": title,
            "author": "-", "likes": "-", "views": "-",
            "date": "-", "subs": "-"}

def extract_tweet_info(url):
    """URL se (username, tweet_id) nikalta hai."""
    if not url or not isinstance(url, str):
        return None, None
    m = re.search(
        r"(?:https?://)?(?:www\.|mobile\.)?(?:x|twitter|fxtwitter|fixupx|vxtwitter|pxtwitter)\.com/(?:(i/web)|([^/?#]+))/status(?:es)?/(\d+)",
        url, re.IGNORECASE)
    if not m:
        return None, None
    return m.group(2), m.group(3)

def extract_tweet_id(url):
    _, tid = extract_tweet_info(url)
    return tid

def _get_token(tweet_id):
    getcontext().prec = 40
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    num = (Decimal(str(tweet_id)) / (Decimal(10) ** 15)) * Decimal(str(math.pi))
    ip = int(num); fp = num - ip
    d = ["0"] if ip == 0 else []
    while ip > 0:
        d.append(chars[ip % 36]); ip //= 36
    res = "".join(reversed(d)) if d else "0"
    f = []
    for _ in range(12):
        fp *= 36; x = int(fp); f.append(chars[x]); fp -= x
        if fp == 0:
            break
    return (res + "".join(f)).replace("0", "")

def _get_retry(session, url, headers=None, timeout=12, tries=3, backoff=1.0):
    last = None
    for i in range(tries):
        try:
            r = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code == 429 and i < tries - 1:
                time.sleep(backoff * (i + 1))
                last = r
                continue
            return r
        except requests.exceptions.RequestException as e:
            last = e
            if i < tries - 1:
                time.sleep(backoff * (i + 1))
    return last

def _check_oembed(session, tweet_id):
    url = f"https://x.com/i/status/{tweet_id}"
    ou = f"https://publish.x.com/oembed?url={quote(url, safe='')}&omit_script=true"
    r = _get_retry(session, ou, timeout=12, tries=3)
    if isinstance(r, Exception):
        return "unknown", {}, f"NET {str(r)[:40]}"
    if r.status_code in (401, 403, 404, 410):
        return "dead", {}, f"HTTP {r.status_code}"
    if r.status_code == 429:
        return "rate_limited", {}, "HTTP 429"
    if r.status_code == 200:
        try:
            d = r.json()
            if d.get("html"):
                return "active", d, "HTTP 200"
        except ValueError:
            pass
        return "dead", {}, "Invalid payload"
    return "unknown", {}, f"HTTP {r.status_code}"

def _check_syndication(session, tweet_id):
    tok = _get_token(tweet_id)
    u = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en&token={tok}"
    h = {"Accept": "application/json", "Referer": "https://platform.twitter.com/"}
    r = _get_retry(session, u, headers=h, timeout=12, tries=3)
    if isinstance(r, Exception):
        return "unknown", {}, f"NET {str(r)[:40]}"
    if r.status_code in (401, 403, 404, 410):
        return "dead", {}, f"HTTP {r.status_code}"
    if r.status_code == 429:
        return "rate_limited", {}, "HTTP 429"
    if r.status_code == 200:
        try:
            d = r.json()
        except ValueError:
            return "unknown", {}, "Invalid JSON"
        if not d:
            return "dead", {}, "Empty JSON"
        if d.get("__typename") == "TweetWithVisibilityResults":
            d = d.get("tweet") or {}
        tn = d.get("__typename")
        if "tombstone" in d or tn in ("TweetTombstone", "TweetUnavailable"):
            return "dead", d, f"Gone ({tn or 'tombstone'})"
        if tn == "Tweet" or (d.get("id_str") and d.get("user")):
            return "active", d, "Tweet Active"
        return "dead", d, f"typename:{tn}"
    return "unknown", {}, f"HTTP {r.status_code}"

def _check_xpage(session, tweet_id):
    u = f"https://x.com/i/status/{tweet_id}"
    r = _get_retry(session, u, timeout=15, tries=2)
    if isinstance(r, Exception):
        return "unknown", {}, f"NET {str(r)[:40]}"
    if r.status_code in (401, 403, 404, 410):
        return "dead", {"final_url": getattr(r, "url", "")}, f"HTTP {r.status_code}"
    if r.status_code == 429:
        return "rate_limited", {}, "HTTP 429"
    if r.status_code == 200:
        final = getattr(r, "url", "") or ""
        if "/login" in final and "/status/" not in final:
            return "unknown", {"final_url": final}, "Login wall"
        if "/status/" in final:
            return "active", {"final_url": final}, "HTTP 200 + status URL"
        if len(r.text or "") > 20000:
            return "active", {"final_url": final}, "HTTP 200 page"
        return "unknown", {"final_url": final}, "HTTP 200 unclear"
    return "unknown", {}, f"HTTP {r.status_code}"

def _check_fx(session, tweet_id):
    u = f"https://api.fxtwitter.com/2/status/{tweet_id}"
    r = _get_retry(session, u, headers={"User-Agent": "MyMultiScraper/1.0"}, timeout=12, tries=3)
    if isinstance(r, Exception):
        return "unknown", {}, f"NET {str(r)[:40]}", {}
    try:
        d = r.json()
    except ValueError:
        if r.status_code in (401, 403, 404, 410):
            return "dead", {}, f"HTTP {r.status_code} non-JSON", {}
        return "unknown", {}, f"HTTP {r.status_code} non-JSON", {}
    if not isinstance(d, dict):
        return "unknown", {}, "bad payload", {}
    code = d.get("code", r.status_code)
    if code in (401, 403, 404, 410):
        return "dead", {}, f"Code {code}", {}
    tweet = d.get("status") or d.get("tweet") or {}
    if (code == 200 or r.status_code == 200) and tweet:
        return "active", tweet, "Code 200", d.get("author") or {}
    return "unknown", {}, f"Code {code}", {}

def _check_vx(session, tweet_id):
    u = f"https://api.vxtwitter.com/2/status/{tweet_id}"
    r = _get_retry(session, u, headers={"User-Agent": "MyMultiScraper/1.0"}, timeout=12, tries=3)
    if isinstance(r, Exception):
        return "unknown", {}, f"NET {str(r)[:40]}"
    txt = r.text or ""
    if "Failed to scan your link" in txt:
        return "dead", {}, "VX not-found page"
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "application/json" not in ctype and r.status_code == 200 and "<html" in txt.lower() and len(txt) < 2000:
        return "dead", {}, "VX HTML page"
    try:
        d = r.json()
    except ValueError:
        if r.status_code in (401, 403, 404, 410):
            return "dead", {}, f"HTTP {r.status_code}"
        return "unknown", {}, f"HTTP {r.status_code} non-JSON"
    if not isinstance(d, dict):
        return "unknown", {}, "bad payload"
    if d.get("tweetID") or (d.get("text") and d.get("user_screen_name")):
        return "active", d, "VX OK"
    if d.get("code") in (401, 403, 404, 410):
        return "dead", {}, f"Code {d.get('code')}"
    return "unknown", {}, "VX unclear"

def _decide(o, s, x, f, v):
    off_a = sum(1 for t in (o, s, x) if t == "active")
    off_d = sum(1 for t in (o, s, x) if t == "dead")
    third_a = sum(1 for t in (f, v) if t == "active")
    third_d = sum(1 for t in (f, v) if t == "dead")
    if off_a >= 2:
        return "Active", f"official {off_a} active"
    if off_d >= 2 and off_a == 0:
        return "Dead / Private", f"official {off_d} dead"
    if off_a == 1 and off_d == 0:
        return "Active", "1 official active, 0 dead"
    if off_a == 0 and off_d == 1:
        if third_a >= 1:
            return "Active", "1 official dead vs third-party active"
        if third_d >= 1:
            return "Dead / Private", "1 official dead + third dead"
        return "Dead / Private", "1 official dead, rest unknown"
    if off_a == 1 and off_d == 1:
        if x == "active":
            return "Active", "tie-break xpage active"
        if x == "dead" and third_d >= 1:
            return "Dead / Private", "tie-break xpage+third dead"
        if third_a >= 1:
            return "Active", "tie-break third active"
        return "Error", "official tie, unclear"
    if "rate_limited" in (o, s, x) and off_a == 0 and off_d == 0:
        return "Rate Limited", "officials rate limited"
    a_score = 3 * off_a + third_a
    d_score = 3 * off_d + third_d
    if a_score == 0 and d_score == 0:
        return "Error", "all unknown (network?)"
    if a_score > d_score:
        return "Active", f"vote {a_score}>{d_score}"
    if d_score > a_score:
        return "Dead / Private", f"vote {d_score}>{a_score}"
    return "Error", f"tie vote {a_score}={d_score}"

def _meta(o_d, s_d, fx_t, fx_top, vx_d):
    fx_a = {}
    if isinstance(fx_t, dict):
        fx_a = (fx_t.get("author") or {}) or fx_top or {}
    s_u = (s_d.get("user") or {}) if isinstance(s_d, dict) else {}
    o_url = (o_d.get("url") or "") if isinstance(o_d, dict) else ""
    m = re.search(r"(?:x|twitter)\.com/([^/?#]+)/status", o_url)
    o_user = m.group(1) if m else ""
    o_author = ((o_d.get("author_name") or "").strip()) if isinstance(o_d, dict) else ""
    vx_user = (vx_d.get("user_screen_name") or "") if isinstance(vx_d, dict) else ""
    author = (fx_a.get("screen_name") or s_u.get("screen_name")
              or vx_user or o_user or o_author or "Unknown")
    text = ""
    if isinstance(fx_t, dict):
        text = fx_t.get("text") or ""
    if not text and isinstance(vx_d, dict):
        text = vx_d.get("text") or ""
    if not text and isinstance(s_d, dict):
        text = s_d.get("text") or ""
    if not text and isinstance(o_d, dict):
        raw = re.sub(r"<[^>]+>", " ", o_d.get("html") or "")
        text = _html.unescape(" ".join(raw.split()))[:200]
    text = " ".join((text or "").split())
    short = (text[:50] + "...") if len(text) > 50 else text
    if not short:
        short = "No text content"
    likes = None; views = None; fol = None; date = "-"
    if isinstance(fx_t, dict):
        likes = fx_t.get("likes"); views = fx_t.get("views"); date = fx_t.get("created_at") or date
        fol = fx_a.get("followers")
    if likes is None and isinstance(vx_d, dict):
        likes = vx_d.get("likes")
    if likes is None and isinstance(s_d, dict):
        likes = s_d.get("favorite_count")
    if fol is None:
        fol = s_u.get("followers_count")
    if date == "-" and isinstance(vx_d, dict):
        date = vx_d.get("date") or date
    if date == "-" and isinstance(s_d, dict):
        date = s_d.get("created_at") or date
    return short, author, likes, views, date, fol

def check_x_status(url, debug=False):
    url = (url or "").strip()
    _, tid = extract_tweet_info(url)
    if not tid:
        return _empty_result("Invalid URL", url)
    session = _get_session()
    o_s, o_d, o_i = _check_oembed(session, tid)
    s_s, s_d, s_i = _check_syndication(session, tid)
    x_s, x_d, x_i = _check_xpage(session, tid)
    f_s, f_t, f_i, f_a = _check_fx(session, tid)
    v_s, v_d, v_i = _check_vx(session, tid)
    if debug:
        print(f"[DEBUG] {url}\n  oEmbed={o_s} ({o_i}) | synd={s_s} ({s_i}) | xpage={x_s} ({x_i}) | fx={f_s} ({f_i}) | vx={v_s} ({v_i})")
    verdict, reason = _decide(o_s, s_s, x_s, f_s, v_s)
    if debug:
        print(f"  => {verdict} ({reason})")
    if verdict != "Active":
        title = reason if verdict in ("Rate Limited", "Error") else "-"
        return _empty_result(verdict, url, title)
    short, author, likes, views, date, fol = _meta(o_d, s_d, f_t, f_a, v_d)
    return {
        "status": "Active", "url": url, "title": short, "author": author,
        "likes": f"{likes:,}" if isinstance(likes, (int, float)) else "0",
        "views": f"{views:,}" if isinstance(views, (int, float)) else "N/A",
        "date": date,
        "subs": f"{fol:,}" if isinstance(fol, (int, float)) else "N/A",
    }

def scrape_data(urls_str):
    if not urls_str or not urls_str.strip():
        return []
    urls = [u.strip() for u in urls_str.splitlines() if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        return list(ex.map(check_x_status, urls))

def check_status(urls_str):
    return [{"status": r["status"], "url": r["url"]} for r in scrape_data(urls_str)]

if __name__ == "__main__":
    print(check_x_status("https://x.com/Goodwatchin/status/2121610324717588488", debug=True))
