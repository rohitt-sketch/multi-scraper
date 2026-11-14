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
    username = match.group(2)
    tweet_id = match.group(3)
    return username, tweet_id

def extract_tweet_id(url):
    _, tweet_id = extract_tweet_info(url)
    return tweet_id

def _get_syndication_token(tweet_id):
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

def _check_oembed_live(session, target_url):
    """X ke official oEmbed endpoint se live status check karta hai."""
    oembed_url = f"https://publish.x.com/oembed?url={quote(target_url, safe='')}&omit_script=true"
    try:
        resp = session.get(oembed_url, timeout=10)
        if resp.status_code in (401, 403, 404, 410):
            return "dead", {}, f"HTTP {resp.status_code}"
        if resp.status_code == 429:
            return "rate_limited", {}, "HTTP 429"
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get("html"):
                    return "active", data, "HTTP 200"
            except ValueError:
                pass
            return "dead", {}, "Invalid oEmbed payload"
        return "unknown", {}, f"HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return "unknown", {}, str(e)[:40]

def _check_syndication_live(session, tweet_id):
    """X ke syndication endpoint se tweet/tombstone/unavailable check karta hai."""
    token = _get_syndication_token(tweet_id)
    synd_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en&token={token}"
    headers = {
        "Accept": "application/json",
        "Referer": "https://platform.twitter.com/",
    }
    try:
        resp = session.get(synd_url, headers=headers, timeout=10)
        if resp.status_code in (401, 403, 404, 410):
            return "dead", {}, f"HTTP {resp.status_code}"
        if resp.status_code == 429:
            return "rate_limited", {}, "HTTP 429"
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                return "unknown", {}, "Invalid JSON"

            if not data:
                return "dead", {}, "Empty JSON"

            # Visibility wrapper unwrap karein
            if data.get("__typename") == "TweetWithVisibilityResults":
                data = data.get("tweet") or {}

            typename = data.get("__typename")
            if "tombstone" in data or typename in ("TweetTombstone", "TweetUnavailable"):
                return "dead", data, f"Gone ({typename or 'tombstone'})"

            if typename == "Tweet" or (data.get("id_str") and data.get("user")):
                return "active", data, "Tweet Active"

            return "dead", data, f"Unexpected typename: {typename}"

        return "unknown", {}, f"HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return "unknown", {}, str(e)[:40]

def _fetch_fxtwitter_details(session, tweet_id):
    """FxTwitter se views, likes, followers aur status code check karta hai."""
    api_url = f"https://api.fxtwitter.com/2/status/{tweet_id}"
    try:
        resp = session.get(api_url, headers={"User-Agent": "MyMultiScraper/1.0"}, timeout=10)
        if resp.status_code in (401, 403, 404, 410):
            return "dead", {}, f"HTTP {resp.status_code}"
        data = resp.json()
        code = data.get("code", resp.status_code)
        if code in (401, 403, 404, 410):
            return "dead", {}, f"API Code {code}"
        if code == 200:
            tweet = data.get("status") or data.get("tweet") or {}
            if tweet:
                return "active", tweet, "Code 200"
        return "unknown", {}, f"Code {code}"
    except Exception as e:
        return "unknown", {}, str(e)[:40]

def check_x_status(url, debug=False):
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

    # 1. oEmbed Live Check
    oembed_state, oembed_data, oembed_info = _check_oembed_live(session, canonical_url)
    if oembed_state == "dead" and not debug:
        return _empty_result("Dead / Private", url)

    # 2. Syndication Live Check
    synd_state, synd_data, synd_info = _check_syndication_live(session, tweet_id)
    if synd_state == "dead" and not debug:
        return _empty_result("Dead / Private", url)

    # 3. FxTwitter Details Check
    fx_state, fx_tweet, fx_info = _fetch_fxtwitter_details(session, tweet_id)

    if debug:
        print(f"[DEBUG] {url}\n  oEmbed={oembed_state} ({oembed_info}) | Synd={synd_state} ({synd_info}) | Fx={fx_state} ({fx_info})")

    # STRICT RULE: Agar koi bhi endpoint tweet ko dead bole -> Dead / Private
    if oembed_state == "dead" or synd_state == "dead" or fx_state == "dead":
        return _empty_result("Dead / Private", url)

    # Kam se kam ek X live endpoint (oEmbed ya Syndication) ka Active hona zaroori hai
    if oembed_state != "active" and synd_state != "active":
        if "rate_limited" in (oembed_state, synd_state):
            return _empty_result("Rate Limited", url, "X rate limited live check")
        return _empty_result("Error", url, "Could not verify live status")

    fx_author = fx_tweet.get("author") or {}
    synd_user = synd_data.get("user") or {}

    actual_author = (
        fx_author.get("screen_name")
        or synd_user.get("screen_name")
        or ""
    )

    # Agar URL me diya gaya username aur tweet ka asli author alag ho, toh check karein ki URL wala account zinda hai ya nahi
    if url_username and actual_author and url_username.lower() != actual_author.lower():
        prof_state, _, prof_info = _check_oembed_live(session, f"https://x.com/{url_username}")
        if debug:
            print(f"  [DEBUG] Handle mismatch ({url_username} != {actual_author}), profile check={prof_state} ({prof_info})")
        if prof_state == "dead":
            return _empty_result("Dead / Private", url)

    raw_text = fx_tweet.get("text") or synd_data.get("text") or ""
    clean_text = " ".join(raw_text.split())
    short_text = (clean_text[:50] + "...") if len(clean_text) > 50 else clean_text
    if not short_text:
        short_text = "No text content"

    author_display = actual_author or oembed_data.get("author_name") or "Unknown"
    likes = fx_tweet.get("likes") if fx_tweet.get("likes") is not None else synd_data.get("favorite_count")
    views = fx_tweet.get("views")
    followers = fx_author.get("followers") if fx_author.get("followers") is not None else synd_user.get("followers_count")
    created_at = fx_tweet.get("created_at") or synd_data.get("created_at") or "-"

    return {
        "status": "Active",
        "url": url,
        "title": short_text,
        "author": author_display,
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


# --- Test with Debug Output ---
if __name__ == "__main__":
    print(check_x_status("https://x.com/Goodwatchin/status/2078540370623754363", debug=True))
    print(check_x_status("https://x.com/X/status/1683920951807971329", debug=True))