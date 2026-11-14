import json
import unittest
from unittest import mock

import x

URL = "https://x.com/abc/status/1234567890123456789"


class R:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


OEMBED = {"html": "<blockquote>hello</blockquote>", "url": "https://twitter.com/abc/status/1", "author_name": "ABC"}
SYND = {"__typename": "Tweet", "id_str": "1", "user": {"screen_name": "abc", "followers_count": 10},
        "text": "hello", "favorite_count": 5, "created_at": "2026-01-01"}
FX = {"code": 200, "status": {"text": "hello", "likes": 5, "views": 100, "created_at": "d",
                              "author": {"screen_name": "abc", "followers": 10}}}
VX = {"tweetID": "1", "text": "hello", "user_screen_name": "abc", "likes": 5}
HTML_WALL = "<html><body>blocked</body></html>"


def router(o, s, f, v):
    def fake_get(url, headers=None, **kw):
        for key, val in (("publish.x.com", o), ("syndication", s), ("api.fxtwitter", f), ("api.vxtwitter", v)):
            if key in url:
                return (None, val) if isinstance(val, Exception) else (val, None)
        raise AssertionError(url)
    return fake_get


def run(o, s, f, v, **kw):
    with mock.patch.object(x, "_get", router(o, s, f, v)), mock.patch.object(x.time, "sleep"):
        return x.check_x_status(URL, **kw)


class Tests(unittest.TestCase):
    def test_active_all(self):
        r = run(R(200, OEMBED), R(200, SYND), R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Active")
        self.assertEqual((r["author"], r["likes"], r["views"], r["subs"]), ("abc", "5", "100", "10"))

    def test_deleted(self):
        r = run(R(404, {"e": 1}), R(404), R(404, {"code": 404}), R(404, text="Failed to scan your link"))
        self.assertEqual(r["status"], "Dead / Private")

    def test_protected_403_json(self):
        r = run(R(403, {"e": "not authorized"}), R(403, {"e": 1}), R(401, {"code": 401}), R(200, text="Failed to scan your link"))
        self.assertEqual(r["status"], "Dead / Private")

    def test_single_primary_404_flake_is_active(self):
        r = run(R(404, {"e": 1}), R(200, SYND), R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Active")

    def test_bot_wall_not_dead(self):
        r = run(R(403, text=HTML_WALL), R(403, text=HTML_WALL), R(200, FX), R(200, VX))
        self.assertNotEqual(r["status"], "Dead / Private")

    def test_network_down_is_error_not_dead(self):
        import requests
        e = requests.ConnectionError("down")
        r = run(e, e, e, e)
        self.assertEqual(r["status"], "Error")

    def test_all_429_is_rate_limited(self):
        r = run(R(429), R(429), R(429), R(429))
        self.assertEqual(r["status"], "Rate Limited")

    def test_primary_dead_but_third_party_active_is_error(self):
        r = run(R(404, {"e": 1}), R(404), R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Error")

    def test_one_primary_dead_other_unknown_is_error(self):
        r = run(R(404, {"e": 1}), R(500), R(500), R(500))
        self.assertEqual(r["status"], "Error")

    def test_tombstone_dead(self):
        r = run(R(404, {"e": 1}), R(200, {"__typename": "TweetTombstone", "tombstone": {}}), R(404, {"code": 404}), R(404, text="x"))
        self.assertEqual(r["status"], "Dead / Private")


    # ---- media disabled (copyright) ----
    def _synd(self, **extra):
        d = dict(SYND)
        d.update(extra)
        return R(200, d)

    TXT = "#dune #DuneDoubleFeatureIMAX #DunePartThree #zendaya #movies https://t.co/AbC123"

    def test_media_explicit_dmca_flag_is_dead(self):
        md = [{"type": "video", "ext_media_availability": {"status": "Unavailable", "reason": "Dmca"}}]
        r = run(R(200, OEMBED), self._synd(mediaDetails=md), R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Dead / Private")
        self.assertIn("media disabled", r["note"])

    def test_media_withheld_copyright_key(self):
        r = run(R(200, OEMBED), self._synd(withheld_copyright=True), R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Dead / Private")

    def test_media_missing_heuristic_is_dead(self):
        text = self.TXT
        end = text.index(" https://t.co")
        r = run(R(200, OEMBED), self._synd(text=text, display_text_range=[0, end]), R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Dead / Private")

    def test_media_present_and_available_is_active(self):
        text = self.TXT
        end = text.index(" https://t.co")
        md = [{"type": "video", "ext_media_availability": {"status": "Available"}}]
        r = run(R(200, OEMBED), self._synd(text=text, display_text_range=[0, end], mediaDetails=md),
                R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Active")

    def test_quote_tweet_trailing_link_not_dead(self):
        text = "nice take https://t.co/Qq1"
        r = run(R(200, OEMBED), self._synd(text=text, display_text_range=[0, 9], quoted_tweet={"id_str": "2"}),
                R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Active")

    def test_link_tweet_inside_display_range_is_active(self):
        text = "read this https://t.co/Zz9"
        r = run(R(200, OEMBED), self._synd(text=text, display_text_range=[0, len(text)]), R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Active")

    def test_media_check_can_be_disabled(self):
        r = run(R(200, OEMBED), self._synd(withheld_copyright=True), R(200, FX), R(200, VX), media_check=False)
        self.assertEqual(r["status"], "Active")

    def test_media_flag_in_fx_payload(self):
        fx = json.loads(json.dumps(FX))
        fx["status"]["media"] = {"all": [{"ext_media_availability": {"status": "Unavailable", "reason": "Dmca"}}]}
        r = run(R(200, OEMBED), R(200, SYND), R(200, fx), R(200, VX))
        self.assertEqual(r["status"], "Dead / Private")

    def test_disabled_text_in_payload(self):
        r = run(R(200, OEMBED), self._synd(note_text="This media has been disabled in response to a report by the copyright owner"),
                R(200, FX), R(200, VX))
        self.assertEqual(r["status"], "Dead / Private")

    def test_invalid_url(self):
        self.assertEqual(x.check_x_status("https://example.com/nope")["status"], "Invalid URL")
        self.assertEqual(x.check_x_status("")["status"], "Invalid URL")

    def test_url_variants(self):
        for u in ("https://twitter.com/a/status/99", "x.com/i/web/status/99",
                  "https://mobile.twitter.com/a/statuses/99?s=20", "https://fxtwitter.com/a/status/99"):
            self.assertEqual(x.extract_tweet_id(u), "99", u)

    def test_scrape_order(self):
        with mock.patch.object(x, "check_x_status", side_effect=lambda u: {"status": "Active", "url": u}):
            out = x.scrape_data("a\n\nb\nc")
        self.assertEqual([r["url"] for r in out], ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
