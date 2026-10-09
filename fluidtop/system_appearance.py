"""Read the active macOS user's appearance without a GUI dependency.

FluidTop's UV launcher runs with sudo -H, so reading preferences as root
would consult the wrong account. Use SUDO_UID to inspect the invoking user's
global preferences instead. Export as a plist because the AppleInterfaceStyle
key is absent in light mode (which makes defaults read with a key fail).
"""

import os
import plistlib
import pwd
import subprocess
import sys
from typing import Literal

Appearance = Literal["light", "dark"]


def read_system_appearance() -> Appearance | None:
    """Return the active macOS appearance, or None if it cannot be read.

    A failed read must never be interpreted as light mode. The caller should
    retain the current UI theme until a later successful poll.
    """
    if sys.platform != "darwin":
        return None

    command = ["/usr/bin/defaults", "export", "-g", "-"]
    if os.geteuid() == 0:
        # No GUI-user identity: querying root preferences would be misleading.
        try:
            uid = int(os.environ["SUDO_UID"])
            if uid <= 0:
                return None
            username = pwd.getpwuid(uid).pw_name
        except (KeyError, ValueError, OverflowError):
            return None
        command = ["/usr/bin/sudo", "-n", "-H", "-u", username, *command]

    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=3, check=False,
        )
        if result.returncode != 0:
            return None
        preferences = plistlib.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, plistlib.InvalidFileException,
            ValueError, TypeError):
        return None

    if not isinstance(preferences, dict):
        return None
    style = preferences.get("AppleInterfaceStyle", "Light")
    if style == "Dark":
        return "dark"
    if style == "Light":
        return "light"
    return None
