import io
import json
import unittest
from unittest.mock import patch
from hosted import request_model


class FakeOpener:
    def __init__(self, terminal):
        self.calls = []
        self.terminal = terminal

    def open(self, request, **kwargs):
        self.calls.append(request)
        if len(self.calls) == 1:
            return io.BytesIO(json.dumps({"event_id": "a" * 32}).encode())
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


if __name__ == "__main__":
    unittest.main()
