"""Live appearance transitions without starting privileged powermetrics."""

import unittest
from unittest.mock import patch

from fluidtop.appearance import DARK_THEME_NAME, LIGHT_THEME_NAME
from fluidtop.fluidtop import FluidTopApp


class NoSensorsApp(FluidTopApp):
    """Exercise theme changes with Textual's headless pilot."""

    async def on_mount(self) -> None:
        pass


class AutoAppearanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_follow_mac_and_allow_temporary_manual_override(self):
        appearance = {"value": "light"}
        with patch("fluidtop.fluidtop.get_soc_info", return_value={}):
            app = NoSensorsApp(1, "cyan", 30, 0, mode="auto")

        with patch("fluidtop.fluidtop.read_system_appearance", side_effect=lambda: appearance["value"]):
            async with app.run_test(size=(120, 40)) as pilot:
                # A real poll changes Textual's theme without restarting FluidTop.
                await app._sync_system_appearance()
                self.assertEqual(app.theme, LIGHT_THEME_NAME)

                await pilot.press("d")
                self.assertEqual(app.theme, DARK_THEME_NAME)
                # Manual override survives polls until macOS actually changes.
                await app._sync_system_appearance()
                self.assertEqual(app.theme, DARK_THEME_NAME)

                await pilot.press("a")
                self.assertEqual(app.theme, LIGHT_THEME_NAME)

                appearance["value"] = "dark"
                await app._sync_system_appearance()
                self.assertEqual(app.theme, DARK_THEME_NAME)
                appearance["value"] = "light"
                await app._sync_system_appearance()
                self.assertEqual(app.theme, LIGHT_THEME_NAME)

    async def test_failed_probe_keeps_current_appearance(self):
        with patch("fluidtop.fluidtop.get_soc_info", return_value={}):
            app = NoSensorsApp(1, "cyan", 30, 0, mode="auto")
        with patch("fluidtop.fluidtop.read_system_appearance", return_value=None):
            async with app.run_test(size=(120, 40)):
                await app._sync_system_appearance()
                self.assertEqual(app.theme, DARK_THEME_NAME)

    async def test_explicit_mode_never_reads_system(self):
        with patch("fluidtop.fluidtop.get_soc_info", return_value={}):
            app = NoSensorsApp(1, "cyan", 30, 0, mode="light")
        with patch("fluidtop.fluidtop.read_system_appearance") as probe:
            async with app.run_test(size=(120, 40)):
                await app._sync_system_appearance()
                self.assertEqual(app.theme, LIGHT_THEME_NAME)
                probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
