import math
import re
import threading
import concurrent.futures
from urllib.parse import quote
import requests

_thread_local = threading.local()

def _get_session():
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        })
        _thread_local.session = session
    return _thread_local.session

def _empty_result(status, url, title="-"):
    return {
        "status": status,
        "url": url,
        "title": title,
        "author": "-",
        "likes": "-",
        "views": "-",
        "date": "-",
        "subs": "-",
    }

def extract_tweet_info(url):
    """URL se (username, tweet_id) nikalta hai."""
    if not url or not isinstance(url, str):
        return None, None
    match = re.search(
        r"(?:https?://)?(?:www\.|mobile\.)?(?:x|twitter|fxtwitter|fixupx|vxtwitter)\.com/(?:(i/web)|([^/?#]+))/status(?:es)?/(\d+)",
        url,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    username = match.group(2)  # /i/web/status/... ke liye None hoga
    tweet_id = match.group(3)
    return username, tweet_id

def extract_tweet_id(url):
    _, tweet_id = extract_tweet_info(url)
    return tweet_id

def _get_syndication_token(tweet_id):
    """X ke syndication endpoint ke liye official embed token generate karta hai."""
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    num = (float(tweet_id) / 1e15) * math.pi
    int_part = int(num)
    frac_part = num - int_part

    int_digits = []
    if int_part == 0:
        int_digits.append("0")
    while int_part > 0:
        int_digits.append(chars[int_part % 36])
        int_part //= 36
    res = "".join(reversed(int_digits))

    frac_digits = []
    for _ in range(12):
        frac_part *= 36
        d = int(frac_part)
        frac_digits.append(chars[d])
        frac_part -= d
        if frac_part == 0:
            break

    return (res + "".join(frac_digits)).replace("0", "")

def _check_oembed_live(session, canonical_url):
    """X ke official oEmbed endpoint se live status check karta hai."""
    oembed_url = f"https://publish.x.com/oembed?url={quote(canonical_url, safe='')}&omit_script=true"
    try:
        resp = session.get(oembed_url, timeout=10)
        if resp.status_code in (401, 403, 404, 410):
            return "dead", {}
        if resp.status_code == 429:
            return "rate_limited", {}
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get("html"):
                    return "active", data
            except ValueError:
                pass
            return "dead", {}
        return "unknown", {}
    except requests.exceptions.RequestException:
        return "unknown", {}

def _check_syndication_live(session, tweet_id):
    """X ke official syndication endpoint se live status + TweetTombstone check karta hai."""
    token = _get_syndication_token(tweet_id)
    synd_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en&token={token}"
    headers = {
        "Accept": "application/json",
        "Referer": "https://platform.twitter.com/",
    }
    try:
        resp = session.get(synd_url, headers=headers, timeout=10)
        if resp.status_code in (404, 410):
            return "dead", {}, False
        if resp.status_code == 429:
            return "rate_limited", {}, False
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                return "unknown", {}, False

            if not data:
                return "dead", {}, False
            if data.get("__typename") == "TweetTombstone":
                # Account suspended / tweet deleted / unavailable
                return "dead", data, True
            if data.get("__typename") == "Tweet" or data.get("id_str"):
                return "active", data, False
        return "unknown", {}, False
    except requests.exceptions.RequestException:
        return "unknown", {}, False

def _fetch_fxtwitter_details(session, tweet_id):
    """Active tweet ke liye views, likes, followers wagairah fetch karta hai."""
    api_url = f"https://api.fxtwitter.com/2/status/{tweet_id}"
    try:
        resp = session.get(api_url, headers={"User-Agent": "MyMultiScraper/1.0"}, timeout=10)
        data = resp.json()
        if data.get("code") == 200:
            return data.get("status") or data.get("tweet") or {}
    except Exception:
        pass
    return {}

def check_x_status(url):
    url = url.strip()
    url_username, tweet_id = extract_tweet_info(url)
    if not tweet_id:
        return _empty_result("Invalid URL", url)

    session = _get_session()
    canonical_url = (
        f"https://x.com/{url_username}/status/{tweet_id}"
        if url_username
        else f"https://x.com/i/web/status/{tweet_id}"
    )

    # 1. Pehle X ke apne live servers par check karein (FxTwitter ke cache par bharosa na karein)
    oembed_state, oembed_data = _check_oembed_live(session, canonical_url)
    if oembed_state == "dead":
        return _empty_result("Dead / Private", url)

    synd_state, synd_data, is_tombstone = _check_syndication_live(session, tweet_id)

    # Agar X Tombstone de raha hai ya syndication dead bol raha hai (aur oembed active nahi hai)
    if is_tombstone or (synd_state == "dead" and oembed_state != "active"):
        return _empty_result("Dead / Private", url)

    # Agar dono live X endpoints rate-limit ya fail ho gaye
    if oembed_state in ("rate_limited", "unknown") and synd_state in ("rate_limited", "unknown"):
        if oembed_state == "rate_limited" or synd_state == "rate_limited":
            return _empty_result("Rate Limited", url, "X rate limited live check")
        return _empty_result("Error", url, "Live verification failed")

    # 2. Tweet sach me Active hai -> ab FxTwitter + Syndication se full details nikalein
    fx_tweet = _fetch_fxtwitter_details(session, tweet_id)
    fx_author = fx_tweet.get("author") or {}
    synd_user = synd_data.get("user") or {}

    raw_text = fx_tweet.get("text") or synd_data.get("text") or ""
    clean_text = " ".join(raw_text.split())
    short_text = (clean_text[:50] + "...") if len(clean_text) > 50 else clean_text
    if not short_text:
        short_text = "No text content"

    author_name = (
        fx_author.get("screen_name")
        or synd_user.get("screen_name")
        or oembed_data.get("author_name")
        or "Unknown"
    )

    likes = fx_tweet.get("likes") if fx_tweet.get("likes") is not None else synd_data.get("favorite_count")
    views = fx_tweet.get("views")
    followers = fx_author.get("followers") if fx_author.get("followers") is not None else synd_user.get("followers_count")
    created_at = fx_tweet.get("created_at") or synd_data.get("created_at") or "-"

    return {
        "status": "Active",
        "url": url,
        "title": short_text,
        "author": author_name,
        "likes": f"{likes:,}" if isinstance(likes, (int, float)) else "0",
        "views": f"{views:,}" if isinstance(views, (int, float)) else "N/A",
        "date": created_at,
        "subs": f"{followers:,}" if isinstance(followers, (int, float)) else "N/A",
    }

def scrape_data(urls_str):
    if not urls_str or not urls_str.strip():
        return []
    url_list = [u.strip() for u in urls_str.splitlines() if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        return list(executor.map(check_x_status, url_list))

def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]


# --- Test ---
if __name__ == "__main__":
    test_urls = """
    https://x.com/Goodwatchin/status/2078540370623754363
    https://x.com/X/status/1683920951807971329
    """
    for row in scrape_data(test_urls):
        print(row)