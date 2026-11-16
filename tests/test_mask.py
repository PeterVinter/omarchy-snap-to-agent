import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import mask  # noqa: E402

# Every value below is invented. None of them is a working credential.
SAMPLE = """\
$ export AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP
$ curl -H "Authorization: Bearer abcdefghijklmnop1234567890" https://example.test
GITHUB_TOKEN=ghp_0123456789abcdefghijklmnopqrstuvwxyzAB
token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop
DATABASE_URL=postgres://admin:hunter22pass@db.example.test/app
password = "correct-horse-battery"
ANTHROPIC_API_KEY=sk-ant-api03-FAKEFAKEFAKEFAKEFAKEFAKE
-----BEGIN RSA PRIVATE KEY-----
MIIFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE
-----END RSA PRIVATE KEY-----
normal line: ls -la /home/peter
"""


class MaskTests(unittest.TestCase):
    def setUp(self):
        self.result = mask.mask(SAMPLE)
        self.text = self.result["text"]
        self.kinds = {f["kind"] for f in self.result["findings"]}

    def test_known_secrets_are_gone(self):
        for secret in ["AKIAABCDEFGHIJKLMNOP", "abcdefghijklmnop1234567890",
                       "ghp_0123456789abcdefghijklmnopqrstuvwxyzAB", "hunter22pass",
                       "correct-horse-battery", "sk-ant-api03-FAKEFAKEFAKEFAKEFAKEFAKE",
                       "MIIFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE", "eyJhbGciOiJIUzI1NiJ9"]:
            self.assertNotIn(secret, self.text, secret)

    def test_expected_kinds(self):
        for kind in ["aws-key", "bearer-token", "github-token", "jwt", "url-credentials",
                     "assignment", "anthropic-key", "private-key"]:
            self.assertIn(kind, self.kinds, kind)

    def test_normal_text_is_untouched(self):
        self.assertIn("normal line: ls -la /home/peter", self.text)
        self.assertIn("curl -H", self.text)
        self.assertIn("postgres://admin:", self.text)  # user name stays, only the password goes

    def test_private_key_is_one_finding(self):
        keys = [f for f in self.result["findings"] if f["kind"] == "private-key"]
        self.assertEqual(len(keys), 1)
        self.assertIn("END RSA PRIVATE KEY", keys[0]["original"])

    def test_undo_restores_one_secret(self):
        first = self.result["findings"][0]
        restored = mask.unmask(self.text, self.result["findings"], first["id"])
        self.assertIn(first["original"], restored)
        self.assertNotIn(first["placeholder"], restored)
        self.assertEqual(restored.count("[MASKED:"), len(self.result["findings"]) - 1)

    def test_clean_text_and_empty_input(self):
        self.assertEqual(mask.mask("just words and a path /usr/bin")["findings"], [])
        self.assertEqual(mask.mask("")["text"], "")
        self.assertEqual(mask.mask(None)["text"], "")
        self.assertFalse(mask.has_secrets("password reset page"))

    def test_allow_leaves_one_secret_unmasked(self):
        first = self.result["findings"][0]
        out = mask.mask(SAMPLE, allow=[first["id"]])
        self.assertIn(first["original"], out["text"])
        self.assertFalse(out["findings"][0]["masked"])
        self.assertTrue(all(f["masked"] for f in out["findings"][1:]))
        self.assertEqual([f["id"] for f in out["findings"]], [f["id"] for f in self.result["findings"]])

    def test_ids_count_from_one_and_from_start(self):
        ids = [f["id"] for f in self.result["findings"]]
        self.assertEqual(ids, list(range(1, len(ids) + 1)))
        text = "a password=hunter22pass and token=abcdef123456 here"
        later = mask.mask(text, start=5)
        self.assertEqual([f["id"] for f in later["findings"]], [5, 6])
        self.assertIn("[MASKED:assignment:5]", later["text"])

    def test_masking_twice_changes_nothing(self):
        again = mask.mask(self.text)
        self.assertEqual(again["text"], self.text)
        self.assertEqual(again["findings"], [])


if __name__ == "__main__":
    unittest.main()
