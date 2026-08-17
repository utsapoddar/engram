import json
import unittest

from engram.sanitize import sanitize_text
from tests.helpers import MemoryTestCase


class SanitizeTests(MemoryTestCase):
    def test_sanitize_rejects_secrets_and_chain_of_thought(self):
        with self.assertRaises(ValueError):
            sanitize_text("api_key=sk-abcdefghijklmnopqrstuvwxyz123456")
        clean = sanitize_text("Summary\n<chain-of-thought>private</chain-of-thought>\nVisible")
        self.assertNotIn("private", clean)
        self.assertIn("Visible", clean)

    def test_secret_detection_extended_formats_and_capture_refuses(self):
        secrets = [
            "sk-proj-" + "A" * 32, "ghp_" + "a" * 36, "AKIA" + "A" * 16,
            "xoxb-1234567890-abcdefghijklmnop", "AIza" + "A" * 35,
            "-----BEGIN PRIVATE KEY-----", "client_secret=supersecretvalue123",
        ]
        for secret in secrets:
            with self.assertRaises(ValueError, msg=secret[:8]):
                sanitize_text(secret)
        transcript = self.root / "secret.jsonl"
        transcript.write_text(json.dumps({"role":"assistant", "content": secrets[0]}))
        with self.assertRaises(ValueError):
            self.store.capture_session("codex", transcript)

    def test_authorization_jwt_and_oauth_secrets_are_rejected(self):
        secrets = [
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "Bearer opaqueOAuthTokenValue123456789",
            "eyJhbGciOiJIUzI1NiJ9."
            + "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            + "signatureABC123",
            "ya29." + "A" * 30,
            "access_token=oauth-access-value-12345",
            "refresh_token=oauth-refresh-value-12345",
        ]
        for secret in secrets:
            with self.assertRaises(ValueError, msg=secret[:20]):
                sanitize_text(secret)
        transcript = self.root / "oauth.jsonl"
        transcript.write_text(json.dumps({"role":"assistant", "content": secrets[0]}))
        with self.assertRaises(ValueError):
            self.store.capture_session("claude", transcript)


if __name__ == "__main__":
    unittest.main()
