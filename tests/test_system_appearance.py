"""macOS appearance detection tests using fake defaults outputs."""

import plistlib
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fluidtop.system_appearance import read_system_appearance


def prefs(**kwargs):
    return plistlib.dumps(kwargs)


class SystemAppearanceTests(unittest.TestCase):
    def setUp(self):
        self.platform = patch("fluidtop.system_appearance.sys.platform", "darwin")
        self.euid = patch("fluidtop.system_appearance.os.geteuid", return_value=501)
        self.platform.start()
        self.euid.start()
        self.addCleanup(self.platform.stop)
        self.addCleanup(self.euid.stop)

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_light_when_style_absent(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, prefs(AppleInterfaceStyleSwitchesAutomatically=True), b"")
        self.assertEqual(read_system_appearance(), "light")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/defaults", "export", "-g", "-"])

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_dark_when_style_is_dark(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, prefs(AppleInterfaceStyle="Dark"), b"")
        self.assertEqual(read_system_appearance(), "dark")

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_root_reads_invoking_user_preferences(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, prefs(AppleInterfaceStyle="Dark"), b"")
        with patch("fluidtop.system_appearance.os.geteuid", return_value=0), \
                patch.dict("fluidtop.system_appearance.os.environ", {"SUDO_UID": "501"}), \
                patch("fluidtop.system_appearance.pwd.getpwuid", return_value=SimpleNamespace(pw_name="shashank")):
            self.assertEqual(read_system_appearance(), "dark")
        self.assertEqual(run.call_args.args[0], [
            "/usr/bin/sudo", "-n", "-H", "-u", "shashank",
            "/usr/bin/defaults", "export", "-g", "-",
        ])

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_no_user_in_root_context_fails_closed(self, run):
        with patch("fluidtop.system_appearance.os.geteuid", return_value=0), \
                patch.dict("fluidtop.system_appearance.os.environ", {}, clear=True):
            self.assertIsNone(read_system_appearance())
        run.assert_not_called()

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_command_failure_does_not_mean_light(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, b"", b"access denied")
        self.assertIsNone(read_system_appearance())

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_malformed_preferences_do_not_change_mode(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, b"not XML", b"")
        self.assertIsNone(read_system_appearance())

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_timeout_does_not_change_mode(self, run):
        run.side_effect = subprocess.TimeoutExpired(["defaults"], 3)
        self.assertIsNone(read_system_appearance())

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_unknown_theme_does_not_change_mode(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, prefs(AppleInterfaceStyle="Other"), b"")
        self.assertIsNone(read_system_appearance())

    @patch("fluidtop.system_appearance.subprocess.run")
    def test_non_macos_does_not_call_defaults(self, run):
        with patch("fluidtop.system_appearance.sys.platform", "linux"):
            self.assertIsNone(read_system_appearance())
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
