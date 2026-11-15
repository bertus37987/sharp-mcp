"""Declarative Roblox GUI tree exporter emitting valid .rbxmx XML and executable Luau.

Supports:
- Generic dict-tree -> .rbxmx XML (`dict_to_rbxmx`) and -> Luau (`dict_to_luau`)
- Modern Roblox UI properties: ScreenInsets, ZIndexBehavior, UIFlexItem, UIStroke,
  UIGradient, UICorner, UISizeConstraint, UIAspectRatioConstraint, SliceCenter (Rect2D),
  ImageRectOffset/Size, FontFace, StyleSheet/StyleRule/StyleLink (with Ref linking).
- Built-in Standard Game GUI blueprint (`generate_standard_gui_rbxmx`, `generate_standard_gui_luau`)
  accepting optional processed 9-slice & atlas asset IDs from `slice_and_atlas_helper.py`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

ROBLOX_XML_HEADER = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime"\n'
    '        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
    '        xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">'
)

# Verified Roblox XML token tables
ENUM_TOKENS: dict[str, dict[str, int]] = {
    "ZIndexBehavior": {"Global": 0, "Sibling": 1},
    "ScreenInsets": {"None": 0, "DeviceSafeInsets": 1, "CoreUISafeInsets": 2, "TopbarSafeInsets": 3},
    "SafeAreaCompatibility": {"None": 0, "FullscreenExtension": 1},
    "ScaleType": {"Stretch": 0, "Slice": 1, "Tile": 2, "Fit": 3, "Crop": 4},
    "ResampleMode": {"Default": 0, "Pixelated": 1},
    "SortOrder": {"Name": 0, "Custom": 1, "LayoutOrder": 2},
    "FillDirection": {"Horizontal": 0, "Vertical": 1},
    "HorizontalAlignment": {"Center": 0, "Left": 1, "Right": 2},
    "VerticalAlignment": {"Center": 0, "Top": 1, "Bottom": 2},
    "HorizontalFlex": {"None": 0, "Fill": 1, "SpaceAround": 2, "SpaceBetween": 3, "SpaceEvenly": 4},
    "VerticalFlex": {"None": 0, "Fill": 1, "SpaceAround": 2, "SpaceBetween": 3, "SpaceEvenly": 4},
    "FlexMode": {"None": 0, "Grow": 1, "Shrink": 2, "Fill": 3, "Custom": 4},
    "ItemLineAlignment": {"Automatic": 0, "Start": 1, "Center": 2, "End": 3, "Stretch": 4},
    "ApplyStrokeMode": {"Contextual": 0, "Border": 1},
    "BorderStrokePosition": {"Outer": 0, "Center": 1, "Inner": 2},
    "StrokeSizingMode": {"FixedSize": 0, "ScaledSize": 1},
    "LineJoinMode": {"Round": 0, "Bevel": 1, "Miter": 2},
    "AutomaticSize": {"None": 0, "X": 1, "Y": 2, "XY": 3},
    "ScrollingDirection": {"X": 1, "Y": 2, "XY": 4},
    "TextXAlignment": {"Left": 0, "Right": 1, "Center": 2},
    "TextYAlignment": {"Top": 0, "Center": 1, "Bottom": 2},
    "SelectionBehaviorUp": {"Escape": 0, "Stop": 1},
    "SelectionBehaviorDown": {"Escape": 0, "Stop": 1},
    "SelectionBehaviorLeft": {"Escape": 0, "Stop": 1},
    "SelectionBehaviorRight": {"Escape": 0, "Stop": 1},
    "InputSink": {"None": 0, "Activate": 1, "All": 100},
    "AspectType": {"FitWithinMaxSize": 0, "ScaleWithParentSize": 1},
    "DominantAxis": {"Width": 0, "Height": 1},
}

ENUM_LUAU_PREFIX: dict[str, str] = {
    "ZIndexBehavior": "Enum.ZIndexBehavior",
    "ScreenInsets": "Enum.ScreenInsets",
    "SafeAreaCompatibility": "Enum.SafeAreaCompatibility",
    "ScaleType": "Enum.ScaleType",
    "ResampleMode": "Enum.ResamplerMode",
    "SortOrder": "Enum.SortOrder",
    "FillDirection": "Enum.FillDirection",
    "HorizontalAlignment": "Enum.HorizontalAlignment",
    "VerticalAlignment": "Enum.VerticalAlignment",
    "HorizontalFlex": "Enum.UIFlexAlignment",
    "VerticalFlex": "Enum.UIFlexAlignment",
    "FlexMode": "Enum.UIFlexMode",
    "ItemLineAlignment": "Enum.ItemLineAlignment",
    "ApplyStrokeMode": "Enum.ApplyStrokeMode",
    "BorderStrokePosition": "Enum.BorderStrokePosition",
    "StrokeSizingMode": "Enum.StrokeSizingMode",
    "LineJoinMode": "Enum.LineJoinMode",
    "AutomaticSize": "Enum.AutomaticSize",
    "ScrollingDirection": "Enum.ScrollingDirection",
    "TextXAlignment": "Enum.TextXAlignment",
    "TextYAlignment": "Enum.TextYAlignment",
    "SelectionBehaviorUp": "Enum.SelectionBehavior",
    "SelectionBehaviorDown": "Enum.SelectionBehavior",
    "SelectionBehaviorLeft": "Enum.SelectionBehavior",
    "SelectionBehaviorRight": "Enum.SelectionBehavior",
    "InputSink": "Enum.InputSink",
    "AspectType": "Enum.AspectType",
    "DominantAxis": "Enum.DominantAxis",
}


class RefGenerator:
    """Deterministic sequential referent generator for Roblox XML <Item> nodes."""

    def __init__(self, prefix: str = "RBX") -> None:
        self._prefix = prefix
        self._counter = 0
        self._named: dict[str, str] = {}

    def next_ref(self, alias: str | None = None) -> str:
        if alias and alias in self._named:
            return self._named[alias]
        ref = f"{self._prefix}{self._counter}"
        self._counter += 1
        if alias:
            self._named[alias] = ref
        return ref

    def resolve(self, alias: str) -> str:
        if alias not in self._named:
            self._named[alias] = self.next_ref()
        return self._named[alias]


def _prop_xml(name: str, value: Any, refs: RefGenerator, indent: str) -> list[str]:
    """Serialize a typed property dictionary entry to Roblox XML lines."""
    if isinstance(value, bool):
        return [f'{indent}<bool name="{xml_escape(name)}">{"true" if value else "false"}</bool>']
    if isinstance(value, int):
        return [f'{indent}<int name="{xml_escape(name)}">{value}</int>']
    if isinstance(value, float):
        return [f'{indent}<float name="{xml_escape(name)}">{value:.6g}</float>']
    if isinstance(value, str):
        if name in ENUM_TOKENS and value in ENUM_TOKENS[name]:
            tok = ENUM_TOKENS[name][value]
            return [f'{indent}<token name="{xml_escape(name)}">{tok}</token>']
        if name in ("Image", "Texture"):
            return [
                f'{indent}<Content name="{xml_escape(name)}"><url>{xml_escape(value)}</url></Content>'
            ]
        return [f'{indent}<string name="{xml_escape(name)}">{xml_escape(value)}</string>']

    if not isinstance(value, dict) or "_type" not in value:
        return []

    t = value["_type"]
    if t == "UDim2":
        xs, xo, ys, yo = value["v"]
        return [
            f'{indent}<UDim2 name="{xml_escape(name)}">'
            f"<XS>{xs}</XS><XO>{xo}</XO><YS>{ys}</YS><YO>{yo}</YO>"
            "</UDim2>"
        ]
    if t == "UDim":
        s, o = value["v"]
        return [f'{indent}<UDim name="{xml_escape(name)}"><S>{s}</S><O>{o}</O></UDim>']
    if t == "Vector2":
        x, y = value["v"]
        return [f'{indent}<Vector2 name="{xml_escape(name)}"><X>{x}</X><Y>{y}</Y></Vector2>']
    if t == "Color3":
        r, g, b = value["v"]
        return [
            f'{indent}<Color3 name="{xml_escape(name)}">'
            f"<R>{r / 255.0:.6f}</R><G>{g / 255.0:.6f}</G><B>{b / 255.0:.6f}</B>"
            "</Color3>"
        ]
    if t == "Rect2D":
        x0, y0, x1, y1 = value["v"]
        return [
            f'{indent}<Rect2D name="{xml_escape(name)}">'
            f"<min><X>{x0}</X><Y>{y0}</Y></min>"
            f"<max><X>{x1}</X><Y>{y1}</Y></max>"
            "</Rect2D>"
        ]
    if t == "FontFace":
        family = xml_escape(str(value.get("family", "rbxasset://fonts/families/BuilderSans.json")))
        weight = int(value.get("weight", 600))
        style = xml_escape(str(value.get("style", "Normal")))
        return [
            f'{indent}<Font name="{xml_escape(name)}">'
            f"<Family><url>{family}</url></Family>"
            f"<Weight>{weight}</Weight>"
            f"<Style>{style}</Style>"
            "</Font>"
        ]
    if t == "ColorSequence":
        parts = []
        for stop_t, (r, g, b) in value["v"]:
            parts.append(f"{stop_t} {r / 255.0:.6f} {g / 255.0:.6f} {b / 255.0:.6f} 0")
        return [f'{indent}<ColorSequence name="{xml_escape(name)}">{" ".join(parts)} </ColorSequence>']
    if t == "NumberSequence":
        parts = [f"{stop_t} {val} 0" for stop_t, val in value["v"]]
        return [f'{indent}<NumberSequence name="{xml_escape(name)}">{" ".join(parts)} </NumberSequence>']
    if t == "Ref":
        target = refs.resolve(str(value["v"]))
        return [f'{indent}<Ref name="{xml_escape(name)}">{target}</Ref>']
    if t == "ProtectedString":
        return [f'{indent}<ProtectedString name="{xml_escape(name)}">{xml_escape(str(value["v"]))}</ProtectedString>']
    return []


def _emit_item_xml(node: dict[str, Any], refs: RefGenerator, depth: int) -> list[str]:
    indent = "  " * depth
    cls = xml_escape(str(node["ClassName"]))
    ref = refs.next_ref(node.get("_ref_id"))
    lines = [f'{indent}<Item class="{cls}" referent="{ref}">', f"{indent}  <Properties>"]

    props = dict(node.get("Properties", {}))
    if "Name" not in props and "Name" in node:
        props["Name"] = node["Name"]

    for pname, pval in props.items():
        lines.extend(_prop_xml(pname, pval, refs, indent + "    "))

    lines.append(f"{indent}  </Properties>")
    for child in node.get("Children", []):
        lines.extend(_emit_item_xml(child, refs, depth + 1))
    lines.append(f"{indent}</Item>")
    return lines


def dict_to_rbxmx(
    instances: list[dict[str, Any]],
    output_path: str | Path | None = None,
) -> str:
    """Serialize a list of declarative GUI instance dictionaries to a Roblox .rbxmx XML string."""
    refs = RefGenerator()
    lines = [ROBLOX_XML_HEADER]
    for node in instances:
        lines.extend(_emit_item_xml(node, refs, 1))
    lines.append("</roblox>\n")
    xml_text = "\n".join(lines)

    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(xml_text, encoding="utf-8")
    return xml_text


def _luau_quote(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _prop_luau(name: str, value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if name in ENUM_LUAU_PREFIX:
            return f"{ENUM_LUAU_PREFIX[name]}.{value}"
        return _luau_quote(value)
    if not isinstance(value, dict) or "_type" not in value:
        return None
    t = value["_type"]
    if t == "UDim2":
        xs, xo, ys, yo = value["v"]
        return f"UDim2.new({xs}, {xo}, {ys}, {yo})"
    if t == "UDim":
        s, o = value["v"]
        return f"UDim.new({s}, {o})"
    if t == "Vector2":
        x, y = value["v"]
        return f"Vector2.new({x}, {y})"
    if t == "Color3":
        r, g, b = value["v"]
        return f"Color3.fromRGB({r}, {g}, {b})"
    if t == "Rect2D":
        x0, y0, x1, y1 = value["v"]
        return f"Rect.new({x0}, {y0}, {x1}, {y1})"
    if t == "FontFace":
        fam = str(value.get("family", "rbxasset://fonts/families/BuilderSans.json"))
        w = int(value.get("weight", 600))
        st = str(value.get("style", "Normal"))
        return f"Font.new({_luau_quote(fam)}, Enum.FontWeight.{_weight_name(w)}, Enum.FontStyle.{st})"
    if t == "ColorSequence":
        kps = [
            f"ColorSequenceKeypoint.new({st}, Color3.fromRGB({r}, {g}, {b}))"
            for st, (r, g, b) in value["v"]
        ]
        return f"ColorSequence.new({{ {', '.join(kps)} }})"
    if t == "NumberSequence":
        kps = [f"NumberSequenceKeypoint.new({st}, {val})" for st, val in value["v"]]
        return f"NumberSequence.new({{ {', '.join(kps)} }})"
    if t == "Ref":
        return f"refMap[{_luau_quote(str(value['v']))}]"
    if t == "ProtectedString":
        return _luau_quote(str(value["v"]))
    return None


def _weight_name(weight: int) -> str:
    mapping = {
        100: "Thin",
        200: "ExtraLight",
        300: "Light",
        400: "Regular",
        500: "Medium",
        600: "SemiBold",
        700: "Bold",
        800: "ExtraBold",
        900: "Heavy",
    }
    return mapping.get(weight, "SemiBold")


def dict_to_luau(
    instances: list[dict[str, Any]],
    output_path: str | Path | None = None,
    root_parent: str = 'game:GetService("StarterGui")',
) -> str:
    """Emit a self-contained --!strict Luau script that instantiates the given GUI tree."""
    lines = [
        "--!strict",
        "-- Auto-generated by roblox-gui/scripts/generate_rbxmx_gui.py",
        f"local ROOT_PARENT: Instance = {root_parent}",
        "local refMap: { [string]: Instance } = {}",
        "local deferredRefs: { { inst: Instance, prop: string, alias: string } } = {}",
        "",
    ]
    counter = [0]

    def emit_node(node: dict[str, Any], parent_var: str) -> None:
        counter[0] += 1
        var = f"i{counter[0]}"
        cls = node["ClassName"]
        props = dict(node.get("Properties", {}))
        if "Name" not in props and "Name" in node:
            props["Name"] = node["Name"]

        if parent_var == "ROOT_PARENT" and "Name" in props:
            lines.append(f"local prev_{var} = ROOT_PARENT:FindFirstChild({_luau_quote(str(props['Name']))})")
            lines.append(f"if prev_{var} then prev_{var}:Destroy() end")

        lines.append(f"local {var} = Instance.new({_luau_quote(cls)})")
        if "_ref_id" in node:
            lines.append(f"refMap[{_luau_quote(str(node['_ref_id']))}] = {var}")

        for pname, pval in props.items():
            if isinstance(pval, dict) and pval.get("_type") == "Ref":
                lines.append(
                    f"table.insert(deferredRefs, {{ inst = {var}, prop = {_luau_quote(pname)}, alias = {_luau_quote(str(pval['v']))} }})"
                )
                continue
            expr = _prop_luau(pname, pval)
            if expr is not None:
                lines.append(f"({var} :: any)[{_luau_quote(pname)}] = {expr}")

        for k, v in node.get("Attributes", {}).items():
            attr_expr = _prop_luau("Attr", v)
            if attr_expr is not None:
                lines.append(f"{var}:SetAttribute({_luau_quote(k)}, {attr_expr})")

        for tag in node.get("Tags", []):
            lines.append(f"{var}:AddTag({_luau_quote(tag)})")

        lines.append(f"{var}.Parent = {parent_var}")
        for child in node.get("Children", []):
            emit_node(child, var)

    for inst in instances:
        emit_node(inst, "ROOT_PARENT")

    lines.extend(
        [
            "",
            "for _, link in ipairs(deferredRefs) do",
            "    local target = refMap[link.alias]",
            "    if target then",
            "        (link.inst :: any)[link.prop] = target",
            "    end",
            "end",
            'return "Built GUI tree (" .. tostring(#ROOT_PARENT:GetChildren()) .. " children)"',
            "",
        ]
    )

    luau_text = "\n".join(lines)
    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(luau_text, encoding="utf-8")
    return luau_text


def _udim2(xs: float, xo: int, ys: float, yo: int) -> dict[str, Any]:
    return {"_type": "UDim2", "v": [xs, xo, ys, yo]}


def _udim(s: float, o: int) -> dict[str, Any]:
    return {"_type": "UDim", "v": [s, o]}


def _vec2(x: float, y: float) -> dict[str, Any]:
    return {"_type": "Vector2", "v": [x, y]}


def _rgb(r: int, g: int, b: int) -> dict[str, Any]:
    return {"_type": "Color3", "v": [r, g, b]}


def _rect(x0: int, y0: int, x1: int, y1: int) -> dict[str, Any]:
    return {"_type": "Rect2D", "v": [x0, y0, x1, y1]}


def _font(weight: int = 600) -> dict[str, Any]:
    return {
        "_type": "FontFace",
        "family": "rbxasset://fonts/families/BuilderSans.json",
        "weight": weight,
        "style": "Normal",
    }


def _card_frame(
    name: str,
    size: dict[str, Any],
    pos: dict[str, Any],
    *,
    anchor: tuple[float, float] = (0.0, 0.0),
    bg: tuple[int, int, int] = (22, 29, 44),
    bg_trans: float = 0.08,
    corner_px: int = 12,
    stroke_rgb: tuple[int, int, int] = (72, 92, 130),
    panel_asset_id: str | None = None,
    panel_slice_center: tuple[int, int, int, int] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if panel_asset_id and panel_slice_center:
        return {
            "ClassName": "ImageLabel",
            "Name": name,
            "Properties": {
                "Size": size,
                "Position": pos,
                "AnchorPoint": _vec2(*anchor),
                "BackgroundTransparency": 1.0,
                "Image": panel_asset_id,
                "ScaleType": "Slice",
                "SliceCenter": _rect(*panel_slice_center),
                "SliceScale": 0.22,
            },
            "Children": list(children or []),
        }
    return {
        "ClassName": "Frame",
        "Name": name,
        "Properties": {
            "Size": size,
            "Position": pos,
            "AnchorPoint": _vec2(*anchor),
            "BackgroundColor3": _rgb(*bg),
            "BackgroundTransparency": bg_trans,
            "BorderSizePixel": 0,
        },
        "Children": [
            {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(0, corner_px)}},
            {
                "ClassName": "UIStroke",
                "Name": "Stroke",
                "Properties": {
                    "ApplyStrokeMode": "Border",
                    "Color": _rgb(*stroke_rgb),
                    "Thickness": 1.5,
                    "Transparency": 0.25,
                },
            },
            *(children or []),
        ],
    }


def build_standard_gui_blueprint(assets: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build a declarative StarterGui blueprint matching Standard Game GUI Mapping.

    Optional `assets` keys:
      - panel_9slice_id: "rbxassetid://..."
      - panel_slice_center: [minX, minY, maxX, maxY]
      - button_9slice_id: "rbxassetid://..."
      - button_slice_center: [minX, minY, maxX, maxY]
      - icon_atlas_id: "rbxassetid://..."
      - icon_rects: { name: [x, y, w, h] }
    """
    assets = assets or {}
    panel_id = assets.get("panel_9slice_id")
    panel_sc_raw = assets.get("panel_slice_center")
    panel_sc = tuple(panel_sc_raw) if isinstance(panel_sc_raw, (list, tuple)) and len(panel_sc_raw) == 4 else None

    btn_id = assets.get("button_9slice_id")
    btn_sc_raw = assets.get("button_slice_center")
    btn_sc = tuple(btn_sc_raw) if isinstance(btn_sc_raw, (list, tuple)) and len(btn_sc_raw) == 4 else None

    atlas_id = assets.get("icon_atlas_id")
    icon_rects: dict[str, list[int]] = assets.get("icon_rects", {})

    def icon_node(name: str, sprite_key: str, fallback_text: str, accent: tuple[int, int, int]) -> dict[str, Any]:
        if atlas_id and sprite_key in icon_rects:
            x, y, w, h = icon_rects[sprite_key]
            return {
                "ClassName": "ImageLabel",
                "Name": name,
                "Properties": {
                    "Size": _udim2(0, 26, 0, 26),
                    "BackgroundTransparency": 1.0,
                    "Image": atlas_id,
                    "ImageRectOffset": _vec2(x, y),
                    "ImageRectSize": _vec2(w, h),
                    "ResampleMode": "Default",
                },
            }
        return {
            "ClassName": "TextLabel",
            "Name": name,
            "Properties": {
                "Size": _udim2(0, 26, 0, 26),
                "BackgroundColor3": _rgb(*accent),
                "Text": fallback_text,
                "TextColor3": _rgb(255, 255, 255),
                "TextSize": 14,
                "FontFace": _font(800),
                "BorderSizePixel": 0,
            },
            "Children": [
                {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(1, 0)}}
            ],
        }

    def action_button(
        name: str,
        text: str,
        bg_rgb: tuple[int, int, int],
        order: int,
        pos: dict[str, Any] | None = None,
        anchor: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        btn_pos = pos or _udim2(0, 0, 0, 0)
        btn_anchor = _vec2(*(anchor or (0.0, 0.0)))
        if btn_id and btn_sc:
            return {
                "ClassName": "ImageButton",
                "Name": name,
                "Properties": {
                    "Size": _udim2(0, 148, 0, 52),
                    "Position": btn_pos,
                    "AnchorPoint": btn_anchor,
                    "LayoutOrder": order,
                    "BackgroundTransparency": 1.0,
                    "Image": btn_id,
                    "ImageColor3": _rgb(*bg_rgb),
                    "ScaleType": "Slice",
                    "SliceCenter": _rect(*btn_sc),
                    "SliceScale": 0.32,
                    "AutoButtonColor": True,
                },
                "Children": [
                    {
                        "ClassName": "UISizeConstraint",
                        "Name": "MinTouch",
                        "Properties": {"MinSize": _vec2(44, 44)},
                    },
                    {
                        "ClassName": "TextLabel",
                        "Name": "Label",
                        "Properties": {
                            "Size": _udim2(1, -16, 1, 0),
                            "Position": _udim2(0, 8, 0, 0),
                            "BackgroundTransparency": 1.0,
                            "Text": text,
                            "TextColor3": _rgb(255, 255, 255),
                            "TextSize": 15,
                            "FontFace": _font(700),
                        },
                    },
                ],
            }
        return {
            "ClassName": "TextButton",
            "Name": name,
            "Properties": {
                "Size": _udim2(0, 148, 0, 52),
                "Position": btn_pos,
                "AnchorPoint": btn_anchor,
                "LayoutOrder": order,
                "BackgroundColor3": _rgb(*bg_rgb),
                "Text": text,
                "TextColor3": _rgb(255, 255, 255),
                "TextSize": 15,
                "FontFace": _font(700),
                "BorderSizePixel": 0,
            },
            "Children": [
                {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(0, 10)}},
                {"ClassName": "UISizeConstraint", "Name": "MinTouch", "Properties": {"MinSize": _vec2(44, 44)}},
            ],
        }

    side_rail_items = [
        ("Shop", "Shop", (56, 130, 246), "coin", "$"),
        ("Inventory", "Bag", (212, 146, 56), "combat", "I"),
        ("Quests", "Quests", (46, 184, 114), "chest", "Q"),
        ("IndexCodes", "Index", (150, 96, 232), "gem", "X"),
        ("Settings", "Settings", (96, 112, 138), "coin", "*"),
    ]
    side_rail_children: list[dict[str, Any]] = [
        {
            "ClassName": "UIListLayout",
            "Name": "Layout",
            "Properties": {
                "FillDirection": "Vertical",
                "SortOrder": "LayoutOrder",
                "Padding": _udim(0, 8),
            },
        }
    ]
    for idx, (key, label, accent, sprite, glyph) in enumerate(side_rail_items):
        side_rail_children.append(
            {
                "ClassName": "TextButton",
                "Name": f"{key}Btn",
                "Properties": {
                    "Size": _udim2(0, 116, 0, 46),
                    "LayoutOrder": idx + 1,
                    "BackgroundColor3": _rgb(24, 32, 48),
                    "BackgroundTransparency": 0.1,
                    "Text": "",
                    "BorderSizePixel": 0,
                },
                "Children": [
                    {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(0, 10)}},
                    {
                        "ClassName": "UIStroke",
                        "Name": "Stroke",
                        "Properties": {"ApplyStrokeMode": "Border", "Color": _rgb(*accent), "Thickness": 1.5},
                    },
                    {
                        "ClassName": "UISizeConstraint",
                        "Name": "MinTouch",
                        "Properties": {"MinSize": _vec2(44, 44)},
                    },
                    {
                        "ClassName": "UIListLayout",
                        "Name": "Row",
                        "Properties": {
                            "FillDirection": "Horizontal",
                            "VerticalAlignment": "Center",
                            "Padding": _udim(0, 8),
                        },
                    },
                    {
                        "ClassName": "UIPadding",
                        "Name": "Pad",
                        "Properties": {"PaddingLeft": _udim(0, 10), "PaddingRight": _udim(0, 8)},
                    },
                    icon_node("Icon", sprite, glyph, accent),
                    {
                        "ClassName": "TextLabel",
                        "Name": "Title",
                        "Properties": {
                            "Size": _udim2(1, -36, 1, 0),
                            "BackgroundTransparency": 1.0,
                            "Text": label,
                            "TextColor3": _rgb(238, 244, 255),
                            "TextSize": 14,
                            "TextXAlignment": "Left",
                            "FontFace": _font(700),
                        },
                    },
                ],
            }
        )

    hotbar_children: list[dict[str, Any]] = [
        {
            "ClassName": "UIListLayout",
            "Name": "Layout",
            "Properties": {
                "FillDirection": "Horizontal",
                "HorizontalAlignment": "Center",
                "VerticalAlignment": "Center",
                "SortOrder": "LayoutOrder",
                "Padding": _udim(0, 8),
            },
        }
    ]
    for slot in range(1, 6):
        hotbar_children.append(
            {
                "ClassName": "TextButton",
                "Name": f"Slot{slot}",
                "Properties": {
                    "Size": _udim2(0, 56, 0, 56),
                    "LayoutOrder": slot,
                    "BackgroundColor3": _rgb(24, 32, 48),
                    "BackgroundTransparency": 0.12,
                    "Text": f"[{slot}]",
                    "TextColor3": _rgb(230, 238, 250),
                    "TextSize": 14,
                    "FontFace": _font(700),
                    "BorderSizePixel": 0,
                },
                "Children": [
                    {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(0, 10)}},
                    {
                        "ClassName": "UIStroke",
                        "Name": "Stroke",
                        "Properties": {
                            "ApplyStrokeMode": "Border",
                            "Color": _rgb(245, 196, 82) if slot == 1 else _rgb(72, 92, 130),
                            "Thickness": 2.0 if slot == 1 else 1.2,
                        },
                    },
                    {"ClassName": "UIAspectRatioConstraint", "Name": "Square", "Properties": {"AspectRatio": 1.0}},
                    {"ClassName": "UISizeConstraint", "Name": "MinTouch", "Properties": {"MinSize": _vec2(44, 44)}},
                ],
            }
        )

    main_hud = {
        "ClassName": "ScreenGui",
        "Name": "MainHudGui",
        "Properties": {
            "DisplayOrder": 10,
            "ScreenInsets": "CoreUISafeInsets",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": True,
        },
        "Children": [
            _card_frame(
                "PlayerStatus",
                _udim2(0, 236, 0, 74),
                _udim2(0, 14, 0, 12),
                children=[
                    {
                        "ClassName": "TextLabel",
                        "Name": "LevelTitle",
                        "Properties": {
                            "Size": _udim2(1, -20, 0, 22),
                            "Position": _udim2(0, 10, 0, 6),
                            "BackgroundTransparency": 1.0,
                            "Text": "Lv. 14 Vanguard",
                            "TextColor3": _rgb(242, 246, 255),
                            "TextSize": 14,
                            "TextXAlignment": "Left",
                            "FontFace": _font(700),
                        },
                    },
                    {
                        "ClassName": "Frame",
                        "Name": "HpTrack",
                        "Properties": {
                            "Size": _udim2(1, -20, 0, 14),
                            "Position": _udim2(0, 10, 0, 32),
                            "BackgroundColor3": _rgb(14, 18, 28),
                            "BorderSizePixel": 0,
                        },
                        "Children": [
                            {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(1, 0)}},
                            {
                                "ClassName": "Frame",
                                "Name": "Fill",
                                "Properties": {
                                    "Size": _udim2(0.84, 0, 1, 0),
                                    "BackgroundColor3": _rgb(54, 204, 118),
                                    "BorderSizePixel": 0,
                                },
                                "Children": [
                                    {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(1, 0)}}
                                ],
                            },
                        ],
                    },
                    {
                        "ClassName": "Frame",
                        "Name": "XpTrack",
                        "Properties": {
                            "Size": _udim2(1, -20, 0, 8),
                            "Position": _udim2(0, 10, 0, 52),
                            "BackgroundColor3": _rgb(14, 18, 28),
                            "BorderSizePixel": 0,
                        },
                        "Children": [
                            {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(1, 0)}},
                            {
                                "ClassName": "Frame",
                                "Name": "Fill",
                                "Properties": {
                                    "Size": _udim2(0.68, 0, 1, 0),
                                    "BackgroundColor3": _rgb(76, 166, 255),
                                    "BorderSizePixel": 0,
                                },
                                "Children": [
                                    {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(1, 0)}}
                                ],
                            },
                        ],
                    },
                ],
            ),
            _card_frame(
                "CurrencyBar",
                _udim2(0, 268, 0, 48),
                _udim2(1, -14, 0, 12),
                anchor=(1.0, 0.0),
                children=[
                    {
                        "ClassName": "UIListLayout",
                        "Name": "Row",
                        "Properties": {
                            "FillDirection": "Horizontal",
                            "HorizontalAlignment": "Center",
                            "VerticalAlignment": "Center",
                            "Padding": _udim(0, 10),
                        },
                    },
                    icon_node("CoinIcon", "coin", "$", (245, 190, 62)),
                    {
                        "ClassName": "TextLabel",
                        "Name": "CoinsLabel",
                        "Properties": {
                            "Size": _udim2(0, 74, 0, 26),
                            "BackgroundTransparency": 1.0,
                            "Text": "12,450",
                            "TextColor3": _rgb(255, 224, 130),
                            "TextSize": 15,
                            "TextXAlignment": "Left",
                            "FontFace": _font(800),
                        },
                    },
                    icon_node("GemIcon", "gem", "*", (46, 206, 255)),
                    {
                        "ClassName": "TextLabel",
                        "Name": "GemsLabel",
                        "Properties": {
                            "Size": _udim2(0, 52, 0, 26),
                            "BackgroundTransparency": 1.0,
                            "Text": "320",
                            "TextColor3": _rgb(142, 232, 255),
                            "TextSize": 15,
                            "TextXAlignment": "Left",
                            "FontFace": _font(800),
                        },
                    },
                    {
                        "ClassName": "TextButton",
                        "Name": "AddCurrencyBtn",
                        "Properties": {
                            "Size": _udim2(0, 44, 0, 44),
                            "BackgroundColor3": _rgb(46, 178, 108),
                            "Text": "+",
                            "TextColor3": _rgb(255, 255, 255),
                            "TextSize": 20,
                            "FontFace": _font(800),
                            "BorderSizePixel": 0,
                        },
                        "Children": [
                            {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(0, 8)}}
                        ],
                    },
                ],
            ),
            {
                "ClassName": "Frame",
                "Name": "SideRail",
                "Properties": {
                    "Size": _udim2(0, 124, 0, 264),
                    "Position": _udim2(0, 14, 0.42, 0),
                    "AnchorPoint": _vec2(0.0, 0.5),
                    "BackgroundTransparency": 1.0,
                },
                "Children": side_rail_children,
            },
            {
                "ClassName": "Frame",
                "Name": "ActionHotbar",
                "Properties": {
                    "Size": _udim2(0, 336, 0, 66),
                    "Position": _udim2(0.5, 0, 1, -12),
                    "AnchorPoint": _vec2(0.5, 1.0),
                    "BackgroundTransparency": 1.0,
                },
                "Children": hotbar_children,
            },
        ],
    }

    modal_menus = {
        "ClassName": "ScreenGui",
        "Name": "ModalMenusGui",
        "Properties": {
            "DisplayOrder": 50,
            "ScreenInsets": "CoreUISafeInsets",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": True,
        },
        "Children": [
            _card_frame(
                "ShopModal",
                _udim2(0.76, 0, 0.74, 0),
                _udim2(0.5, 0, 0.5, 0),
                anchor=(0.5, 0.5),
                panel_asset_id=panel_id,
                panel_slice_center=panel_sc,
                children=[
                    {
                        "ClassName": "UISizeConstraint",
                        "Name": "Bounds",
                        "Properties": {"MinSize": _vec2(320, 240), "MaxSize": _vec2(780, 520)},
                    },
                    {
                        "ClassName": "TextLabel",
                        "Name": "HeaderTitle",
                        "Properties": {
                            "Size": _udim2(1, -72, 0, 44),
                            "Position": _udim2(0, 20, 0, 12),
                            "BackgroundTransparency": 1.0,
                            "Text": "STARTER SHOP",
                            "TextColor3": _rgb(250, 242, 220),
                            "TextSize": 20,
                            "TextXAlignment": "Left",
                            "FontFace": _font(800),
                        },
                    },
                    {
                        "ClassName": "TextButton",
                        "Name": "CloseButton",
                        "Properties": {
                            "Size": _udim2(0, 44, 0, 44),
                            "Position": _udim2(1, -14, 0, 12),
                            "AnchorPoint": _vec2(1.0, 0.0),
                            "BackgroundColor3": _rgb(192, 62, 72),
                            "Text": "X",
                            "TextColor3": _rgb(255, 255, 255),
                            "TextSize": 18,
                            "FontFace": _font(800),
                            "BorderSizePixel": 0,
                        },
                        "Children": [
                            {"ClassName": "UICorner", "Name": "Corner", "Properties": {"CornerRadius": _udim(0, 8)}}
                        ],
                    },
                    action_button(
                        "BuyStarterPackBtn",
                        "Buy 500G",
                        (56, 130, 246),
                        1,
                        pos=_udim2(0.5, 0, 0.58, 0),
                        anchor=(0.5, 0.5),
                    ),
                ],
            )
        ],
    }

    backdrop_vignette = {
        "ClassName": "ScreenGui",
        "Name": "BackdropVignetteGui",
        "Properties": {
            "DisplayOrder": 0,
            "ScreenInsets": "None",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": True,
        },
        "Children": [],
    }
    topbar_widgets = {
        "ClassName": "ScreenGui",
        "Name": "TopbarWidgetsGui",
        "Properties": {
            "DisplayOrder": 20,
            "ScreenInsets": "TopbarSafeInsets",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": True,
        },
        "Children": [],
    }
    modal_backdrop = {
        "ClassName": "ScreenGui",
        "Name": "ModalBackdropGui",
        "Properties": {
            "DisplayOrder": 49,
            "ScreenInsets": "None",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": False,
        },
        "Children": [
            {
                "ClassName": "TextButton",
                "Name": "Scrim",
                "Properties": {
                    "Size": _udim2(1, 0, 1, 0),
                    "BackgroundColor3": _rgb(6, 10, 18),
                    "BackgroundTransparency": 0.45,
                    "Text": "",
                    "AutoButtonColor": False,
                    "BorderSizePixel": 0,
                },
            }
        ],
    }
    npc_dialog = {
        "ClassName": "ScreenGui",
        "Name": "NpcDialogGui",
        "Properties": {
            "DisplayOrder": 65,
            "ScreenInsets": "CoreUISafeInsets",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": False,
        },
        "Children": [],
    }
    confirm_dialog = {
        "ClassName": "ScreenGui",
        "Name": "ConfirmDialogGui",
        "Properties": {
            "DisplayOrder": 80,
            "ScreenInsets": "CoreUISafeInsets",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": False,
        },
        "Children": [],
    }
    tooltip_gui = {
        "ClassName": "ScreenGui",
        "Name": "FloatingTooltipGui",
        "Properties": {
            "DisplayOrder": 90,
            "ScreenInsets": "CoreUISafeInsets",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": True,
        },
        "Children": [],
    }
    toast_gui = {
        "ClassName": "ScreenGui",
        "Name": "ToastNotificationGui",
        "Properties": {
            "DisplayOrder": 100,
            "ScreenInsets": "CoreUISafeInsets",
            "ResetOnSpawn": False,
            "ZIndexBehavior": "Sibling",
            "Enabled": True,
        },
        "Children": [],
    }

    return [
        backdrop_vignette,
        main_hud,
        topbar_widgets,
        modal_backdrop,
        modal_menus,
        npc_dialog,
        confirm_dialog,
        tooltip_gui,
        toast_gui,
    ]


