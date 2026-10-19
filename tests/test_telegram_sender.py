"""telegram_sender: relay first, straight to Telegram when the relay is down.

No network: urllib.request.urlopen is replaced by a fake that records each URL.
"""
import io
import json
import socket
import unittest
import urllib.error
from unittest import mock

import telegram_sender as ts

ENV = {"TELEGRAM_TOKEN": "123:FAKE", "TELEGRAM_CHAT_ID": "42"}
OK = {"ok": True, "result": {"message_id": 7}}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"{}"))


class Fake:
    """Answers per base: a dict → 200 JSON, an exception → raised."""

    def __init__(self, relay, direct=OK):
        self.relay, self.direct, self.calls = relay, direct, []

    def __call__(self, req, timeout):
        self.calls.append((req.full_url, timeout, json.loads(req.data)))
        ans = self.direct if req.full_url.startswith(ts.DIRECT_BASE) else self.relay
        if isinstance(ans, BaseException):
            raise ans
        return _Resp(json.dumps(ans).encode())


def run(fake, env=ENV, text="FAKE"):
    with mock.patch.dict("os.environ", env, clear=True), \
            mock.patch("urllib.request.urlopen", fake):
        return ts.send(text)


class TestTelegramSender(unittest.TestCase):
    def test_relay_ok_no_direct_call(self):
        f = Fake(relay=OK)
        self.assertEqual(run(f), OK)
        self.assertEqual(len(f.calls), 1)
        url, timeout, body = f.calls[0]
        self.assertTrue(url.startswith(ts.RELAY_BASE + "/bot123:FAKE/sendMessage"))
        self.assertEqual(timeout, ts.RELAY_TIMEOUT_S)
        self.assertLessEqual(ts.RELAY_TIMEOUT_S, 8)
        self.assertEqual(body, {"chat_id": "42", "text": "FAKE", "parse_mode": "HTML",
                                "disable_web_page_preview": True})

    def test_fallback_on_network_errors_and_timeout(self):
        for err in (urllib.error.URLError("refused"), socket.timeout("slow"),
                    TimeoutError("slow"), ConnectionResetError("reset")):
            f = Fake(relay=err)
            self.assertEqual(run(f), OK)
            self.assertEqual([c[0].startswith(ts.DIRECT_BASE) for c in f.calls], [False, True])
            self.assertEqual(f.calls[0][2], f.calls[1][2])  # same body, same text

    def test_fallback_on_5xx_401_404(self):
        for code in (500, 502, 503, 401, 404):
            f = Fake(relay=_http(code))
            self.assertEqual(run(f), OK)
            self.assertEqual(len(f.calls), 2)
            self.assertEqual(f.calls[1][2]["parse_mode"], "HTML")

    def test_telegram_400_keeps_plain_text_retry_via_relay(self):
        f = Fake(relay=_http(400))
        with self.assertRaises(urllib.error.HTTPError):
            run(f)
        # HTML try, then plain-text retry; both via the relay, never direct
        self.assertEqual(len(f.calls), 2)
        self.assertTrue(all(c[0].startswith(ts.RELAY_BASE) for c in f.calls))
        self.assertNotIn("parse_mode", f.calls[1][2])

    def test_env_rollback_goes_direct_only(self):
        f = Fake(relay=OK)
        run(f, env={**ENV, "TELEGRAM_API_BASE": "https://api.telegram.org"})
        self.assertEqual(len(f.calls), 1)
        self.assertTrue(f.calls[0][0].startswith(ts.DIRECT_BASE))
        self.assertEqual(f.calls[0][1], ts.TIMEOUT_S)


if __name__ == "__main__":
    unittest.main()
