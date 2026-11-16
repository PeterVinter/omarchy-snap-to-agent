import json
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "helper"))


def catalog(code):
    with open(os.path.join(ROOT, "i18n", code + ".json"), encoding="utf-8") as f:
        return json.load(f)


def placeholders(text):
    """The %N holes of a string, or of every plural form of it."""
    if isinstance(text, dict):
        return sorted({h for form in text.values() for h in re.findall(r"%\d", form)})
    return sorted(re.findall(r"%\d", text))


class CatalogTests(unittest.TestCase):
    def test_every_language_has_exactly_the_english_keys(self):
        en = catalog("en")
        for name in sorted(os.listdir(os.path.join(ROOT, "i18n"))):
            code = name[:-5]
            other = catalog(code)
            self.assertEqual(sorted(set(en) - set(other)), [], "%s misses keys" % code)
            self.assertEqual(sorted(set(other) - set(en)), [], "%s has extra keys" % code)

    def test_placeholders_match_the_english_ones(self):
        en = catalog("en")
        for name in sorted(os.listdir(os.path.join(ROOT, "i18n"))):
            other = catalog(name[:-5])
            for key, text in en.items():
                self.assertEqual(placeholders(text), placeholders(other[key]), "%s in %s" % (key, name))

    def test_plural_entries_have_one_and_other(self):
        for name in os.listdir(os.path.join(ROOT, "i18n")):
            for key, text in catalog(name[:-5]).items():
                if isinstance(text, dict):
                    self.assertIn("other", text, "%s in %s" % (key, name))

    def test_no_empty_translations(self):
        for name in os.listdir(os.path.join(ROOT, "i18n")):
            for key, text in catalog(name[:-5]).items():
                forms = text.values() if isinstance(text, dict) else [text]
                for form in forms:
                    self.assertTrue(str(form).strip(), "%s empty in %s" % (key, name))


class UsageTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "Panel.qml"), encoding="utf-8") as f:
            self.qml = f.read()
        self.en = catalog("en")

    def test_every_literal_key_used_in_qml_exists(self):
        used = set(re.findall(r'strings\.tn?\(\s*"([A-Za-z0-9_.-]+)"\s*[,)]', self.qml))
        self.assertTrue(used)
        self.assertEqual(sorted(k for k in used if k not in self.en), [])

    def test_keys_built_from_a_prefix_exist_for_every_value(self):
        # strings.t("error." + code), ("note." + x), ("mode." + m), ("modeShort." + m), ("question.default." + m)
        helper = ""
        for name in ("capture.py", "launch.py", "snap.py", "sources.py"):
            with open(os.path.join(ROOT, "helper", name), encoding="utf-8") as f:
                helper += f.read()
        codes = set(re.findall(r'(?:CaptureError|LaunchError|Problem)\(\s*"([a-z-]+)"', helper))
        codes |= set(re.findall(r'"error": "([a-z-]+)"', helper))
        codes |= {"helper", "generic"}
        # Codes the panel never shows as its own message.
        codes -= {"usage", "declined", "no-hyprland-x"}
        missing = sorted(c for c in codes if "error." + c not in self.en)
        self.assertEqual(missing, [], "no text for these error codes")
        with open(os.path.join(ROOT, "helper", "compose.py"), encoding="utf-8") as f:
            compose_src = f.read()
        notes = set(re.findall(r'notes\.append\("([a-z_]+)"\)', compose_src))
        self.assertEqual(sorted(n for n in notes if "note." + n not in self.en), [])
        for mode in ("region", "window", "error", "notification", "clipboard"):
            for prefix in ("modeShort.", "question.default."):
                self.assertIn(prefix + mode, self.en)
        for problem in ("missing-file", "empty", "unreadable"):
            self.assertIn("defaults." + problem, self.en)

    def test_english_defaults_match_the_helper(self):
        import compose
        for mode, text in compose.DEFAULT_QUESTIONS.items():
            self.assertEqual(self.en["question.default." + mode], text)


if __name__ == "__main__":
    unittest.main()
