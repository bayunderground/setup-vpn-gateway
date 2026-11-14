import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "gateway"))

import happ_watch as hw  # noqa: E402


def read_line(fd, payload):
    return f'990   02:00:00.000001 read({fd}, "{payload}", {len(payload)}) = {len(payload)}\n'


def write_line(fd, payload):
    return f'990   02:00:00.000002 write({fd}, "{payload}", {len(payload)}) = {len(payload)}\n'


STOP_REQ = read_line(7, '\\0\\0\\0A{\\"action\\":\\"stop\\",\\"process-id\\":\\"xray-core\\",\\"request-id\\":\\"req_1\\"}')
START_REQ = read_line(7, '\\0\\0\\0z{\\"action\\":\\"start\\",\\"arguments\\":[],\\"executable\\":\\"/opt/happ/bin/core/xray\\",\\"process-id\\":\\"xray-core\\",\\"stdin-data\\":\\"{\\\\\\"log\\\\\\":{}}\\"}')
STARTED_EVT = write_line(7, '\\0\\0\\0N{\\"event\\":\\"started\\",\\"process-id\\":\\"xray-core\\",\\"timestamp\\":\\"2026-11-14T02:05:39\\"}')
FINISHED_0 = write_line(7, '\\0\\0\\0Z{\\"data\\":\\"0\\",\\"event\\":\\"finished\\",\\"process-id\\":\\"xray-core\\",\\"timestamp\\":\\"2026-11-14T02:05:50\\"}')
FINISHED_9 = write_line(7, '\\0\\0\\0Z{\\"data\\":\\"9\\",\\"event\\":\\"finished\\",\\"process-id\\":\\"xray-core\\",\\"timestamp\\":\\"2026-11-14T02:09:15\\"}')
CRASHED = write_line(7, '\\0\\0\\0e{\\"data\\":\\"Process crashed\\",\\"event\\":\\"error\\",\\"process-id\\":\\"xray-core\\"}')
STATUS_RUNNING = write_line(7, '\\0\\0\\0\\256{\\"pid\\":53193,\\"process-id\\":\\"xray-core\\",\\"running\\":true,\\"state\\":2,\\"status\\":\\"success\\"}')
NOT_FOUND = write_line(7, '\\0\\0\\0r{\\"error\\":\\"Process not found: xray-core\\",\\"request-id\\":\\"req_749\\",\\"status\\":\\"error\\"}')


def run(lines):
    state = hw.State()
    seen = []
    for line in lines:
        for event in hw.parse_line(line):
            if state.apply(event):
                seen.append((state.intent, state.process))
    return state, seen


class ParseTests(unittest.TestCase):
    def test_stop_request_detected(self):
        self.assertEqual(hw.parse_line(STOP_REQ), [("stop_request",)])

    def test_start_request_detected(self):
        self.assertEqual(hw.parse_line(START_REQ), [("start_request",)])

    def test_started_event_detected(self):
        self.assertEqual(hw.parse_line(STARTED_EVT), [("started",)])

    def test_finished_codes_detected(self):
        self.assertEqual(hw.parse_line(FINISHED_0), [("finished", "0")])
        self.assertEqual(hw.parse_line(FINISHED_9), [("finished", "9")])

    def test_crash_detected(self):
        self.assertEqual(hw.parse_line(CRASHED), [("crashed",)])

    def test_status_reply_is_not_an_event(self):
        self.assertEqual(hw.parse_line(STATUS_RUNNING), [])

    def test_stdin_and_stdout_ignored(self):
        self.assertEqual(hw.parse_line(read_line(0, '{\\"action\\":\\"stop\\",\\"process-id\\":\\"xray-core\\"}')), [])
        self.assertEqual(hw.parse_line(write_line(1, 'x \\"event\\":\\"started\\",\\"process-id\\":\\"xray-core\\"')), [])

    def test_request_text_in_a_write_is_ignored(self):
        self.assertEqual(hw.parse_line(write_line(7, '{\\"action\\":\\"stop\\",\\"process-id\\":\\"xray-core\\"}')), [])

    def test_other_process_ignored(self):
        self.assertEqual(hw.parse_line(read_line(7, '{\\"action\\":\\"stop\\",\\"process-id\\":\\"sing-box\\"}')), [])

    def test_non_syscall_lines_ignored(self):
        self.assertEqual(hw.parse_line("strace: Process 990 attached with 2 threads\n"), [])
        self.assertEqual(hw.parse_line(""), [])