def generate_standard_gui_rbxmx(
    output_path: str | Path,
    assets: dict[str, Any] | None = None,
) -> str:
    """Write the Standard Game GUI tree as an importable Roblox .rbxmx file."""
    blueprint = build_standard_gui_blueprint(assets=assets)
    return dict_to_rbxmx(blueprint, output_path=output_path)


def generate_standard_gui_luau(
    output_path: str | Path,
    assets: dict[str, Any] | None = None,
) -> str:
    """Write the Standard Game GUI tree as an executable Luau script."""
    blueprint = build_standard_gui_blueprint(assets=assets)
    return dict_to_luau(blueprint, output_path=output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export declarative Roblox GUI blueprints to .rbxmx XML and Luau."
    )
    parser.add_argument("--rbxmx", type=Path, default=None, help="Output .rbxmx file path.")
    parser.add_argument("--luau", type=Path, default=None, help="Output .luau file path.")
    parser.add_argument(
        "--assets-json",
        type=Path,
        default=None,
        help="Optional JSON file containing panel_9slice_id, button_9slice_id, icon_atlas_id, etc.",
    )
    parser.add_argument(
        "--blueprint-json",
        type=Path,
        default=None,
        help="Optional custom GUI tree JSON array instead of built-in Standard Game GUI blueprint.",
    )
    args = parser.parse_args(argv)

    assets: dict[str, Any] | None = None
    if args.assets_json is not None:
        assets = json.loads(args.assets_json.read_text(encoding="utf-8"))

    if args.blueprint_json is not None:
        tree = json.loads(args.blueprint_json.read_text(encoding="utf-8"))
        if not isinstance(tree, list):
            raise ValueError("--blueprint-json must contain a top-level JSON array of instance dicts.")
    else:
        tree = build_standard_gui_blueprint(assets=assets)

    if args.rbxmx is not None:
        dict_to_rbxmx(tree, output_path=args.rbxmx)
        print(f"Wrote .rbxmx GUI to {args.rbxmx}")

    if args.luau is not None:
        dict_to_luau(tree, output_path=args.luau)
        print(f"Wrote .luau GUI builder to {args.luau}")

    if args.rbxmx is None and args.luau is None:
        print(f"Blueprint contains {len(tree)} top-level ScreenGuis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
