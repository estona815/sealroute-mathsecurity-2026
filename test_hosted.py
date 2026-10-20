import io
import json
import unittest
from unittest.mock import patch
from hosted import request_model, SUBMISSION_MAX_BYTES, SSE_MAX_BYTES


class FakeOpener:
    def __init__(self, terminal, submission=None):
        self.calls = []
        self.terminal = terminal
        self.submission = submission

    def open(self, request, **kwargs):
        self.calls.append(request)
        if len(self.calls) == 1:
            return io.BytesIO(self.submission if self.submission is not None else
                              json.dumps({"event_id": "a" * 32}).encode())
        return io.BytesIO(self.terminal)


class HostedBoundaryTests(unittest.TestCase):
    def test_actual_payload_contract_and_terminal_parse(self):
        terminal = b"event: complete\ndata: " + json.dumps(["ACCESS", None]).encode() + b"\n"
        opener = FakeOpener(terminal)
        submitted = []
        with patch("urllib.request.build_opener", return_value=opener):
            result = request_model("public synthetic request", on_submitted=submitted.append)
        self.assertEqual(result["response"], "ACCESS")
        self.assertEqual(submitted, ["a" * 32])
        payload = json.loads(opener.calls[0].data)
        self.assertEqual(payload["message"], "public synthetic request")
        self.assertEqual(payload["max_new_tokens"], 64)
        self.assertEqual(payload["temperature"], 0.1)
        self.assertEqual(set(payload), {"message", "max_new_tokens", "temperature"})
        self.assertTrue(opener.calls[0].full_url.endswith("/call/v2/generate"))
        self.assertTrue(opener.calls[1].endswith("/call/generate/" + "a" * 32))
        self.assertEqual(opener.calls[0].get_header("Cookie"), None)
        self.assertEqual(opener.calls[0].get_header("Authorization"), None)
        self.assertEqual(len(opener.calls), 2)

    def test_known_error_has_no_automatic_resubmit(self):
        opener = FakeOpener(b'event: error\ndata: {"error":"fixture rejection"}\n')
        with patch("urllib.request.build_opener", return_value=opener):
            result = request_model("synthetic")
        self.assertEqual(result["terminal"], "error")
        self.assertEqual(len(opener.calls), 2)

    def test_no_terminal_is_unresolved_without_resubmit(self):
        opener = FakeOpener(b'event: heartbeat\ndata: null\n')
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "No terminal"):
                request_model("synthetic")
        self.assertEqual(len(opener.calls), 2)

    def test_oversized_submission_stops_before_polling_and_callback(self):
        opener = FakeOpener(b"", json.dumps({"event_id": "a" * 32,
                            "padding": "x" * SUBMISSION_MAX_BYTES}).encode())
        submitted = []
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "Oversized submission"):
                request_model("synthetic", on_submitted=submitted.append)
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(submitted, [])

    def assert_oversized_stream_rejected(self, terminal):
        opener = FakeOpener(terminal)
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "Oversized SSE"):
                request_model("synthetic")
        self.assertEqual(len(opener.calls), 2)

    def test_single_oversized_line_is_bounded(self):
        self.assert_oversized_stream_rejected(b":" + b"x" * SSE_MAX_BYTES)

    def test_sse_limit_counts_utf8_bytes_not_characters(self):
        self.assert_oversized_stream_rejected((":" + "\u20ac" * 34000 + "\n").encode())

    def test_sse_aggregate_limit_includes_heartbeat_bytes(self):
        self.assert_oversized_stream_rejected(b": heartbeat\n" * 10000)

    def test_invalid_submission_shape_does_not_poll_or_resubmit(self):
        for submission in ([], {"event_id": 42}, {"event_id": "z" * 32}):
            with self.subTest(submission=submission):
                opener = FakeOpener(b"", json.dumps(submission).encode())
                with patch("urllib.request.build_opener", return_value=opener):
                    with self.assertRaisesRegex(RuntimeError, "Unexpected"):
                        request_model("synthetic")
                self.assertEqual(len(opener.calls), 1)


if __name__ == "__main__":
    unittest.main()