class StateTests(unittest.TestCase):
    def test_starts_unknown(self):
        state = hw.State()
        self.assertEqual((state.intent, state.process), ("UNKNOWN", "unknown"))

    def test_user_off_then_on_then_off(self):
        _, seen = run([STOP_REQ, FINISHED_0, START_REQ, STARTED_EVT, STOP_REQ, FINISHED_0])
        self.assertEqual(seen, [
            ("TRANSITION", "up"), ("DISABLED", "down"),
            ("TRANSITION", "unknown"), ("ENABLED", "up"),
            ("TRANSITION", "up"), ("DISABLED", "down"),
        ])

    def test_user_stop_without_finished_event_is_disabled(self):
        # Observed on 2026-11-14 at 02:06:33: stop, status polls, then "Process not found", no finished event.
        state, seen = run([STARTED_EVT, STATUS_RUNNING, STOP_REQ, STATUS_RUNNING, NOT_FOUND])
        self.assertEqual(seen, [("ENABLED", "up"), ("TRANSITION", "up"), ("DISABLED", "down")])
        self.assertEqual(state.intent, "DISABLED")

    def test_stop_still_running_stays_transition(self):
        state, _ = run([STARTED_EVT, STOP_REQ, STATUS_RUNNING])
        self.assertEqual((state.intent, state.process), ("TRANSITION", "up"))

    def test_not_found_without_stop_while_enabled_fails_closed(self):
        state, _ = run([STARTED_EVT, NOT_FOUND])
        self.assertEqual((state.intent, state.process), ("ENABLED", "down"))

    def test_not_found_while_disabled_stays_disabled(self):
        state, seen = run([STARTED_EVT, STOP_REQ, NOT_FOUND, NOT_FOUND, NOT_FOUND])
        self.assertEqual(state.intent, "DISABLED")
        self.assertEqual(seen.count(("DISABLED", "down")), 1)

    def test_not_found_while_transition_does_not_enable(self):
        state, _ = run([START_REQ, NOT_FOUND])
        self.assertEqual(state.intent, "TRANSITION")

    def test_crash_is_enabled_but_down(self):
        state, seen = run([STARTED_EVT, CRASHED, FINISHED_9])
        self.assertEqual(seen, [("ENABLED", "up"), ("ENABLED", "down")])
        self.assertEqual(state.intent, "ENABLED")

    def test_crash_is_not_mistaken_for_user_off(self):
        state, _ = run([STARTED_EVT, CRASHED, FINISHED_9])
        self.assertNotEqual(state.intent, "DISABLED")

    def test_zero_exit_without_stop_request_fails_closed(self):
        state, _ = run([STARTED_EVT, FINISHED_0])
        self.assertEqual((state.intent, state.process), ("ENABLED", "down"))

    def test_stop_request_then_crash_is_not_disabled(self):
        state, _ = run([STARTED_EVT, STOP_REQ, FINISHED_9])
        self.assertEqual((state.intent, state.process), ("ENABLED", "down"))

    def test_gui_cleanup_stop_after_crash_stays_blocked(self):
        # Observed on 2026-11-14 at 02:09:15: crash, then GUI sends stop 0.3 s later, then "Process not found".
        state, seen = run([STARTED_EVT, CRASHED, FINISHED_9, STOP_REQ, NOT_FOUND, NOT_FOUND])
        self.assertEqual((state.intent, state.process), ("ENABLED", "down"))
        self.assertNotIn(("DISABLED", "down"), seen)

    def test_restart_after_crash_recovers(self):
        state, _ = run([STARTED_EVT, CRASHED, FINISHED_9, START_REQ, STARTED_EVT])
        self.assertEqual((state.intent, state.process), ("ENABLED", "up"))

    def test_unknown_reset(self):
        state, _ = run([STARTED_EVT])
        state.unknown("tracer stopped")
        self.assertEqual((state.intent, state.process), ("UNKNOWN", "unknown"))
        self.assertFalse(state.pending_stop)

    def test_replay_prints_only_transitions(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("".join([
                "990 02:00:01.000000 " + STOP_REQ.split(" ", 1)[1],
                "990 02:00:02.000000 " + FINISHED_0.split(" ", 1)[1],
            ]))
            path = f.name
        try:
            with mock.patch("builtins.print") as printer:
                hw.replay(path)
            printed = [c.args[0] for c in printer.call_args_list]
        finally:
            os.unlink(path)
        self.assertEqual(len(printed), 2)
        self.assertIn("TRANSITION", printed[0])
        self.assertIn("DISABLED", printed[1])
        self.assertNotIn("xray-core", " ".join(printed))


class PublishTests(unittest.TestCase):
    def test_publish_writes_atomic_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "vpn-gateway", "state.json")
            with mock.patch.object(hw, "STATE_PATH", target):
                state = hw.State()
                state.set("ENABLED", "up", "test")
                hw.publish(state, 990)
            with open(target) as f:
                doc = json.load(f)
            self.assertEqual(doc["intent"], "ENABLED")
            self.assertEqual(doc["process"], "up")
            self.assertEqual(doc["happd_pid"], 990)
            self.assertIn("updated", doc)
            self.assertEqual(oct(os.stat(target).st_mode & 0o777), "0o644")
            leftovers = [n for n in os.listdir(os.path.dirname(target)) if n.startswith(".state-")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
