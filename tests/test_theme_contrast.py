from pathlib import Path
import tomllib
import unittest
from dashboard.theme import CHART_COLORS


def luminance(colour):
    channels = [int(colour[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
    return sum(channel * weight for channel, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(foreground, background):
    light, dark = sorted([luminance(foreground), luminance(background)], reverse=True)
    return (light + .05) / (dark + .05)


class ThemeContrastTests(unittest.TestCase):
    def test_both_native_themes_have_readable_body_buttons_and_alerts(self):
        for classification in ("Direct", "Indirect"):
            self.assertGreaterEqual(contrast("#FFFFFF", CHART_COLORS[classification]), 4.5)
        path = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"
        theme = tomllib.loads(path.read_text(encoding="utf-8"))["theme"]
        for mode in ("light", "dark"):
            colours = theme[mode]
            pairs = [("body", colours["textColor"], colours["backgroundColor"]),
                     ("widgets", colours["textColor"], colours["secondaryBackgroundColor"]),
                     ("primary button", "#FFFFFF", colours["primaryColor"]),
                     ("table header", colours["textColor"], colours["dataframeHeaderBackgroundColor"]),
                     ("sidebar", colours["sidebar"]["textColor"], colours["sidebar"]["backgroundColor"])]
            pairs.extend((semantic, colours[f"{semantic}TextColor"], colours[f"{semantic}BackgroundColor"]) for semantic in ("yellow", "blue", "green", "red"))
            for label, foreground, background in pairs:
                with self.subTest(mode=mode, element=label):
                    self.assertGreaterEqual(contrast(foreground, background), 4.5)
