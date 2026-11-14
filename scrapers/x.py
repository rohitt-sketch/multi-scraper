import re
import threading
import concurrent.futures
import requests

_thread_local = threading.local()

def _get_session():
    """Har thread ke liye alag reusable Session banata hai (fast & thread-safe)."""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        session.headers.update({"User-Agent": "MyMultiScraper/1.0"})
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

def extract_tweet_id(url):
    if not url or not isinstance(url, str):
        return None
    # x.com, twitter.com, mobile/www subdomains, /i/web/status/ aur fxtwitter links ko support karta hai
    match = re.search(
        r"(?:https?://)?(?:www\.|mobile\.)?(?:x|twitter|fxtwitter|fixupx|vxtwitter)\.com/(?:i/web|\w+)/status(?:es)?/(\d+)",
        url,
        re.IGNORECASE,
    )
    return match.group(1) if match else None

def check_x_status(url):
    url = url.strip()
    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        return _empty_result("Invalid URL", url)

    api_url = f"https://api.fxtwitter.com/2/status/{tweet_id}"
    session = _get_session()

    try:
        response = session.get(api_url, timeout=10)

        # Agar API JSON ke bajaye HTML error page bheje (e.g. Cloudflare / 502)
        try:
            data = response.json()
        except ValueError:
            if response.status_code in (401, 403, 404):
                return _empty_result("Dead / Private", url)
            if response.status_code == 429:
                return _empty_result("Rate Limited", url, "Too many requests")
            return _empty_result("Error", url, f"Invalid JSON (HTTP {response.status_code})")

        code = data.get("code", response.status_code)

        # Code 200 matlab tweet active hai
        if code == 200:
            # v2 me 'status' key hoti hai, fallback ke liye 'tweet' bhi check kar liya
            tweet = data.get("status") or data.get("tweet") or {}
            if not tweet:
                return _empty_result("Error", url, "Empty tweet data")

            author = tweet.get("author") or {}

            # Text ke extra newlines/spaces clean karke short title banana
            raw_text = tweet.get("text") or ""
            clean_text = " ".join(raw_text.split())
            short_text = (clean_text[:50] + "...") if len(clean_text) > 50 else clean_text
            if not short_text:
                short_text = "No text content"

            # None values se bachne ke liye safe formatting
            likes = tweet.get("likes")
            views = tweet.get("views")
            followers = author.get("followers")

            return {
                "status": "Active",
                "url": url,
                "title": short_text,
                "author": author.get("screen_name") or "Unknown",
                "likes": f"{likes:,}" if isinstance(likes, (int, float)) else "0",
                "views": f"{views:,}" if isinstance(views, (int, float)) else "N/A",
                "date": tweet.get("created_at") or "-",
                "subs": f"{followers:,}" if isinstance(followers, (int, float)) else "N/A",
            }

        elif code in (401, 403, 404):
            # 404 = Deleted/Not found, 401/403 = Private/Suspended account
            return _empty_result("Dead / Private", url)

        elif code == 429:
            return _empty_result("Rate Limited", url, "Too many requests")

        else:
            msg = data.get("message") or f"API Code {code}"
            return _empty_result("Error", url, str(msg)[:50])

    except requests.exceptions.Timeout:
        return _empty_result("Error", url, "Request timed out")
    except Exception as e:
        return _empty_result("Error", url, str(e)[:50])

def scrape_data(urls_str):
    if not urls_str or not urls_str.strip():
        return []
    url_list = [u.strip() for u in urls_str.splitlines() if u.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        return list(executor.map(check_x_status, url_list))

def check_status(urls_str):
    results = scrape_data(urls_str)
    return [{"status": r["status"], "url": r["url"]} for r in results]


# --- Quick Test ---
if __name__ == "__main__":
    test_urls = """
    https://x.com/elonmusk/status/1850000000000000000
    https://twitter.com/X/status/1683920951807971329
    https://x.com/invalid_url_here
    """
    for item in scrape_data(test_urls):
        print(item)