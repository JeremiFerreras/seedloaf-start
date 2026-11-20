"""Fault injection for the opt-in provider adapter. No external network."""
import io
import os
import random
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from official_start import (
    ProviderConfig, ProviderError, Response, TransientProviderError,
    config_from_env, parse_status, require_endpoint, request_json,
    run_official, _NoRedirect,
)
from entrypoint import main as entrypoint_main

ID = "123e4567-e89b-42d3-a456-426614174000"
BASE = "https://api.seedloaf.com"
STATUS = BASE + "/v1/servers/status-placeholder"
START = BASE + "/v1/servers/start-placeholder"
TOKEN = "fake-test-token"


def config():
    return ProviderConfig(STATUS, START, TOKEN, ID)


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, token, server_id):
        self.calls.append((method, url, token, server_id))
        if not self.responses:
            raise AssertionError("Unexpected network request")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    @property
    def posts(self):
        return sum(method == "POST" for method, *_ in self.calls)

    @property
    def gets(self):
        return sum(method == "GET" for method, *_ in self.calls)


def answer(state, code=200):
    return Response(code, {"status": state})


class TestConfig(unittest.TestCase):
    def test_valid_url(self):
        self.assertEqual(require_endpoint(START), START)

    def test_main_domain(self):
        self.assertEqual(require_endpoint("https://seedloaf.com/api/start"),
                         "https://seedloaf.com/api/start")

    def test_https_443(self):
        self.assertEqual(require_endpoint("https://seedloaf.com:443/api/start"),
                         "https://seedloaf.com:443/api/start")

    def test_case_insensitive_host(self):
        self.assertEqual(require_endpoint("https://API.SEEDLOAF.COM/action"),
                         "https://API.SEEDLOAF.COM/action")

    def test_disallowed_urls(self):
        urls = (None, 1, "", "/relative", "http://api.seedloaf.com/launch",
                "https://evil.test/launch",
                "https://seedloaf.com.evil.test/start",
                "https://evil-seedloaf.com/start",
                "https://accounts.seedloaf.com/sign-in",
                "https://api.seedloaf.com:8443/start",
                "https://api.seedloaf.com:abc/start",
                "https://u:p@seedloaf.com/start",
                "https://seedloaf.com/",
                "https://seedloaf.com/start?token=secret",
                "https://seedloaf.com/start#fragment",
                "javascript:alert(1)")
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(ProviderError):
                    require_endpoint(url)

    def test_config_valid(self):
        e = {
            "SEEDLOAF_SERVER_ID": ID,
            "SEEDLOAF_OFFICIAL_STATUS_URL": STATUS,
            "SEEDLOAF_OFFICIAL_START_URL": START,
            "SEEDLOAF_OFFICIAL_API_TOKEN": TOKEN,
        }
        c = config_from_env(e)
        self.assertEqual(c.server_id, ID)
        self.assertEqual(c.api_token, TOKEN)

    def test_config_uuid_normalized(self):
        e = {"SEEDLOAF_SERVER_ID": ID.upper(),
             "SEEDLOAF_OFFICIAL_STATUS_URL": STATUS,
             "SEEDLOAF_OFFICIAL_START_URL": START,
             "SEEDLOAF_OFFICIAL_API_TOKEN": TOKEN}
        self.assertEqual(config_from_env(e).server_id, ID)

    def test_missing_secrets_fail_closed(self):
        for missing in ("SEEDLOAF_SERVER_ID", "SEEDLOAF_OFFICIAL_STATUS_URL",
                        "SEEDLOAF_OFFICIAL_START_URL", "SEEDLOAF_OFFICIAL_API_TOKEN"):
            e = {"SEEDLOAF_SERVER_ID": ID,
                 "SEEDLOAF_OFFICIAL_STATUS_URL": STATUS,
                 "SEEDLOAF_OFFICIAL_START_URL": START,
                 "SEEDLOAF_OFFICIAL_API_TOKEN": TOKEN}
            del e[missing]
            with self.subTest(missing=missing):
                with self.assertRaises(ProviderError):
                    config_from_env(e)

    def test_token_with_crlf_rejected(self):
        for token in ("\nabc", "\rabc", "abc\n", "abc\r"):
            e = {"SEEDLOAF_SERVER_ID": ID,
                 "SEEDLOAF_OFFICIAL_STATUS_URL": STATUS,
                 "SEEDLOAF_OFFICIAL_START_URL": START,
                 "SEEDLOAF_OFFICIAL_API_TOKEN": token}
            with self.subTest(token=repr(token)):
                with self.assertRaises(ProviderError):
                    config_from_env(e)


