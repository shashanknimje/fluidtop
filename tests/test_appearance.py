"""Theme and keyboard regression tests; no privileged sensors needed."""

import unittest
from unittest.mock import patch

from click.testing import CliRunner
from textual_plotext import PlotextPlot

from fluidtop.appearance import DARK_THEME_NAME, LIGHT_THEME_NAME, PURE_WHITE_THEME
from fluidtop.fluidtop import FluidTopApp, main


class NoSensorsApp(FluidTopApp):
    """Render FluidTop without starting powermetrics."""

    async def on_mount(self) -> None:
        pass


class ThemeConfigurationTests(unittest.TestCase):
    def test_pure_white_palette(self):
        variables = PURE_WHITE_THEME.to_color_system().generate()
        for key in ("background", "surface", "panel"):
            self.assertEqual(variables[key].lower(), "#ffffff")
        self.assertEqual(variables["foreground"].lower(), "#000000")
        self.assertEqual(variables["text"].lower(), "#000000")
        self.assertFalse(PURE_WHITE_THEME.dark)

    def test_cli_modes_and_accent_option(self):
        result = CliRunner().invoke(main, ["--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--mode [light|dark|auto]", result.output)
        self.assertIn("--theme", result.output)


class ThemeInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_white_ui_charts_and_d_toggle(self):
        with patch("fluidtop.fluidtop.get_soc_info", return_value={}):
            app = NoSensorsApp(1, "cyan", 30, 0, mode="light")

        async with app.run_test(size=(120, 40)) as pilot:
            self.assertEqual(app.theme, LIGHT_THEME_NAME)
            self.assertEqual(app.theme_variables["background"].lower(), "#ffffff")
            self.assertEqual(app.theme_variables["surface"].lower(), "#ffffff")
            self.assertEqual(app.theme_variables["foreground"].lower(), "#000000")

            charts = list(app.query(PlotextPlot))
            self.assertEqual(len(charts), 6)
            for chart in charts:
                self.assertEqual(chart.theme, "auto")
                self.assertEqual(chart.styles.background.hex.lower(), "#ffffff")

            await pilot.press("d")
            self.assertEqual(app.theme, DARK_THEME_NAME)
            await pilot.press("d")
            self.assertEqual(app.theme, LIGHT_THEME_NAME)


if __name__ == "__main__":
    unittest.main()
