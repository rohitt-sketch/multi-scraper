"""
X/Twitter status checker v2

Rule: Dead sirf pakke saboot par. Shak ho to Error / Rate Limited (retry), Dead NAHI.

  Primary   : oEmbed (publish.x.com) + Syndication (cdn.syndication.twimg.com)
  Secondary : fxtwitter + vxtwitter (sirf confirm / metadata ke liye)

  - Primary me se koi 1 Active            -> Active  (ek 404 flake ignore)
  - Dono primary Dead (secondary na ulte) -> Dead / Private
  - Sirf 1 primary Dead                   -> secondary se confirm ho tabhi Dead, warna Error
  - Kuch clear nahi / network / 429       -> Error / Rate Limited (auto recheck 1 baar)
  - Tweet zinda par media copyright/DMCA se disabled -> Dead / Private (media_check=False se band)

Setup:  pip install requests
Use:
    from x_checker_v2 import check_x_status
    print(check_x_status("https://x.com/user/status/123456789"))
"""
from __future__ import annotations

import concurrent.futures
import html as _html
import math
import re
import threading
import time
from decimal import Decimal, localcontext
from typing import NamedTuple, Optional
from urllib.parse import quote

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

ACTIVE, DEAD, UNKNOWN, RATE = "active", "dead", "unknown", "rate_limited"

_local = threading.local()


class Sig(NamedTuple):
    state: str      # active | dead | unknown | rate_limited
    data: dict      # parsed payload (sirf active me kaam ka)
    info: str       # debug reason


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _session() -> requests.Session:
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _local.s = s
    return _local.s


def _get(url, headers=None, timeout=12, tries=3, backoff=1.0):
    """Returns (response | None, error | None). 429/5xx/network par retry."""
    resp, err = None, None
    for i in range(tries):
        try:
            resp, err = _session().get(url, headers=headers, timeout=timeout), None
            if resp.status_code != 429 and resp.status_code < 500:
                return resp, None
        except requests.RequestException as e:
            resp, err = None, e
        if i < tries - 1:
            time.sleep(backoff * (i + 1))
    return resp, err


def _failure(resp, err, name) -> Optional[Sig]:
    """Network / 429 / 5xx ko Unknown ya Rate me badalta hai. Normal response par None."""
    if resp is None:
        return Sig(UNKNOWN, {}, f"{name} net: {str(err)[:50]}")
    if resp.status_code == 429:
        return Sig(RATE, {}, f"{name} 429")
    if resp.status_code >= 500:
        return Sig(UNKNOWN, {}, f"{name} HTTP {resp.status_code}")
    return None


def _http_dead(resp) -> bool:
    """404/410 = dead. 401/403 = dead sirf jab HTML bot-wall na ho."""
    code = resp.status_code
    if code in (404, 410):
        return True
    if code in (401, 403):
        return "<html" not in (resp.text or "")[:500].lower()
    return False


def _json(resp):
    try:
        d = resp.json()
        return d if isinstance(d, dict) else None
    except ValueError:
        return None


_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.|mobile\.)?"
    r"(?:x|twitter|fxtwitter|fixupx|vxtwitter|pxtwitter)\.com/"
    r"(?:i/web|[^/?#]+)/status(?:es)?/(\d+)",
    re.IGNORECASE,
)


def extract_tweet_id(url) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    m = _URL_RE.match(url.strip())
    return m.group(1) if m else None


def _get_token(tweet_id: str) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    with localcontext() as ctx:
        ctx.prec = 40
        num = (Decimal(str(tweet_id)) / (Decimal(10) ** 15)) * Decimal(str(math.pi))
        ip = int(num)
        fp = num - ip
        digits = []
        while ip > 0:
            digits.append(chars[ip % 36])
            ip //= 36
        res = "".join(reversed(digits)) or "0"
        frac = []
        for _ in range(12):
            fp *= 36
            x = int(fp)
            frac.append(chars[x])
            fp -= x
            if fp == 0:
                break
    return (res + "".join(frac)).replace("0", "")


