import base64
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import flop_agent


class ProtocolTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(flop_agent.normalize_text("a\nb"), "a b")

    def test_did_roundtrip(self):
        key = Ed25519PrivateKey.generate()
        did = flop_agent.did_from_private_key(key)
        self.assertEqual(len(did), 56)
        pub = flop_agent.public_key_from_did(did)
        msg = b"hello"
        sig = key.sign(msg)
        pub.verify(sig, msg)

    def test_signing_payload(self):
        key = Ed25519PrivateKey.generate()
        did = flop_agent.did_from_private_key(key)
        text, sig = flop_agent.sign_message(key, "lobby", 123, "hello")
        flop_agent.public_key_from_did(did).verify(
            base64.urlsafe_b64decode(sig + "=="),
            f"lobby|123|{text}".encode(),
        )

    def test_evidence_shape_can_verify(self):
        key = Ed25519PrivateKey.generate()
        did = flop_agent.did_from_private_key(key)
        statement = {"did": did, "records": [], "format": "test"}
        canonical = json.dumps(statement, sort_keys=True, separators=(",", ":")).encode()
        sig = key.sign(canonical)
        flop_agent.public_key_from_did(did).verify(sig, canonical)

    def test_parse_text_response(self):
        did = "did:key:z6Mk11111111111111111111111111111111111111111111ABCD"
        text = "hello legacy"
        response = "[12345] 2026-08-27T19:20:10.000000Z <z6Mk…ABCD> hello legacy"
        msg = flop_agent._message_from_text_response(response, did, 99, text)
        self.assertEqual(msg["seq"], 12345)
        self.assertEqual(msg["nonce"], "99")

    def test_legacy_signed_message_is_verified(self):
        did = "did:key:z6Mk11111111111111111111111111111111111111111111ABCD"
        row = {
            "kind": "signed_message",
            "data": {
                "room": "lobby",
                "did": did,
                "nonce": 99,
                "text": "hello legacy",
                "response": "[12345] 2026-08-27T19:20:10.000000Z <z6Mk…ABCD> hello legacy",
            },
        }
        fixed = flop_agent._enrich_legacy_receipt(row)
        self.assertTrue(fixed["data"]["verified"])
        self.assertEqual(fixed["data"]["seq"], 12345)

    def test_legacy_contribution_is_recognized(self):
        did = "did:key:z6Mk11111111111111111111111111111111111111111111ABCD"
        text = "I published a Technocore contribution: https://example.com. useful."
        row = {
            "kind": "signed_message",
            "data": {
                "room": "technocore",
                "did": did,
                "nonce": 100,
                "text": text,
                "response": f"[777] 2026-08-27T19:34:43.000000Z <z6Mk…ABCD> {text}",
            },
        }
        fixed = flop_agent._enrich_legacy_receipt(row)
        self.assertEqual(fixed["kind"], "contribution")
        self.assertTrue(fixed["data"]["verified"])
        self.assertEqual(fixed["data"]["seq"], 777)

    def test_legacy_publish_did_is_verified(self):
        did = "did:key:z6Mk11111111111111111111111111111111111111111111ABCD"
        row = {
            "kind": "publish_did",
            "data": {"did": did, "verify": f"prefix\n{did}\n"},
        }
        fixed = flop_agent._enrich_legacy_receipt(row)
        self.assertTrue(fixed["data"]["verified"])


if __name__ == "__main__":
    unittest.main()
