import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import capture  # noqa: E402

WINDOW = {"address": "0x1", "at": [12, 38], "size": [1896, 1030], "class": "foot", "pid": 4242}


class Fake:
    """Stands in for runner.run. Records calls; grim writes a file of a chosen size."""

    def __init__(self, window=WINDOW, slurp=(0, "100,200 300x400\n"), grim_code=0, size=1000):
        self.calls, self.window, self.slurp, self.grim_code, self.size = [], window, slurp, grim_code, size

    def __call__(self, argv, timeout=15, input=None):
        self.calls.append(argv)
        cmd = argv[0]
        if cmd == "hyprctl":
            return 0, json.dumps(self.window if self.window is not None else {}), ""
        if cmd == "slurp":
            return self.slurp[0], self.slurp[1], ""
        if cmd == "grim":
            if self.grim_code == 0:
                with open(argv[-1], "wb") as f:
                    f.write(b"x" * self.size)
            return self.grim_code, "", "boom" if self.grim_code else ""
        if cmd == "magick" and argv[1] == "identify":
            return 0, "1920 1080", ""
        if cmd == "magick":
            path = argv[1]
            if argv[-3] == "-resize" and argv[-2] == "85%":
                os.truncate(path, int(os.path.getsize(path) * 0.85))
            return 0, "", ""
        return 127, "", ""


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SNAP_TO_AGENT_CACHE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("SNAP_TO_AGENT_CACHE", None)

    def test_geometry_parsing(self):
        self.assertEqual(capture.parse_geometry("10,20 300x400"), (10, 20, 300, 400))
        self.assertEqual(capture.parse_geometry("-1920,0 1920x1080"), (-1920, 0, 1920, 1080))
        for bad in ["", None, "10,20", "10,20 0x5", "1,2 3x4; rm -rf ~", "a,b cxd", "1,2 3x4 5"]:
            with self.assertRaises(capture.CaptureError, msg=repr(bad)):
                capture.parse_geometry(bad)

    def test_window_capture_uses_the_window_box(self):
        fake = Fake()
        result = capture.capture("window", run=fake)
        grim = [c for c in fake.calls if c[0] == "grim"][0]
        self.assertEqual(grim[1:3], ["-g", "12,38 1896x1030"])
        self.assertTrue(os.path.exists(result["path"]))
        self.assertTrue(result["path"].startswith(self.tmp.name))
        self.assertEqual(oct(os.stat(result["path"]).st_mode & 0o777), "0o600")
        self.assertEqual(result["window"]["class"], "foot")

    def test_region_with_explicit_geometry_skips_slurp(self):
        fake = Fake()
        capture.capture("region", "5,6 70x80", run=fake)
        self.assertFalse(any(c[0] == "slurp" for c in fake.calls))

    def test_region_selector_and_cancel(self):
        fake = Fake()
        capture.capture("region", run=fake)
        grim = [c for c in fake.calls if c[0] == "grim"][0]
        self.assertEqual(grim[2], "100,200 300x400")
        with self.assertRaises(capture.CaptureError) as cm:
            capture.capture("region", run=Fake(slurp=(1, "")))
        self.assertEqual(cm.exception.code, "cancelled")

    def test_errors_are_named(self):
        with self.assertRaises(capture.CaptureError) as cm:
            capture.capture("window", run=Fake(window=None))
        self.assertEqual(cm.exception.code, "no-window")
        with self.assertRaises(capture.CaptureError) as cm:
            capture.capture("window", run=Fake(grim_code=1))
        self.assertEqual(cm.exception.code, "capture-failed")
        with self.assertRaises(capture.CaptureError) as cm:
            capture.capture("full", run=Fake())
        self.assertEqual(cm.exception.code, "bad-mode")

    def test_large_images_are_shrunk_until_small_enough(self):
        result = capture.capture("window", run=Fake(size=5_000_000))
        self.assertLessEqual(result["bytes"], capture.MAX_BYTES)
        self.assertTrue(result["shrunk"])

    def test_shrinking_stops_instead_of_looping_forever(self):
        fake = Fake(size=500_000_000)
        result = capture.capture("window", run=fake)
        resizes = [c for c in fake.calls if c[0] == "magick" and c[-2] == "85%"]
        self.assertLessEqual(len(resizes), 8)
        self.assertTrue(result["bytes"] > 0)

    def test_small_images_get_one_resize_pass(self):
        fake = Fake(size=1000)
        capture.capture("window", run=fake)
        resizes = [c for c in fake.calls if c[0] == "magick" and "-resize" in c]
        self.assertEqual(len(resizes), 1)
        self.assertIn("1920x1920>", resizes[0])


if __name__ == "__main__":
    unittest.main()
