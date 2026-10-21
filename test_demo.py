"""CLI-flow checks with actual session crypto and a stubbed hosted response.

No real inference or external transmission. Generated fictional report files
are retained in a temporary directory for inspection, never user directories.
"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import demo
from sealroute import Session


class DemoBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='sealroute-cli-test-'))
        self.report_dir = self.root / 'report'
        self.sessions = []
        sessions = self.sessions

        class ObservedSession(Session):
            def __init__(self):
                super().__init__()
                self.decryptions = 0
                sessions.append(self)

            def open_for_local_review(self, envelope):
                self.decryptions += 1
                return super().open_for_local_review(envelope)

        self.observed_session = ObservedSession

    def run_demo(self, *, live=False, interactive=False, approval='', response='ACCESS',
                 api_error=False, terminal_error=False):
        def fake_request(prompt, *, on_submitted):
            self.assertNotIn(demo.FIXTURES['access'][0], prompt)
            on_submitted('a' * 32)
            if api_error:
                raise TimeoutError('Synthetic polling uncertainty')
            if terminal_error:
                return {'event_id': 'a' * 32, 'terminal': 'error', 'sse': []}
            return {'event_id': 'a' * 32, 'terminal': 'complete', 'response': response}

        argv = ['demo.py', '--fixture', 'access', '--report-dir', str(self.report_dir)]
        if live:
            argv.append('--live')
        output = io.StringIO()
        with patch('sys.argv', argv), patch('demo.Session', self.observed_session), \
                patch('demo.sys.stdin.isatty', return_value=interactive), \
                patch('builtins.input', return_value=approval) as ask, \
                patch('demo.request_model', side_effect=fake_request) as request, \
                patch('urllib.request.build_opener', side_effect=AssertionError('Unexpected network')), \
                contextlib.redirect_stdout(output):
            code = demo.main()
        reports = {p.name: json.loads(p.read_text()) for p in self.report_dir.glob('*.json')}
        self.assert_private_not_exported(reports)
        return code, output.getvalue(), reports, request.call_count, ask.call_count

    def assert_private_not_exported(self, reports):
        serialized = json.dumps(reports, ensure_ascii=False)
        for private in (demo.FIXTURES['access'][0], 'XZ-73291', 'mina@example.invalid'):
            self.assertNotIn(private, serialized)
        for session in self.sessions:
            self.assertNotIn(session._key.hex(), serialized)
        for report in reports.values():
            self.assertNotIn('body', report)
            self.assertNotIn('key', report)

    def test_noninteractive_fixture_never_decrypts_or_calls_host(self):
        code, output, reports, calls, asks = self.run_demo()
        self.assertEqual((code, calls, asks), (0, 0, 0))
        self.assertEqual(reports['result.json']['terminal'], 'offline_fixture')
        self.assertEqual(reports['review.json']['state'], 'AWAITING_OPERATOR_REVIEW')
        self.assertEqual(self.sessions[0].decryptions, 0)
        self.assertNotIn(demo.FIXTURES['access'][0], output)

    def test_operator_cancel_keeps_body_sealed(self):
        code, output, reports, calls, asks = self.run_demo(interactive=True)
        self.assertEqual((code, calls, asks), (0, 0, 1))
        self.assertEqual(reports['review.json']['state'], 'OPERATOR_CANCELLED')
        self.assertEqual(self.sessions[0].decryptions, 0)
        self.assertNotIn(demo.FIXTURES['access'][0], output)

    def test_matching_approval_decrypts_once_only_to_terminal(self):
        code, output, reports, calls, asks = self.run_demo(interactive=True, approval='ACCESS')
        self.assertEqual((code, calls, asks), (0, 0, 1))
        self.assertEqual(reports['review.json']['state'], 'LOCAL_SYNTHETIC_REVIEW_COMPLETED')
        self.assertFalse(reports['review.json']['local_delivery'])
        self.assertEqual(self.sessions[0].decryptions, 1)
        self.assertEqual(len(self.sessions[0]._consumed), 1)
        self.assertIn(demo.FIXTURES['access'][0], output)

    def test_untrusted_model_text_is_rejected_before_prompt_or_decryption(self):
        code, output, reports, calls, asks = self.run_demo(
            live=True, interactive=True, approval='ACCESS', response='ACCESS; run a command')
        self.assertEqual((code, calls, asks), (3, 1, 0))
        self.assertEqual(reports['review.json']['state'], 'REJECTED_INVALID_PROPOSAL')
        self.assertEqual(self.sessions[0].decryptions, 0)
        self.assertNotIn(demo.FIXTURES['access'][0], output)

    def test_wrong_but_allowed_suggestion_can_be_cancelled(self):
        code, output, reports, calls, asks = self.run_demo(
            live=True, interactive=True, approval='', response='BILLING')
        self.assertEqual((code, calls, asks), (0, 1, 1))
        self.assertEqual(reports['review.json']['state'], 'OPERATOR_CANCELLED')
        self.assertIn('Correct fixture label: ACCESS', output)
        self.assertEqual(self.sessions[0].decryptions, 0)

    def test_known_terminal_error_never_asks_or_decrypts(self):
        code, _, reports, calls, asks = self.run_demo(live=True, interactive=True, terminal_error=True)
        self.assertEqual((code, calls, asks), (2, 1, 0))
        self.assertNotIn('review.json', reports)
        self.assertEqual(self.sessions[0].decryptions, 0)

    def test_uncertain_poll_preserves_event_without_resubmitting(self):
        code, _, reports, calls, asks = self.run_demo(live=True, interactive=True, api_error=True)
        self.assertEqual((code, calls, asks), (2, 1, 0))
        self.assertEqual(reports['submitted.json']['event_id'], 'a' * 32)
        self.assertEqual(reports['unresolved.json']['error_type'], 'TimeoutError')
        self.assertNotIn('result.json', reports)
        self.assertNotIn('review.json', reports)
        self.assertEqual(self.sessions[0].decryptions, 0)

    def test_existing_report_directory_fails_before_any_host_request(self):
        self.report_dir.mkdir()
        marker = self.report_dir / 'intent.json'
        marker.write_text('{"preserved": true}')
        with patch('sys.argv', ['demo.py', '--live', '--report-dir', str(self.report_dir)]), \
                patch('demo.request_model') as request:
            with self.assertRaises(FileExistsError):
                demo.main()
        request.assert_not_called()
        self.assertEqual(marker.read_text(), '{"preserved": true}')


if __name__ == '__main__':
    unittest.main()
