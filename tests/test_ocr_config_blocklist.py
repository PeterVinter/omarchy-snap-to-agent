import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import blocklist  # noqa: E402
import config  # noqa: E402
import ocr  # noqa: E402


class ConfigTests(unittest.TestCase):
    def write(self, text):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "config.json")
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_defaults_when_file_is_missing_or_broken(self):
        self.assertEqual(config.load("/no/such/file")["retention_days"], 7)
        self.assertEqual(config.load(self.write("{ not json"))["ocr"], True)
        self.assertEqual(config.load(self.write("[1,2]"))["retention_days"], 7)

    def test_valid_values_win_and_wrong_types_are_ignored(self):
        cfg = config.load(self.write(json.dumps({"retention_days": 30, "ocr": False, "hook": "yes",
                                                 "image": {"max_edge": 1000, "max_bytes": "big"},
                                                 "unknown": 1})))
        self.assertEqual(cfg["retention_days"], 30)
        self.assertFalse(cfg["ocr"])
        self.assertFalse(cfg["hook"])
        self.assertEqual(cfg["image"], {"max_edge": 1000, "max_bytes": 2_000_000})
        self.assertNotIn("unknown", cfg)

    def test_blocklist_lists_are_replaced_and_normalised(self):
        cfg = config.load(self.write(json.dumps({"blocklist": {"classes": ["  MyVault "], "titles": [5, "x"]}})))
        self.assertEqual(cfg["blocklist"]["classes"], ["myvault"])
        self.assertIn("incognito", cfg["blocklist"]["titles"])  # the bad titles list is ignored whole

    def test_region_tool_accepts_only_known_values(self):
        self.assertEqual(config.load(self.write(json.dumps({"region_tool": "slurp"})))["region_tool"], "slurp")
        self.assertEqual(config.load(self.write(json.dumps({"region_tool": "rm -rf"})))["region_tool"], "auto")
        self.assertEqual(config.load(self.write(json.dumps({"region_tool": 3})))["region_tool"], "auto")

    def test_questions_keep_only_strings(self):
        cfg = config.load(self.write(json.dumps({"questions": {"error": "Fix it", "window": 3}})))
        self.assertEqual(cfg["questions"], {"error": "Fix it"})


class BlocklistTests(unittest.TestCase):
    BL = config.DEFAULTS["blocklist"]

    def test_default_matches(self):
        self.assertEqual(blocklist.match({"class": "org.keepassxc.KeePassXC", "title": "x"}, self.BL), "class:keepassxc")
        self.assertEqual(blocklist.match({"class": "firefox", "title": "Mozilla Firefox Private Browsing"}, self.BL),
                         "title:private browsing")
        self.assertEqual(blocklist.match({"class": "chromium", "title": "Swedbank - Chromium"}, self.BL), "title:swedbank")
        self.assertEqual(blocklist.match({"class": "foot", "title": "~/Work"}, self.BL), "")
        self.assertEqual(blocklist.match(None, self.BL), "")

    def test_region_only_checks_windows_under_it(self):
        vault = {"class": "keepassxc", "title": "", "at": [0, 0], "size": [500, 500]}
        other = {"class": "foot", "title": "", "at": [600, 0], "size": [500, 500]}
        self.assertIsNotNone(blocklist.find_blocked([vault, other], self.BL, (100, 100, 50, 50)))
        self.assertIsNone(blocklist.find_blocked([vault, other], self.BL, (700, 100, 50, 50)))
        self.assertIsNotNone(blocklist.find_blocked([vault, other], self.BL, (450, 100, 300, 50)))  # straddles both

    def test_result_never_contains_the_title(self):
        w = {"class": "firefox", "title": "secret page - Incognito", "at": [0, 0], "size": [10, 10]}
        found = blocklist.find_blocked([w], self.BL)
        self.assertEqual(set(found), {"class", "reason"})
        self.assertNotIn("secret page", json.dumps(found))


@unittest.skipUnless(shutil.which("tesseract") and shutil.which("magick"), "tesseract and magick are needed")
class OcrTests(unittest.TestCase):
    def test_fake_key_in_an_image_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "key.png")
            subprocess.run(["magick", "-size", "900x120", "xc:white", "-fill", "black", "-pointsize", "26",
                            "-annotate", "+20+50", "GITHUB_TOKEN=ghp_0123456789abcdefghijklmnopqrstuvwxyzAB", img],
                           check=True, capture_output=True)
            result = ocr.read_text(img)
            self.assertTrue(result["ok"])
            self.assertIn("github-token", ocr.secret_kinds(result["text"]))

    def test_plain_image_has_no_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "plain.png")
            subprocess.run(["magick", "-size", "600x100", "xc:white", "-fill", "black", "-pointsize", "26",
                            "-annotate", "+20+50", "Hello world, build finished", img], check=True, capture_output=True)
            result = ocr.read_text(img)
            self.assertIn("Hello", result["text"])
            self.assertEqual(ocr.secret_kinds(result["text"]), [])


class OcrFallbackTests(unittest.TestCase):
    def test_missing_tesseract_is_reported_not_raised(self):
        r = ocr.read_text("/x.png", run=lambda argv, timeout=15, input=None: (127, "", ""))
        self.assertEqual((r["ok"], r["missing"], r["package"]), (False, True, "tesseract"))

    def test_failure_is_reported(self):
        r = ocr.read_text("/x.png", run=lambda argv, timeout=15, input=None: (1, "", "bad image"))
        self.assertFalse(r["ok"])
        self.assertFalse(r["missing"])

    def test_text_is_capped(self):
        r = ocr.read_text("/x.png", run=lambda argv, timeout=15, input=None: (0, "x" * 50000, ""))
        self.assertEqual(len(r["text"]), ocr.MAX_TEXT)


if __name__ == "__main__":
    unittest.main()