# --------------------------------------------------------------------------- #
# individual checkers
# --------------------------------------------------------------------------- #
def check_oembed(tid) -> Sig:
    target = quote(f"https://x.com/i/status/{tid}", safe="")
    resp, err = _get(f"https://publish.x.com/oembed?url={target}&omit_script=true")
    bad = _failure(resp, err, "oembed")
    if bad:
        return bad
    if _http_dead(resp):
        return Sig(DEAD, {}, f"oembed HTTP {resp.status_code}")
    if resp.status_code == 200:
        d = _json(resp)
        if d and d.get("html"):
            return Sig(ACTIVE, d, "oembed 200")
        return Sig(UNKNOWN, {}, "oembed 200 but no html")
    return Sig(UNKNOWN, {}, f"oembed HTTP {resp.status_code}")


def check_syndication(tid) -> Sig:
    url = (f"https://cdn.syndication.twimg.com/tweet-result"
           f"?id={tid}&lang=en&token={_get_token(tid)}")
    resp, err = _get(url, headers={"Accept": "application/json",
                                   "Referer": "https://platform.twitter.com/"})
    bad = _failure(resp, err, "synd")
    if bad:
        return bad
    if _http_dead(resp):
        return Sig(DEAD, {}, f"synd HTTP {resp.status_code}")
    if resp.status_code == 200:
        d = _json(resp)
        if d is None:
            return Sig(UNKNOWN, {}, "synd bad JSON")
        if not d:
            return Sig(DEAD, {}, "synd empty")
        if d.get("__typename") == "TweetWithVisibilityResults":
            d = d.get("tweet") or {}
        tn = d.get("__typename")
        if "tombstone" in d or tn in ("TweetTombstone", "TweetUnavailable"):
            return Sig(DEAD, d, f"synd tombstone ({tn})")
        if tn == "Tweet" or (d.get("id_str") and d.get("user")):
            return Sig(ACTIVE, d, "synd Tweet")
        return Sig(UNKNOWN, d, f"synd unknown typename {tn}")
    return Sig(UNKNOWN, {}, f"synd HTTP {resp.status_code}")


def check_fx(tid) -> Sig:
    resp, err = _get(f"https://api.fxtwitter.com/2/status/{tid}",
                     headers={"User-Agent": "x-status-checker/2.0"})
    bad = _failure(resp, err, "fx")
    if bad:
        return bad
    d = _json(resp)
    if d is None:
        return Sig(DEAD if _http_dead(resp) else UNKNOWN, {}, f"fx HTTP {resp.status_code} non-JSON")
    tweet = d.get("status") or d.get("tweet")
    if isinstance(tweet, dict) and tweet:
        return Sig(ACTIVE, tweet, "fx 200")
    code = d.get("code", resp.status_code)
    if code in (401, 403, 404, 410):
        return Sig(DEAD, {}, f"fx code {code}")
    return Sig(UNKNOWN, {}, f"fx code {code}")


def check_vx(tid) -> Sig:
    resp, err = _get(f"https://api.vxtwitter.com/Twitter/status/{tid}",
                     headers={"User-Agent": "x-status-checker/2.0"})
    bad = _failure(resp, err, "vx")
    if bad:
        return bad
    txt = resp.text or ""
    if "Failed to scan your link" in txt:
        return Sig(DEAD, {}, "vx not-found")
    d = _json(resp)
    if d is None:
        return Sig(DEAD if _http_dead(resp) else UNKNOWN, {}, f"vx HTTP {resp.status_code} non-JSON")
    if d.get("tweetID") or (d.get("text") and d.get("user_screen_name")):
        return Sig(ACTIVE, d, "vx OK")
    if d.get("code") in (401, 403, 404, 410):
        return Sig(DEAD, {}, f"vx code {d.get('code')}")
    return Sig(UNKNOWN, {}, "vx unclear")