class TestStatus(unittest.TestCase):
    def test_recognized_states(self):
        for raw, expected in (("online", "running"), ("running", "running"),
                              ("STARTING", "starting"), ("booting", "starting"),
                              ("offline", "stopped"), ("stopped", "stopped")):
            with self.subTest(raw=raw):
                self.assertEqual(parse_status(answer(raw)), expected)

    def test_invalid_states_rejected(self):
        for raw in ("", None, False, 1, "crashed", "unknown", "ready?",
                    [], {}, "starting offline"):
            with self.subTest(raw=repr(raw)):
                with self.assertRaises(ProviderError):
                    parse_status(answer(raw))

    def test_missing_status(self):
        with self.assertRaises(ProviderError):
            parse_status(Response(200, {"other": "running"}))


class TestStateMachine(unittest.TestCase):
    def test_already_running_no_post(self):
        t = Transport(answer("running"))
        self.assertEqual(run_official(config(), transport=t, pause=lambda _: None),
                         "running")
        self.assertEqual((t.gets, t.posts), (1, 0))

    def test_starting_no_post(self):
        t = Transport(answer("starting"))
        self.assertEqual(run_official(config(), transport=t, pause=lambda _: None),
                         "starting")
        self.assertEqual(t.posts, 0)

    def test_check_only_never_posts(self):
        t = Transport(answer("stopped"))
        self.assertEqual(run_official(config(), check_only=True,
                                      transport=t, pause=lambda _: None), "stopped")
        self.assertEqual(t.posts, 0)

    def test_stopped_then_started_once_then_running(self):
        t = Transport(answer("stopped"), answer("starting", 202),
                      answer("starting"), answer("running"))
        self.assertEqual(run_official(config(), transport=t,
                                      pause=lambda _: None), "running")
        self.assertEqual((t.posts, t.gets), (1, 3))

    def test_post_running_no_poll(self):
        t = Transport(answer("stopped"), answer("running"))
        self.assertEqual(run_official(config(), transport=t,
                                      pause=lambda _: None), "running")
        self.assertEqual((t.posts, t.gets), (1, 1))

    def test_post_stopped_rejected(self):
        t = Transport(answer("stopped"), answer("stopped"))
        with self.assertRaises(ProviderError):
            run_official(config(), transport=t, pause=lambda _: None)
        self.assertEqual(t.posts, 1)

    def test_post_timeout_never_retried(self):
        t = Transport(answer("stopped"), TransientProviderError("timeout"))
        with self.assertRaises(TransientProviderError):
            run_official(config(), transport=t, pause=lambda _: None)
        self.assertEqual(t.posts, 1)

    def test_post_429_never_retried(self):
        t = Transport(answer("stopped"), TransientProviderError("HTTP 429"))
        with self.assertRaises(TransientProviderError):
            run_official(config(), transport=t, pause=lambda _: None)
        self.assertEqual(t.posts, 1)

    def test_get_429_retry_twice(self):
        t = Transport(TransientProviderError("429"), TransientProviderError("503"),
                      answer("stopped"))
        self.assertEqual(run_official(config(), check_only=True,
                                      transport=t, pause=lambda _: None), "stopped")
        self.assertEqual((t.gets, t.posts), (3, 0))

    def test_get_exhausted_without_post(self):
        t = Transport(*[TransientProviderError("503") for _ in range(3)])
        with self.assertRaises(TransientProviderError):
            run_official(config(), transport=t, pause=lambda _: None)
        self.assertEqual((t.gets, t.posts), (3, 0))

    def test_unauthorized_without_post(self):
        t = Transport(ProviderError("HTTP 401"))
        with self.assertRaises(ProviderError):
            run_official(config(), transport=t, pause=lambda _: None)
        self.assertEqual((t.gets, t.posts), (1, 0))

    def test_unknown_status_never_posts(self):
        t = Transport(answer("unknown"))
        with self.assertRaises(ProviderError):
            run_official(config(), transport=t, pause=lambda _: None)
        self.assertEqual(t.posts, 0)

    def test_polling_timeout_no_second_post(self):
        t = Transport(answer("stopped"), answer("starting", 202),
                      *[answer("starting") for _ in range(20)])
        self.assertEqual(run_official(config(), transport=t, pause=lambda _: None,
                                      status_checks=20), "starting")
        self.assertEqual(t.posts, 1)

    def test_poll_running_after_transient(self):
        t = Transport(answer("stopped"), answer("starting", 202),
                      TransientProviderError("503"), answer("running"))
        self.assertEqual(run_official(config(), transport=t, pause=lambda _: None),
                         "running")
        self.assertEqual(t.posts, 1)

    def test_poll_reports_stopped(self):
        t = Transport(answer("stopped"), answer("starting", 202), answer("stopped"))
        with self.assertRaises(ProviderError):
            run_official(config(), transport=t, pause=lambda _: None)
        self.assertEqual(t.posts, 1)

    def test_post_401_not_repeated(self):
        t = Transport(answer("stopped"), ProviderError("HTTP 401"))
        with self.assertRaises(ProviderError):
            run_official(config(), transport=t, pause=lambda _: None)
        self.assertEqual(t.posts, 1)

    def test_polling_bound_30(self):
        t = Transport(answer("stopped"), answer("starting", 202),
                      *[answer("starting") for _ in range(35)])
        self.assertEqual(run_official(config(), transport=t, pause=lambda _: None,
                                      status_checks=100), "starting")
        self.assertEqual(t.gets, 31)
        self.assertEqual(t.posts, 1)

    def test_zero_polling_returns_pending(self):
        t = Transport(answer("stopped"), answer("starting", 202))
        self.assertEqual(run_official(config(), transport=t, pause=lambda _: None,
                                      status_checks=0), "starting")

    def test_randomized_finite_states_2000(self):
        rng = random.Random(20261120)
        allowed = ["running", "starting", "stopped", "invalid"]
        for _ in range(2000):
            initial = rng.choice(allowed)
            t = Transport(answer(initial))
            if initial in ("stopped",):
                t.responses.append(answer("starting", 202))
            try:
                result = run_official(config(), transport=t, pause=lambda _: None,
                                      status_checks=0)
                self.assertIn(result, ("running", "starting"))
            except ProviderError:
                self.assertEqual(initial, "invalid")
            self.assertLessEqual(t.posts, 1)
            if initial != "stopped":
                self.assertEqual(t.posts, 0)


