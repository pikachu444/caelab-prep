"""Original CAELab visual assets, shared by the gallery and consuming apps."""

from .appearance import STYLESHEET, icon

TOKENS = {
    "surface": "#ffffff", "workspace": "#e7ebef", "text": "#25313d",
    "muted": "#677582", "border": "#cbd4dd", "accent": "#217a90",
    "selection": "#dcecf9", "error": "#b23838", "spacing": (2, 4, 6, 10, 16),
    "row_height": 25, "icon_size": 20,
}

__all__ = ["STYLESHEET", "TOKENS", "icon"]