# --------------------------------------------------------------------------- #
# decision
# --------------------------------------------------------------------------- #
def decide(o: Sig, s: Sig, f: Sig, v: Optional[Sig] = None):
    prim = (o.state, s.state)
    sec = tuple(x.state for x in (f, v) if x is not None)
    pa, pd = prim.count(ACTIVE), prim.count(DEAD)
    sa, sd = sec.count(ACTIVE), sec.count(DEAD)

    if pa:
        note = " (ek primary dead ignore: flake/sensitive)" if pd else ""
        return "Active", f"primary {pa}/2 active{note}"

    if pd == 2:
        if sa > sd:
            return "Error", f"primary dono dead par secondary active ({sa} vs {sd}) - recheck"
        return "Dead / Private", "oEmbed + syndication dono dead"

    if pd == 1:
        if sa >= 1:
            return "Error", "1 primary dead vs secondary active - recheck"
        if sd >= 1:
            return "Dead / Private", "1 primary dead + secondary dead"
        return "Error", "1 primary dead, confirm nahi hua - recheck (Dead nahi)"

    # primary ne kuch clear nahi bola
    if sa >= 1 and sd == 0:
        return "Active", "primary silent, secondary active"
    if RATE in prim + sec:
        return "Rate Limited", "rate limit - thoda ruk ke retry karo"
    return "Error", "sab unknown/conflict (network?) - Dead nahi, retry karo"


# --------------------------------------------------------------------------- #
# metadata
# --------------------------------------------------------------------------- #
def _data(sig: Optional[Sig]) -> dict:
    return sig.data if sig is not None and sig.state == ACTIVE else {}


def _first(*vals, default=None):
    for x in vals:
        if x is not None and x != "" and x != {}:
            return x
    return default


def _fmt(x, default):
    return f"{x:,}" if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def _meta(o, s, f, v):
    od, sd_, fd, vd = _data(o), _data(s), _data(f), _data(v)
    fa = fd.get("author") or {}
    su = sd_.get("user") or {}
    m = re.search(r"(?:x|twitter)\.com/([^/?#]+)/status", od.get("url") or "")

    author = _first(fa.get("screen_name"), su.get("screen_name"), vd.get("user_screen_name"),
                    m.group(1) if m else None, (od.get("author_name") or "").strip() or None,
                    default="Unknown")

    text = _first(fd.get("text"), vd.get("text"), sd_.get("text"), default="")
    if not text and od.get("html"):
        text = _html.unescape(" ".join(re.sub(r"<[^>]+>", " ", od["html"]).split()))
    text = " ".join((text or "").split())
    title = (text[:50] + "...") if len(text) > 50 else (text or "No text content")

    return {
        "title": title,
        "author": author,
        "likes": _fmt(_first(fd.get("likes"), sd_.get("favorite_count"), vd.get("likes")), "0"),
        "views": _fmt(fd.get("views"), "N/A"),
        "date": _first(fd.get("created_at"), vd.get("date"), sd_.get("created_at"), default="-"),
        "subs": _fmt(_first(fa.get("followers"), su.get("followers_count")), "N/A"),
    }


def _result(status, url, title="-", **kw):
    base = {"status": status, "url": url, "title": title, "author": "-",
            "likes": "-", "views": "-", "date": "-", "subs": "-", "note": "-"}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# media disabled (copyright / DMCA) detection
# Tweet zinda hota hai par media "disabled in response to a report by the
# copyright owner" hota hai -> hum isse Dead / Private maante hain.
# --------------------------------------------------------------------------- #
_DMCA_RE = re.compile(r"dmca|copyright", re.I)
_DISABLED_TXT_RE = re.compile(r"disabled in response to a report|media has been disabled", re.I)
_TRAIL_TCO_RE = re.compile(r"\s*https://t\.co/\w+\s*")


def _scan_media_flags(obj, depth=0):
    """Payload me kahin bhi explicit 'media unavailable / DMCA' flag dhundta hai."""
    if depth > 12:
        return None
    if isinstance(obj, dict):
        ema = obj.get("ext_media_availability")
        if isinstance(ema, dict):
            st = str(ema.get("status", "")).strip().lower()
            if st and st != "available":
                return f"ext_media_availability={ema.get('status')} ({ema.get('reason', '')})"
        if obj.get("withheld_copyright") is True:
            return "withheld_copyright=true"
        for k, val in obj.items():
            if k in ("reason", "withheld_reason") and isinstance(val, str) and _DMCA_RE.search(val):
                return f"{k}={val}"
            hit = _scan_media_flags(val, depth + 1)
            if hit:
                return hit
    elif isinstance(obj, list):
        for val in obj:
            hit = _scan_media_flags(val, depth + 1)
            if hit:
                return hit
    elif isinstance(obj, str) and _DISABLED_TXT_RE.search(obj):
        return "text: media disabled by copyright owner"
    return None