class TestEntrypoint(unittest.TestCase):
    def test_official_backend_selected(self):
        with patch.dict(os.environ, {"START_BACKEND": "official_api"}):
            with patch("official_start.main", return_value=0) as called:
                self.assertEqual(entrypoint_main(), 0)
                called.assert_called_once()

    def test_browser_backend_selected(self):
        with patch.dict(os.environ, {"START_BACKEND": "browser"}):
            with patch("seedloaf_start.main", return_value=0) as called:
                self.assertEqual(entrypoint_main(), 0)
                called.assert_called_once()

    def test_unknown_backend_rejected(self):
        with patch.dict(os.environ, {"START_BACKEND": "random"}):
            with self.assertRaises(ValueError):
                entrypoint_main()


class TestHttpTransport(unittest.TestCase):
    class FakeResponse:
        def __init__(self, code=200, body=b'{"status":"running"}',
                     content_type="application/json"):
            self.status = code
            self.body = body
            self.headers = {"Content-Type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, max_bytes):
            return self.body[:max_bytes]

    class FakeOpener:
        def __init__(self, action):
            self.action = action
            self.requests = []

        def open(self, request, timeout=10):
            self.requests.append((request, timeout))
            if isinstance(self.action, Exception):
                raise self.action
            return self.action

    def test_http_request_sends_token_only_to_allowed_url(self):
        opener = self.FakeOpener(self.FakeResponse())
        with patch("urllib.request.build_opener", return_value=opener):
            result = request_json("GET", STATUS, TOKEN, ID)
        self.assertEqual(result.data["status"], "running")
        request = opener.requests[0][0]
        self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertEqual(request.get_method(), "GET")

    def test_post_body_uuid(self):
        opener = self.FakeOpener(self.FakeResponse(202, b'{"status":"starting"}'))
        with patch("urllib.request.build_opener", return_value=opener):
            result = request_json("POST", START, TOKEN, ID)
        self.assertEqual(result.http_code, 202)
        request = opener.requests[0][0]
        self.assertIn(ID.encode("ascii"), request.data)
        self.assertEqual(request.get_method(), "POST")

    def test_block_untrusted_url_before_network(self):
        for url in ("https://evil.test/start", "http://seedloaf.com/start",
                    "https://seedloaf.com.evil.test/start"):
            with patch("urllib.request.build_opener") as factory:
                with self.assertRaises(ProviderError):
                    request_json("POST", url, TOKEN, ID)
                factory.assert_not_called()

    def test_disallow_put_delete(self):
        for method in ("DELETE", "PUT", "PATCH", "HEAD"):
            with self.assertRaises(ProviderError):
                request_json(method, START, TOKEN, ID)

    def test_reject_html(self):
        opener = self.FakeOpener(self.FakeResponse(
            body=b"<html>Cloudflare</html>", content_type="text/html"))
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                request_json("GET", STATUS, TOKEN, ID)

    def test_reject_bad_json(self):
        opener = self.FakeOpener(self.FakeResponse(body=b"{bad"))
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                request_json("GET", STATUS, TOKEN, ID)

    def test_reject_too_large_body(self):
        opener = self.FakeOpener(self.FakeResponse(body=b'{' + b'a' * 17000))
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                request_json("GET", STATUS, TOKEN, ID)

    def test_reject_array_json(self):
        opener = self.FakeOpener(self.FakeResponse(body=b'["online"]'))
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                request_json("GET", STATUS, TOKEN, ID)

    def test_redirect_handler_disallows_redirect(self):
        handler = _NoRedirect()
        self.assertIsNone(handler.redirect_request(
            object(), None, 302, "Found", {}, "https://evil.test/"))
    
    def test_redirect_response_raises(self):
        error = urllib.error.HTTPError(STATUS, 302, "Moved", {}, io.BytesIO(b""))
        opener = self.FakeOpener(error)
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                request_json("GET", STATUS, TOKEN, ID)

    def test_rate_limited_transient(self):
        error = urllib.error.HTTPError(STATUS, 429, "Too many", {}, io.BytesIO(b""))
        opener = self.FakeOpener(error)
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(TransientProviderError):
                request_json("GET", STATUS, TOKEN, ID)

    def test_403_permanent(self):
        error = urllib.error.HTTPError(STATUS, 403, "Forbidden", {}, io.BytesIO(b""))
        opener = self.FakeOpener(error)
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                request_json("GET", STATUS, TOKEN, ID)

    def test_network_timeout_transient(self):
        opener = self.FakeOpener(TimeoutError("simulated timeout"))
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(TransientProviderError):
                request_json("GET", STATUS, TOKEN, ID)


class TestOptionalMinecraftPreflight(unittest.TestCase):
    def test_verified_minecraft_skips_browser(self):
        env = {"START_BACKEND": "browser", "MINECRAFT_ADDRESS": "foo.seedloaf.gg"}
        with patch.dict(os.environ, env):
            with patch("mc_probe.minecraft_status", return_value={"responding": True}) as mc:
                with patch("seedloaf_start.main") as browser:
                    self.assertEqual(entrypoint_main(), 0)
                    browser.assert_not_called()
                    mc.assert_called_once_with("foo.seedloaf.gg", timeout=3)

    def test_offline_or_unreachable_falls_back_to_browser(self):
        env = {"START_BACKEND": "browser", "MINECRAFT_ADDRESS": "foo.seedloaf.gg"}
        with patch.dict(os.environ, env):
            with patch("mc_probe.minecraft_status", return_value=None):
                with patch("entrypoint.postflight", return_value="not_confirmed"), \
                     patch("seedloaf_start.main", return_value=0) as browser:
                    self.assertEqual(entrypoint_main(), 0)
                    browser.assert_called_once_with()

    def test_no_host_does_not_probe(self):
        with patch.dict(os.environ, {"START_BACKEND": "browser", "MINECRAFT_ADDRESS": ""}):
            with patch("mc_probe.minecraft_status") as mc:
                with patch("entrypoint.postflight", return_value="not_confirmed"), \
                     patch("seedloaf_start.main", return_value=0) as browser:
                    self.assertEqual(entrypoint_main(), 0)
                    mc.assert_not_called()
                    browser.assert_called_once_with()

    def test_empty_fake_status_does_not_skip_backend(self):
        with patch.dict(os.environ, {"START_BACKEND": "browser", "MINECRAFT_ADDRESS": "foo.seedloaf.gg"}):
            with patch("mc_probe.minecraft_status", return_value={"responding": False}):
                with patch("entrypoint.postflight", return_value="not_confirmed"), \
                     patch("seedloaf_start.main", return_value=0) as browser:
                    self.assertEqual(entrypoint_main(), 0)
                    browser.assert_called_once_with()

    def test_invalid_hostname_rejected_before_browser(self):
        from mc_probe import ProbeError
        with patch.dict(os.environ, {"START_BACKEND": "browser", "MINECRAFT_ADDRESS": "127.0.0.1"}):
            with patch("seedloaf_start.main") as browser:
                with self.assertRaises(ProbeError):
                    entrypoint_main()
                browser.assert_not_called()

    def test_provider_running_skips_official_api_call(self):
        env = {"START_BACKEND": "official_api", "MINECRAFT_ADDRESS": "foo.seedloaf.gg"}
        with patch.dict(os.environ, env):
            with patch("mc_probe.minecraft_status", return_value={"responding": True}):
                with patch("official_start.main") as provider:
                    self.assertEqual(entrypoint_main(), 0)
                    provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
