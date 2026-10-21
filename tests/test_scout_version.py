"""The version check: the root it confirms, the line it prints per host, and the silence when it can't know."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scout_version", ROOT / "scripts" / "scout_version.py")
VERSION = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VERSION)


class VersionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="scout-version-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.plugin = self.base / "scout"
        (self.plugin / ".claude-plugin").mkdir(parents=True)
        self.manifest("2.4.0")
        for patcher in (mock.patch.object(VERSION, "cache_file", return_value=self.base / "cache" / "latest.json"),
                        mock.patch.dict(os.environ, {}, clear=False)):
            patcher.start()
            self.addCleanup(patcher.stop)
        os.environ.pop("SCOUT_NO_UPDATE_CHECK", None)

    def manifest(self, version, name="sf-demo-scout"):
        (self.plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name, "version": version}))

    def test_the_root_check_confirms_a_scout_install(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(VERSION.main(["--root"]), 0)
        self.assertTrue(output.getvalue().startswith("SCOUT_ROOT %s VERSION " % ROOT))
        copy = self.base / "elsewhere" / "scripts"
        copy.mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "scout_version.py", copy)
        other = importlib.util.spec_from_file_location("version_copy", copy / "scout_version.py")
        module = importlib.util.module_from_spec(other)
        other.loader.exec_module(module)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(module.main(["--root"]), 2)
        self.assertIn("SCOUT_ROOT_INVALID", output.getvalue())

    def test_a_newer_release_gets_one_line_with_this_hosts_way_to_update(self):
        with mock.patch.object(VERSION, "fetch", return_value="2.5.0"):
            for host, words in (("claude", "`claude plugin update sf-demo-scout@scout`"), ("codex", "Restart Codex"),
                                ("cursor", "its own marketplace"), ("unknown", "the way you installed it")):
                with self.subTest(host=host):
                    line = VERSION.update_line(host, self.plugin, now=1000.0)
                    self.assertTrue(line.startswith("SCOUT_UPDATE Scout 2.4.0 is installed; 2.5.0 is out."), line)
                    self.assertIn(words, line)
        (self.plugin / ".git").mkdir()  # the clone route: the update is a pull, on a yes
        with mock.patch.object(VERSION, "fetch", return_value="2.5.0"):
            self.assertIn('git -C "%s" pull --ff-only' % self.plugin, VERSION.update_line("cursor", self.plugin, 1000.0))

    def test_silence_when_current_unknown_older_or_switched_off(self):
        for fetched in ("2.4.0", "2.3.9", None):
            with self.subTest(fetched=fetched), mock.patch.object(VERSION, "fetch", return_value=fetched):
                VERSION.cache_file().unlink(missing_ok=True)
                self.assertIsNone(VERSION.update_line("claude", self.plugin, now=1000.0))
        self.manifest("2026.10.19-scout-2.3.2")  # a version Scout can't order says nothing
        with mock.patch.object(VERSION, "fetch", return_value="2.5.0") as fetch:
            self.assertIsNone(VERSION.update_line("claude", self.plugin, now=1000.0))
            fetch.assert_not_called()
        self.manifest("2.4.0")
        with mock.patch.dict(os.environ, {"SCOUT_NO_UPDATE_CHECK": "1"}), \
             mock.patch.object(VERSION, "fetch", return_value="2.5.0") as fetch:
            self.assertIsNone(VERSION.update_line("claude", self.plugin, now=1000.0))
            fetch.assert_not_called()

    def test_a_failed_attempt_also_waits_a_day(self):
        with mock.patch.object(VERSION, "fetch", return_value=None) as fetch:
            self.assertIsNone(VERSION.update_line("claude", self.plugin, now=1000.0))
            self.assertIsNone(VERSION.update_line("claude", self.plugin, now=2000.0))
            self.assertEqual(fetch.call_count, 1)

    def test_github_is_asked_at_most_once_a_day(self):
        with mock.patch.object(VERSION, "fetch", return_value="2.5.0") as fetch:
            VERSION.update_line("claude", self.plugin, now=1000.0)
            VERSION.update_line("claude", self.plugin, now=1000.0 + VERSION.DAY - 1)
            self.assertEqual(fetch.call_count, 1)
            VERSION.update_line("claude", self.plugin, now=1000.0 + VERSION.DAY + 1)
            self.assertEqual(fetch.call_count, 2)

    def test_an_offline_fetch_is_unknown_and_never_raises(self):
        with mock.patch.object(VERSION.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertIsNone(VERSION.fetch())
            self.assertIsNone(VERSION.update_line("codex", self.plugin, now=1000.0))

    def test_a_disk_that_fills_mid_write_keeps_the_last_known_release(self):
        # Writing the cache in place truncated it first, so a full disk left the next run without the
        # release it knew. The write goes to a file beside the cache and replaces it only once it's complete. Any write
        # fails halfway here, wherever it happens, so the old in-place write fails this test too.
        cache = VERSION.cache_file()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"version": "2.5.0", "checked": 1000.0}))
        real_open = io.open

        class Full:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                self.stream.close()
            def write(self, text):
                self.stream.write(text[: len(text) // 2])  # part of it lands, then the disk is full
                self.stream.flush()
                raise OSError(28, "No space left on device")

        def opening(file, mode="r", *args, **kwargs):
            stream = real_open(file, mode, *args, **kwargs)
            return Full(stream) if "w" in mode else stream

        later = 1000.0 + VERSION.DAY + 1
        with mock.patch.object(VERSION, "fetch", return_value=None), mock.patch("io.open", side_effect=opening):
            self.assertEqual(VERSION.latest(now=later), "2.5.0")
        self.assertEqual(json.loads(cache.read_text())["version"], "2.5.0")  # the old cache, untouched
        self.assertEqual([path.name for path in cache.parent.iterdir()], ["latest.json"])  # no temporary file left
        with mock.patch.object(VERSION, "fetch", return_value=None):  # and the next offline run still knows it
            self.assertEqual(VERSION.latest(now=later + 60), "2.5.0")

    def test_a_failed_attempt_keeps_the_newer_release_it_already_knew(self):
        # Offline, a proxy's sign-in page or a manifest without a strict version: the attempt counts for the day, and
        # the release the last good answer named is still announced.
        with mock.patch.object(VERSION, "fetch", return_value="2.5.0"):
            self.assertIn("2.5.0 is out", VERSION.update_line("claude", self.plugin, now=1000.0))
        later = 1000.0 + VERSION.DAY + 1
        for name, answer in (("offline", OSError("offline")), ("sign-in page", b"<html>Sign in to continue</html>"),
                             ("no strict version", b'{"version": "2.6"}'), ("not a manifest", b'["2.6.0"]')):
            with self.subTest(answer=name):
                VERSION.cache_file().write_text(json.dumps({"version": "2.5.0", "checked": 1000.0}))
                response = mock.MagicMock()
                response.__enter__.return_value.read.return_value = answer
                opened = (mock.patch.object(VERSION.urllib.request, "urlopen", side_effect=answer)
                          if isinstance(answer, Exception) else
                          mock.patch.object(VERSION.urllib.request, "urlopen", return_value=response))
                with opened as urlopen:
                    self.assertIn("2.5.0 is out", VERSION.update_line("claude", self.plugin, now=later))
                    self.assertIn("2.5.0 is out", VERSION.update_line("claude", self.plugin, now=later + 60))
                    self.assertEqual(urlopen.call_count, 1)  # still one attempt a day
                self.assertEqual(json.loads(VERSION.cache_file().read_text()), {"version": "2.5.0", "checked": later})

    def test_a_good_answer_replaces_the_kept_one_and_nothing_known_stays_unknown(self):
        VERSION.cache_file().parent.mkdir(parents=True)
        VERSION.cache_file().write_text(json.dumps({"version": "2.5.0", "checked": 1000.0}))
        with mock.patch.object(VERSION, "fetch", return_value="2.4.0"):  # a newer answer wins, even a lower version
            self.assertIsNone(VERSION.update_line("claude", self.plugin, now=1000.0 + VERSION.DAY + 1))
        self.assertEqual(json.loads(VERSION.cache_file().read_text())["version"], "2.4.0")
        for cached in ('{"version": null, "checked": 1000.0}', '{"version": "2.5", "checked": 1000.0}', '["2.5.0"]',
                       "not json"):
            with self.subTest(cached=cached), mock.patch.object(VERSION, "fetch", return_value=None):
                VERSION.cache_file().write_text(cached)
                self.assertIsNone(VERSION.latest(now=1000.0 + VERSION.DAY + 1))
                self.assertEqual(json.loads(VERSION.cache_file().read_text()),
                                 {"version": None, "checked": 1000.0 + VERSION.DAY + 1})


if __name__ == "__main__":
    unittest.main()
