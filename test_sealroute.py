import base64
import dataclasses
import unittest
from cryptography.exceptions import InvalidTag
from sealroute import Session, build_prompt, canonical


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.body = "FICTIONAL-ONLY: 김샘플 👩🏽‍💻\r\nAccount 73291; never send this detail."
        self.envelope = self.session.seal(self.body, "I forgot my password and cannot sign in")

    def test_exact_unicode_roundtrip(self):
        self.assertEqual(self.session.open_for_local_review(self.envelope), self.body)

    def test_outbound_excludes_private_material(self):
        wire = build_prompt(self.envelope)
        for private in (self.body, "73291", "김샘플", self.session._key.hex(),
                        base64.b64encode(self.session._key).decode()):
            self.assertNotIn(private, wire)
        self.assertIn(self.envelope.ciphertext, wire)
        self.assertEqual(set(self.envelope.outbound()),
                         {"version", "id", "public_intent", "queues", "nonce", "ciphertext"})

    def test_ciphertext_nonce_and_metadata_tampering(self):
        ciphertext = bytearray(base64.b64decode(self.envelope.ciphertext))
        ciphertext[0] ^= 1
        variants = [dataclasses.replace(self.envelope, ciphertext=base64.b64encode(ciphertext).decode()),
                    dataclasses.replace(self.envelope, nonce=base64.b64encode(bytes(12)).decode()),
                    dataclasses.replace(self.envelope, public_intent="tampered"),
                    dataclasses.replace(self.envelope, queues=("ACCESS",)),
                    dataclasses.replace(self.envelope, id="other")]
        for variant in variants:
            with self.subTest(variant=variant):
                with self.assertRaises(InvalidTag):
                    self.session.open_for_local_review(variant)
                with self.assertRaises(ValueError):
                    self.session.validate_proposal(variant, "ACCESS")

    def test_wrong_session_key(self):
        with self.assertRaises(InvalidTag):
            Session().open_for_local_review(self.envelope)

    def test_model_response_is_untrusted(self):
        cases = ["ACCESS; rm -rf /", "```ACCESS```", "{\"queue\":\"ACCESS\"}",
                 "I choose ACCESS", "ACCESS\nBILLING", "ADMIN", "ＡＣＣＥＳＳ", "", None]
        for response in cases:
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.session.validate_proposal(self.envelope, response)

    def test_allowlist_is_per_envelope(self):
        narrow = self.session.seal("fictional", "refund question", ("BILLING",))
        with self.assertRaises(ValueError):
            self.session.validate_proposal(narrow, "ACCESS")

    def test_operator_gate_and_single_session_consumption(self):
        with self.assertRaises(ValueError):
            self.session.commit_local_review(self.envelope, "ACCESS")
        outcome = self.session.commit_local_review(self.envelope, "ACCESS", approved=True)
        self.assertEqual(outcome["body"], self.body)
        self.assertEqual(outcome["action"], "LOCAL_REVIEW_ONLY_NO_DELIVERY")
        with self.assertRaises(ValueError):
            self.session.commit_local_review(self.envelope, "ACCESS", approved=True)

    def test_distinct_nonce_and_ciphertext(self):
        another = self.session.seal(self.body, self.envelope.public_intent)
        self.assertNotEqual(another.nonce, self.envelope.nonce)
        self.assertNotEqual(another.ciphertext, self.envelope.ciphertext)

    def test_bounds_and_terminal_escape(self):
        cases = [("", "ok"), ("x" * 4097, "ok"), ("valid", ""),
                 ("valid", "x" * 241), ("valid", "\x1b[31m")]
        for body, intent in cases:
            with self.subTest(body_length=len(body), intent=intent), self.assertRaises(ValueError):
                self.session.seal(body, intent)

    def test_allowlisted_is_not_semantic_correctness(self):
        # A wrong but authorized suggestion still needs a human decision.
        self.assertEqual(self.session.validate_proposal(self.envelope, "BILLING"), "BILLING")


if __name__ == "__main__":
    unittest.main()
