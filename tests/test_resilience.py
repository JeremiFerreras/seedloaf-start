"""Deterministic fault-injection & fuzz tests. No Seedloaf network calls."""
import itertools
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seedloaf_start import (
    START, STOP, action_for_state, authenticated_dashboard, classify_buttons,
    confirmation_from_state, console_url, is_challenge, is_target, norm,
    retry_challenge_allowed, snapshot_state,
)

SERVER = "123e4567-e89b-42d3-a456-426614174000"
URL = console_url(SERVER)


class Button:
    def __init__(self, text="", aria=None, title=None, visible=True,
                 enabled=True, stale=False):
        self.text = text
        self.attrs = {"aria-label": aria, "title": title}
        self.visible = visible
        self.enabled = enabled
        self.stale = stale

    def is_displayed(self):
        if self.stale:
            raise RuntimeError("Simulated stale element")
        return self.visible

    def is_enabled(self):
        if self.stale:
            raise RuntimeError("Simulated stale element")
        return self.enabled

    def get_attribute(self, name):
        if self.stale:
            raise RuntimeError("Simulated stale element")
        return self.attrs.get(name)


class TestURLs(unittest.TestCase):
    def test_console_url(self):
        self.assertEqual(URL, "https://seedloaf.com/dashboard/" + SERVER + "/console")

    def test_uppercase_uuid_normalized(self):
        self.assertEqual(console_url(SERVER.upper()), URL)

    def test_invalid_uuids(self):
        for bad in (None, 12, "", "/", "a", "../", " " + SERVER,
                    SERVER + "x", "https://evil.test", "00000000"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    console_url(bad)

    def test_normal_url(self):
        self.assertTrue(is_target(URL, SERVER))

    def test_port_443(self):
        self.assertTrue(is_target(URL.replace("seedloaf.com", "seedloaf.com:443"), SERVER))

    def test_trailing_slash(self):
        self.assertTrue(is_target(URL + "/", SERVER))

    def test_query_string_ignored(self):
        self.assertTrue(is_target(URL + "?a=1", SERVER))

    def test_wrong_server(self):
        self.assertFalse(is_target(URL, "b23e4567-e89b-42d3-a456-426614174000"))

    def test_other_dashboard_tab(self):
        self.assertFalse(is_target(URL.replace("/console", "/files"), SERVER))

    def test_path_prefix_attack(self):
        self.assertFalse(is_target(URL + "/../other", SERVER))

    def test_other_domain(self):
        self.assertFalse(is_target(URL.replace("seedloaf.com", "seedloaf.com.evil.test"), SERVER))

    def test_http_rejected(self):
        self.assertFalse(is_target(URL.replace("https:", "http:"), SERVER))

    def test_username_in_url(self):
        self.assertFalse(is_target(URL.replace("https://", "https://seedloaf.com@"), SERVER))

    def test_nondefault_port(self):
        self.assertFalse(is_target(URL.replace("seedloaf.com", "seedloaf.com:8443"), SERVER))

    def test_malformed_port(self):
        self.assertFalse(is_target(URL.replace("seedloaf.com", "seedloaf.com:abc"), SERVER))

    def test_dashboard_signed_in(self):
        self.assertTrue(authenticated_dashboard("https://seedloaf.com/dashboard"))
        self.assertTrue(authenticated_dashboard(URL))

    def test_home_not_authenticated(self):
        self.assertFalse(authenticated_dashboard("https://seedloaf.com/"))

    def test_fake_dashboard_path(self):
        self.assertFalse(authenticated_dashboard("https://seedloaf.com/dashboardish"))

    def test_bad_domain_for_login(self):
        self.assertFalse(authenticated_dashboard("https://accounts.seedloaf.com/sign-in"))
        self.assertFalse(authenticated_dashboard("https://seedloaf.com.evil.test/dashboard"))

    def test_invalid_login_port(self):
        self.assertFalse(authenticated_dashboard("https://seedloaf.com:abc/dashboard"))
        self.assertFalse(authenticated_dashboard("https://seedloaf.com:8080/dashboard"))

    def test_logout_avoids_false_success(self):
        self.assertFalse(authenticated_dashboard("https://seedloaf.com/sign-in"))


class TestButtons(unittest.TestCase):
    def test_single_start(self):
        b = Button("Start")
        self.assertEqual(classify_buttons([b]), ("can_start", b))

    def test_start_server(self):
        self.assertEqual(classify_buttons([Button("Start server")])[0], "can_start")

    def test_spanish_start(self):
        self.assertEqual(classify_buttons([Button("Encender servidor")])[0], "can_start")

    def test_accent_normalization(self):
        self.assertEqual(norm("  ENCÉNDER   SERVIDOR  "), "encender servidor")

    def test_aria_label(self):
        self.assertEqual(classify_buttons([Button(aria="Start Server")])[0], "can_start")

    def test_title_label(self):
        self.assertEqual(classify_buttons([Button(title="Iniciar")])[0], "can_start")

    def test_stop_indicates_running(self):
        self.assertEqual(classify_buttons([Button("Stop")]), ("already_running", None))

    def test_stop_from_aria(self):
        self.assertEqual(classify_buttons([Button(aria="Stop server")])[0], "already_running")

    def test_both_conflict(self):
        self.assertEqual(classify_buttons([Button("Start"), Button("Stop")])[0], "ambiguous")

    def test_two_start_ambiguous(self):
        self.assertEqual(classify_buttons([Button("Start"), Button("Start")])[0], "ambiguous")

    def test_two_stop_ambiguous(self):
        self.assertEqual(classify_buttons([Button("Stop"), Button("Stop")])[0], "ambiguous")

    def test_ambiguous_does_not_return_clickable(self):
        self.assertIsNone(classify_buttons([Button("Start"), Button("Stop")])[1])

    def test_disabled_start_not_clickable(self):
        self.assertEqual(classify_buttons([Button("Start", enabled=False)])[0], "not_found")

    def test_hidden_start_not_clickable(self):
        self.assertEqual(classify_buttons([Button("Start", visible=False)])[0], "not_found")

    def test_hidden_stop_ignored(self):
        self.assertEqual(classify_buttons([Button("Stop", visible=False), Button("Start")])[0],
                         "can_start")

    def test_stale_element_fails_closed(self):
        self.assertEqual(classify_buttons([Button("Start"), Button(stale=True)])[0],
                         "ambiguous")

    def test_empty_buttons(self):
        self.assertEqual(classify_buttons([]), ("not_found", None))

    def test_restart_is_not_start(self):
        self.assertEqual(classify_buttons([Button("Restart")])[0], "not_found")

    def test_long_start_like_label_does_not_match(self):
        self.assertEqual(classify_buttons([Button("Start another server")])[0], "not_found")

    def test_none_labels(self):
        self.assertEqual(classify_buttons([Button(None)])[0], "not_found")

    def test_whitespace_start(self):
        self.assertEqual(classify_buttons([Button("  START   SERVER  ")])[0], "can_start")

    def test_dangerous_buttons_never_start(self):
        labels = ["Delete world", "Restart", "Reset", "Stop now", "Start again",
                  "Cancel", "Back up", "Shutdown", "Execute", "Start all servers"]
        for label in labels:
            with self.subTest(label=label):
                self.assertEqual(classify_buttons([Button(label)])[0], "not_found")


class TestStateMachine(unittest.TestCase):
    def test_snapshot_accepts_exact_page(self):
        self.assertEqual(snapshot_state(URL, SERVER, [Button("Start")])[0], "can_start")

    def test_snapshot_rejects_wrong_page(self):
        self.assertEqual(snapshot_state("https://seedloaf.com/dashboard", SERVER,
                                        [Button("Start")]), ("wrong_page", None))

    def test_snapshot_rejects_phishing_page(self):
        self.assertEqual(snapshot_state("https://evil.example/" + SERVER, SERVER,
                                        [Button("Start")]), ("wrong_page", None))

    def test_live_start_only_on_one_valid_start(self):
        self.assertEqual(action_for_state("can_start", check_only=False), "start")

    def test_check_only_never_requests_start(self):
        self.assertEqual(action_for_state("can_start", check_only=True), "check_off")

    def test_running_never_requests_start(self):
        self.assertEqual(action_for_state("already_running"), "already_running")
        self.assertEqual(action_for_state("already_running", True), "already_running")

    def test_other_states_rejected(self):
        for state in ("ambiguous", "not_found", "wrong_page", "loading", "", "offline"):
            for read_only in (True, False):
                with self.subTest(state=state, read_only=read_only):
                    with self.assertRaises(RuntimeError):
                        action_for_state(state, read_only)

    def test_confirm_running(self):
        self.assertTrue(confirmation_from_state("already_running"))

    def test_start_still_visible_is_not_confirmed(self):
        self.assertFalse(confirmation_from_state("can_start"))

    def test_loading_is_not_confirmed(self):
        self.assertFalse(confirmation_from_state("not_found"))

    def test_never_confirm_ambiguous(self):
        with self.assertRaises(RuntimeError):
            confirmation_from_state("ambiguous")

    def test_never_confirm_wrong_page(self):
        with self.assertRaises(RuntimeError):
            confirmation_from_state("wrong_page")

    def test_confirmation_sequence(self):
        sequence = ["can_start", "not_found", "not_found", "already_running"]
        self.assertEqual([confirmation_from_state(s) for s in sequence],
                         [False, False, False, True])

    def test_challenge_retry_one_time(self):
        self.assertTrue(retry_challenge_allowed(True, 0))
        self.assertFalse(retry_challenge_allowed(True, 1))
        self.assertFalse(retry_challenge_allowed(True, 2))

    def test_no_retry_when_login_fails_without_challenge(self):
        self.assertFalse(retry_challenge_allowed(False, 0))

    def test_negative_retry_counter_fails_closed(self):
        self.assertFalse(retry_challenge_allowed(True, -1))

    def test_detect_challenge_en(self):
        self.assertTrue(is_challenge("Just a moment...", ""))

    def test_detect_challenge_es(self):
        self.assertTrue(is_challenge("", "Verifica que eres humano"))

    def test_no_challenge_normal_page(self):
        self.assertFalse(is_challenge("Seedloaf dashboard", "Start server"))


class TestStress(unittest.TestCase):
    """Thousands of synthetic combinations, deterministic for reproducibility."""

    def test_all_four_button_combinations_1296(self):
        labels = ["Start", "Stop", "Restart", "Delete", "Start Server", "Stop Server"]
        for combo in itertools.product(labels, repeat=4):
            starts = sum(norm(x) in START for x in combo)
            stops = sum(norm(x) in STOP for x in combo)
            expected = ("ambiguous" if starts + stops > 1 else
                        "can_start" if starts == 1 else
                        "already_running" if stops == 1 else "not_found")
            state, selected = classify_buttons([Button(x) for x in combo])
            self.assertEqual(state, expected, msg=str(combo))
            self.assertEqual(selected is not None, expected == "can_start")

    def test_random_unknown_labels_never_activate_start_5000(self):
        rng = random.Random(20261119)
        words = ("restart", "delete", "files", "stop now", "start now", "backup",
                 "reboot", "permissions", "remove", "upgrade", "later", "console")
        for _ in range(5000):
            labels = [rng.choice(words) for _ in range(rng.randint(0, 8))]
            state, selected = classify_buttons([Button(x) for x in labels])
            self.assertEqual(state, "not_found")
            self.assertIsNone(selected)

    def test_random_visibility_enabled_3000(self):
        rng = random.Random(76327)
        for _ in range(3000):
            buttons = [Button(rng.choice(("Start", "Stop", "Restart")),
                              visible=rng.choice((True, False)),
                              enabled=rng.choice((True, False)))
                       for _ in range(rng.randrange(0, 9))]
            visible = [b.text for b in buttons if b.visible and b.enabled]
            s_count = visible.count("Start")
            t_count = visible.count("Stop")
            expected = ("ambiguous" if s_count + t_count > 1 else
                        "can_start" if s_count else
                        "already_running" if t_count else "not_found")
            state, selected = classify_buttons(buttons)
            self.assertEqual(state, expected)
            self.assertEqual(selected is not None, expected == "can_start")

    def test_readonly_1000_scenarios_never_starts(self):
        rng = random.Random(7722)
        states = ("not_found", "ambiguous", "can_start",
                  "already_running", "wrong_page")
        for _ in range(1000):
            state = rng.choice(states)
            try:
                decision = action_for_state(state, True)
            except RuntimeError:
                continue
            self.assertNotEqual(decision, "start")

    def test_only_stop_can_confirm_across_3000_states(self):
        rng = random.Random(1245)
        states = ("not_found", "ambiguous", "can_start", "already_running", "wrong_page")
        for _ in range(3000):
            state = rng.choice(states)
            try:
                confirmed = confirmation_from_state(state)
            except RuntimeError:
                continue
            self.assertEqual(confirmed, state == "already_running")


if __name__ == "__main__":
    unittest.main()
