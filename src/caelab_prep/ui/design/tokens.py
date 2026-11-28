"""The shared visual values used by QSS, icons and engineering controls."""

_SPACING = (2, 4, 6, 10, 16)

TOKENS = {
    "surface": "#ffffff", "workspace": "#dbe1e7", "text": "#243343",
    "muted": "#536575", "border": "#b7c2cd", "accent": "#246a9c",
    "accent_hover": "#195780", "on_accent": "#ffffff",
    "selection": "#d9e9f6", "selection_text": "#143e61",
    "error": "#b23838", "error_surface": "#fff5f3", "focus": "#3788c4",
    "subtle": "#f4f6f8", "alternate": "#f7f9fb", "raised": "#e9eef3",
    "divider": "#ccd5de", "hover": "#e6eef5", "hover_border": "#adc6dc",
    "checked": "#dcebf8", "checked_border": "#acc9e2", "pressed": "#d8e6f0",
    "button": "#f4f7fa", "button_border": "#c4cfda", "button_hover_border": "#9abbd7",
    "disabled": "#f0f3f5", "disabled_text": "#8b97a3", "disabled_border": "#dce2e7",
    "disabled_accent": "#e1e7ea", "heading": "#243c52", "group_heading": "#324d60",
    "icon_stroke": "#40556a", "plot_text": "#536574", "plot_grid": "#e5ebef",
    "plot_border": "#aab8c4",
    "ok_text": "#1b653e", "ok_surface": "#ebf7f0", "ok_border": "#96cfb0",
    "warn_text": "#7c5211", "warn_surface": "#fdf6e7", "warn_border": "#dfc082",
    "bad_text": "#9e2a2b", "bad_surface": "#fff2f0", "bad_border": "#e0a3a0",
    "font_family": "'Segoe UI'",
    "font_size": 10, "title_size": 11, "heading_weight": 600, "header_weight": 600,
    "spacing": _SPACING, "space_xs": _SPACING[0], "space_sm": _SPACING[1],
    "space_md": _SPACING[2], "space_lg": _SPACING[3], "space_xl": _SPACING[4],
    "border_width": 1, "radius": 2, "row_height": 20, "tree_row_height": 20,
    "icon_size": 16, "icon_canvas": 20, "icon_render_size": 48, "icon_stroke_width": 1.65,
    "control_min_height": 20, "numeric_min_width": 70, "tree_indent": 14,
    "control_pad_y": 1, "control_pad_x": 4, "button_pad_y": 2, "button_pad_x": 6,
    "menu_pad": 4, "menu_bar_pad_y": 2, "menu_bar_pad_x": 6,
    "menu_item_pad_y": 3, "menu_item_pad_x": 8,
    "menu_popup_pad_y": 4, "menu_popup_pad_right": 24, "menu_popup_pad_left": 18,
    "toolbar_pad_y": 2, "toolbar_pad_x": 4, "toolbutton_pad": 2,
    "dock_pad_y": 3, "dock_pad_x": 6, "tree_pad_y": 0, "tree_pad_x": 2,
    "checkbox_spacing": 4, "checkbox_pad_y": 1, "form_spacing": 2,
    "form_column_gap": 6, "panel_pad_y": 4, "catalogue_navigation_width": 180,
    "catalogue_metadata_height": 110,
    "plot_min_width": 220, "plot_min_height": 180, "plot_preview_min_height": 120,
    "plot_left": 64, "plot_top": 30, "plot_right": 24, "plot_bottom": 54,
    "plot_line_width": 2, "plot_marker_radius": 3,
}

DARK_TOKENS = {
    **TOKENS,
    "workspace": "#141920",
    "surface": "#1d242e",
    "text": "#e6edf3",
    "muted": "#9bb0c6",
    "border": "#344254",
    "divider": "#2a3644",
    "subtle": "#18202a",
    "alternate": "#212a36",
    "raised": "#232d3a",
    "accent": "#4ea1f3",
    "accent_hover": "#6bb3f8",
    "on_accent": "#ffffff",
    "selection": "#1f3d5c",
    "selection_text": "#f0f6fc",
    "button": "#25303e",
    "button_border": "#3b4b5f",
    "button_hover_border": "#5c84ad",
    "hover": "#2a3848",
    "hover_border": "#4e6a88",
    "checked": "#223b54",
    "checked_border": "#4ea1f3",
    "pressed": "#1b3147",
    "focus": "#58a6ff",
    "disabled": "#192029",
    "disabled_text": "#637587",
    "disabled_border": "#283341",
    "disabled_accent": "#253545",
    "heading": "#eaf2fa",
    "group_heading": "#cfe0f2",
    "icon_stroke": "#d3e0ee",
    "error": "#f47067",
    "error_surface": "#3a1e20",
    "ok_text": "#6fdd9c", "ok_surface": "#183326", "ok_border": "#2d6a49",
    "warn_text": "#f0c265", "warn_surface": "#362b17", "warn_border": "#735826",
    "bad_text": "#ff8b82", "bad_surface": "#3a1e20", "bad_border": "#7a383c",
    "plot_text": "#9bb0c6",
    "plot_grid": "#283442",
    "plot_border": "#3d4f63",
    "font_family": "'Malgun Gothic', 'Segoe UI'",
}

ELEMENT_FAMILY_PALETTE_LIGHT = {
    "Hex8": "#3b82c4",
    "Wedge6": "#7c62b8",
    "Pyramid5": "#d4822a",
    "Tet4": "#2e9e7e",
    "Tet10": "#c9566b",
    "Hex20": "#2697b5",
    "Wedge15": "#8c9638",
    "Quad4": "#4d88b8",
    "Tri3": "#4aa382",
    "Quad8": "#3898ad",
    "Tri6": "#c4687a",
    "Line2": "#7b8794",
}

ELEMENT_FAMILY_PALETTE_DARK = {
    "Hex8": "#4d96db",
    "Wedge6": "#967ad6",
    "Pyramid5": "#ea9c3e",
    "Tet4": "#3eb895",
    "Tet10": "#e06e84",
    "Hex20": "#3cb6d6",
    "Wedge15": "#aab64c",
    "Quad4": "#5da0d6",
    "Tri3": "#5ec09c",
    "Quad8": "#4cb6cc",
    "Tri6": "#db7d8f",
    "Line2": "#95a3b3",
}


def tokens_for_theme(mode: str = "light") -> dict:
    return DARK_TOKENS if str(mode).strip().lower() == "dark" else TOKENS


def element_family_palette(mode: str = "light") -> dict[str, str]:
    source = ELEMENT_FAMILY_PALETTE_DARK if str(mode).strip().lower() == "dark" else ELEMENT_FAMILY_PALETTE_LIGHT
    return dict(source)