def _media_missing_heuristic(sy: dict) -> Optional[str]:
    """Syndication me text ke end me media wala t.co link hai par media object gayab -> media hata hua.
    Quote-tweets me bhi trailing link cut hota hai, isliye unhe exclude karte hain."""
    if not sy:
        return None
    rng = sy.get("display_text_range")
    text = sy.get("text") or ""
    if not (isinstance(rng, list) and len(rng) == 2 and isinstance(rng[1], int)):
        return None
    if not _TRAIL_TCO_RE.fullmatch(text[rng[1]:]):
        return None
    if sy.get("mediaDetails") or sy.get("photos") or sy.get("video"):
        return None
    if sy.get("quoted_tweet") or sy.get("is_quote_status"):
        return None
    return "media attached tha par ab media data gayab (likely removed/disabled)"


def media_disabled(o, s, f, v=None) -> Optional[str]:
    """Reason string agar tweet ka media disabled/removed lagta hai, warna None."""
    for sig in (s, f, v):
        hit = _scan_media_flags(_data(sig))
        if hit:
            return hit
    return _media_missing_heuristic(_data(s))


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def _round(tid):
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        fo, fs, ff = ex.submit(check_oembed, tid), ex.submit(check_syndication, tid), ex.submit(check_fx, tid)
        o, s, f = fo.result(), fs.result(), ff.result()
    verdict, reason = decide(o, s, f)
    v = None
    if verdict in ("Error", "Rate Limited"):      # tie-breaker, sirf zarurat par
        v = check_vx(tid)
        verdict, reason = decide(o, s, f, v)
    return verdict, reason, (o, s, f, v)


def check_x_status(url, debug=False, recheck=True, media_check=True):
    url = (url or "").strip()
    tid = extract_tweet_id(url)
    if not tid:
        return _result("Invalid URL", url)
    try:
        attempts = 2 if recheck else 1
        for attempt in range(attempts):
            verdict, reason, sigs = _round(tid)
            if debug:
                names = ("oembed", "synd", "fx", "vx")
                print(f"[DEBUG] {url} (try {attempt + 1})")
                print("  " + " | ".join(f"{n}={x.state} ({x.info})" for n, x in zip(names, sigs) if x))
                print(f"  => {verdict} ({reason})")
            if verdict not in ("Error", "Rate Limited"):
                break
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
    except Exception as e:  # koi bhi surprise Dead nahi banega
        return _result("Error", url, f"internal: {str(e)[:60]}")

    if verdict == "Active":
        meta = _meta(*sigs)
        if media_check:
            why = media_disabled(*sigs)
            if debug:
                print(f"  media check: {why or 'ok (media available / no media)'}")
            if why:
                return _result("Dead / Private", url, note=f"media disabled: {why}", **meta)
        return _result("Active", url, **meta)
    title = reason if verdict in ("Rate Limited", "Error") else "-"
    return _result(verdict, url, title, note=reason)


def scrape_data(urls_str, max_workers=5):
    urls = [u.strip() for u in (urls_str or "").splitlines() if u.strip()]
    if not urls:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(check_x_status, urls))


def check_status(urls_str):
    return [{"status": r["status"], "url": r["url"]} for r in scrape_data(urls_str)]


def dump_raw(url):
    """Debug: syndication + fx ka raw JSON print karta hai (media detection check karne ke liye)."""
    import json
    tid = extract_tweet_id(url)
    for name, sig in (("syndication", check_syndication(tid)), ("fxtwitter", check_fx(tid))):
        print(f"\n===== {name}: {sig.state} ({sig.info}) =====")
        print(json.dumps(sig.data, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    u = args[0] if args else "https://x.com/Goodwatchin/status/2121610324717588488"
    if "--raw" in sys.argv:
        dump_raw(u)
    r = check_x_status(u, debug=True)
    print(r)
    print("STATUS:", r["status"], "|", r["note"])