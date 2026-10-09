"""Tests for the optional sudo-safe shell launcher."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "fluidtop-launch"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mock_bin = self.root / "bin"
        self.mock_bin.mkdir()
        self.log_file = self.root / "sudo-args.txt"
        self.fluidtop_bin = self.root / "fake fluidtop"
        self.fluidtop_bin.write_text("#!/bin/sh\nprintf 'FluidTop help\\n'\n", encoding="utf-8")
        self.fluidtop_bin.chmod(0o755)
        self.mock_sudo = self.mock_bin / "sudo"
        self.mock_sudo.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$MOCK_SUDO_LOG\"\n"
            "exit \"$MOCK_SUDO_EXIT_CODE\"\n", encoding="utf-8"
        )
        self.mock_sudo.chmod(0o755)
        self.env = dict(os.environ)
        self.env.update(
            PATH=str(self.mock_bin) + os.pathsep + os.environ.get("PATH", ""),
            FLUIDTOP_BIN=str(self.fluidtop_bin),
            MOCK_SUDO_LOG=str(self.log_file),
            MOCK_SUDO_EXIT_CODE="0",
        )

    def launch(self, *args, env=None):
        return subprocess.run(
            ["/bin/sh", str(LAUNCHER), *args],
            env=self.env if env is None else env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_default_light_mode_and_safe_env(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.log_file.read_text(encoding="utf-8").splitlines(),
            [
                "-H",
                "/usr/bin/env",
                "PYTHONDONTWRITEBYTECODE=1",
                str(self.fluidtop_bin),
                "--mode",
                "light",
            ],
        )

    def test_explicit_dark_mode_and_arguments_not_modified(self):
        arguments = ["--mode=dark", "--theme", "cyan", "--interval", "2"]
        result = self.launch(*arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = self.log_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(captured[4:], arguments)

    def test_explicit_mode_as_separate_argument(self):
        arguments = ["--mode", "dark"]
        result = self.launch(*arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.log_file.read_text(encoding="utf-8").splitlines()[4:],
            arguments,
        )

    def test_help_without_elevating(self):
        result = self.launch("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FluidTop help", result.stdout)
        self.assertFalse(self.log_file.exists())

    def test_missing_binary_produces_clear_error(self):
        env = dict(self.env, FLUIDTOP_BIN=str(self.root / "missing"))
        result = self.launch(env=env)
        self.assertEqual(result.returncode, 127)
        self.assertIn("executable not found", result.stderr)
        self.assertFalse(self.log_file.exists())

    def test_sudo_exit_status_is_propagated(self):
        env = dict(self.env, MOCK_SUDO_EXIT_CODE="42")
        result = self.launch(env=env)
        self.assertEqual(result.returncode, 42)


if __name__ == "__main__":
    unittest.main()
