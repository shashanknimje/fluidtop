"""FluidTop UI appearance, independent of the chart/accent theme."""

from textual.theme import Theme

LIGHT_THEME_NAME = "fluidtop-white"
DARK_THEME_NAME = "textual-dark"

# Textual's built-in light theme has gray surfaces. Explicit white
# surfaces also give textual-plotext a white plot canvas and dark axes.
PURE_WHITE_THEME = Theme(
    name=LIGHT_THEME_NAME,
    primary="#0f766e",
    secondary="#0891b2",
    accent="#0891b2",
    foreground="#000000",
    background="#ffffff",
    surface="#ffffff",
    panel="#ffffff",
    dark=False,
    text_alpha=1.0,
    variables={
        "text": "#000000",
        "text-muted": "#374151",
    },
)
