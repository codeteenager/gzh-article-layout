#!/usr/bin/env python3
"""Build registered WeChat libraries from the five checked-in design HTML exports.

Uses only the Python standard library. No network, API key, or Tailwind runtime.
Raw exports are evidence, never directly pasted into WeChat.
"""

import copy
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from stitch_themes import (ROOT, LAYOUT_NAMES, declarations, escape_style_attribute,
                           merge_text_leaf_spans)

SOURCE = ROOT / "assets/stitch"
VOID = {"img", "br", "hr", "meta", "link", "input"}
FONT = "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif"
MONO = "'JetBrains Mono','SF Mono',Consolas,Monaco,monospace"
INHERITED_TYPOGRAPHY = {
    "font-family", "font-size", "font-weight", "font-style", "line-height",
    "letter-spacing", "color", "text-align", "overflow-wrap",
}
# These native elements may introduce UA typography or table inheritance resets.
# Always keep their own declarations, even when an ancestor has the same value.
TYPOGRAPHY_BOUNDARIES = {
    "h1", "h2", "h3", "h4", "h5", "h6", "table", "th", "code", "pre",
    "strong", "b", "em", "i", "small", "sub", "sup", "button", "input",
}


def css_tokens(value):
    """Keep functional colors together while splitting simple border values."""
    return re.findall(r"[a-zA-Z-]+\([^()]*\)|#[\da-fA-F]+|[^\s]+", value)


def equivalent_border(pairs):
    """Resolve known border declarations in source order, or leave them alone."""
    sides = ("top", "right", "bottom", "left")
    kinds = ("width", "style", "color")
    styles = {"none", "hidden", "dotted", "dashed", "solid", "double",
              "groove", "ridge", "inset", "outset"}
    state = {side: {} for side in sides}
    used = []
    for index, (key, value) in enumerate(pairs):
        if not key.startswith("border") or key.startswith("border-radius"):
            continue
        if key.startswith("border-image"):
            return pairs
        suffix = key.removeprefix("border").lstrip("-")
        targets = sides
        if suffix in sides or not suffix:
            targets = (suffix,) if suffix else sides
            # Common border shorthands reset unspecified width/style/color.
            result = {"width": "medium", "style": "none", "color": "currentcolor"}
            for token in css_tokens(value):
                if token in styles:
                    result["style"] = token
                elif re.fullmatch(r"(?:0|[\d.]+(?:px|em|rem)|thin|medium|thick)", token):
                    result["width"] = token
                elif re.fullmatch(r"#[\da-fA-F]{3,8}|rgba?\([^()]*\)|[a-zA-Z]+", token):
                    if token in {"inherit", "initial", "unset", "revert"}:
                        return pairs
                    result["color"] = token
                else:
                    return pairs
            for side in targets:
                state[side].update(result)
        elif suffix in kinds:
            tokens = css_tokens(value)
            if not 1 <= len(tokens) <= 4:
                return pairs
            tokens = (tokens * 4)[:4] if len(tokens) in {1, 2} else (
                [tokens[0], tokens[1], tokens[2], tokens[1]] if len(tokens) == 3 else tokens)
            for side, token in zip(sides, tokens):
                state[side][suffix] = token
        elif any(suffix == side + "-" + kind for side in sides for kind in kinds):
            side, kind = suffix.split("-", 1)
            state[side][kind] = value
        else:
            # Corner radii and unsupported border forms are not touched.
            continue
        used.append(index)
    if not used or any(set(state[side]) != set(kinds) for side in sides):
        return pairs
    if any(value in {"inherit", "initial", "unset", "revert", "revert-layer"}
           or "var(" in value for data in state.values() for value in data.values()):
        return pairs
    if all(state[side] == state[sides[0]] for side in sides):
        data = state[sides[0]]
        # Keep invisible style/color too, so later border overrides behave alike.
        replacement = [("border", f'{data["width"]} {data["style"]} {data["color"]}')]
    else:
        replacement = [("border-" + kind, short_box([state[side][kind] for side in sides]))
                       for kind in kinds]
    # Border shorthand resets border-image; absence above makes this safe for the
    # static self-contained libraries. Do not rewrite a group unless it is smaller.
    original = sum(len(pairs[i][0]) + len(pairs[i][1]) + 2 for i in used)
    if sum(len(k) + len(v) + 2 for k, v in replacement) >= original:
        return pairs
    return [pair for i, pair in enumerate(pairs) if i not in used] + replacement


ZERO_LENGTH_PROPERTIES = {
    "margin", "padding", "width", "height", "min-width", "max-width",
    "min-height", "max-height", "gap", "row-gap", "column-gap", "border",
    "border-width", "border-radius", "box-shadow", "letter-spacing",
}


def compact_css_value(key, value):
    if key == "font-family":
        value = re.sub(r"\s*,\s*", ",", value).strip()
        # Only known simple family names: never rewrite arbitrary CSS strings.
        return re.sub(r"'(PingFang SC|Microsoft YaHei|Plus Jakarta Sans|JetBrains Mono|SF Mono)'",
                      r"\1", value)
    if key == "box-shadow":
        # Remove only the exact transparent, zero-size layers in source exports.
        value = re.sub(r"(?:^|(?<=,))\s*rgba\(0,0,0,(?:0(?:\.0)?|\.0)\)\s+0(?:px)?\s+0(?:px)?\s+0(?:px)?\s+0(?:px)?\s*,\s*",
                       "", value)
    if key in ZERO_LENGTH_PROPERTIES or re.fullmatch(
        r"(?:margin|padding)-(?:top|right|bottom|left)|border-(?:top|right|bottom|left)(?:-width)?",
        key,
    ):
        # Never change strings, URL tokens or functions such as calc().
        tokens = re.split(r'("[^"]*"|\'[^\']*\'|[a-zA-Z-]+\([^)]*\))', value)
        for i in range(0, len(tokens), 2):
            tokens[i] = re.sub(r"(?<![\w.#-])0px\b", "0", tokens[i])
        value = "".join(tokens)
    # Do not touch URLs or quoted strings. Color/functions in these templates
    # contain numeric tokens; their decimal and hex forms remain equivalent.
    tokens = re.split(r'("[^"]*"|\'[^\']*\'|url\([^)]*\))', value)
    for i in range(0, len(tokens), 2):
        tokens[i] = re.sub(r"(?<![\w.])0\.(\d)", r".\1", tokens[i])
        tokens[i] = re.sub(r"#([\da-fA-F])\1([\da-fA-F])\2([\da-fA-F])\3\b",
                           r"#\1\2\3", tokens[i])
    return "".join(tokens)


def compact_template_style(style, tag=None, minimal=False):
    pairs = declarations(style)
    # Unknown/custom CSS is not rewritten: these optimizations target the built-in
    # templates, not arbitrary cascading styles or important declarations.
    if any("!important" in value or key.startswith("--") for key, value in pairs):
        return style
    props = dict(equivalent_border(pairs))
    for key, default in {
        "opacity": "1", "box-shadow": "none", "align-items": "normal",
        "justify-content": "normal", "gap": "normal",
    }.items():
        if props.get(key) == default:
            del props[key]
    # Transparent is the initial background, provided no shorthand sets a fill.
    if props.get("background-color") in {"rgba(0,0,0,0.0)", "rgba(0,0,0,0)", "transparent"} and "background" not in props:
        del props["background-color"]
    display = props.get("display", "block")
    if display not in {"flex", "inline-flex"}:
        for key in ("flex-direction", "align-items", "justify-content"):
            props.pop(key, None)
    # flex:0 1 auto already supplies the same explicit flex-shrink.
    if props.get("flex") == "0 1 auto" and props.get("flex-shrink") == "1":
        del props["flex-shrink"]
    sides = ("top", "right", "bottom", "left")
    border_keys = [f"border-{side}-{suffix}" for side in sides
                   for suffix in ("width", "style", "color")]
    if all(key in props for key in border_keys) and not any(
        key in props for key in ("border", "border-top", "border-right", "border-bottom", "border-left",
                                 "border-width", "border-style", "border-color")
    ):
        values = {suffix: [props[f"border-{side}-{suffix}"] for side in sides]
                  for suffix in ("width", "style", "color")}
        if all(value in {"0", "0px"} for value in values["width"]):
            for key in border_keys:
                del props[key]
            props["border"] = "0"
        else:
            for suffix, values in values.items():
                for side in sides:
                    del props[f"border-{side}-{suffix}"]
                props["border-" + suffix] = short_box(values)
    for base in ("padding", "margin"):
        keys = [base + "-" + side for side in sides]
        if all(key in props for key in keys):
            values = [props.pop(key) for key in keys]
            # Fully specified longhands override an earlier shorthand.
            props.pop(base, None)
            props[base] = short_box(values)
    if minimal:
        # This final compiler pass runs AFTER structure merging, which relies on
        # explicit source defaults. Never apply it to arbitrary author HTML.
        if "all" not in props:
            # Non-inherited initial values on ordinary template boxes. Keep
            # shorthand/longhand interactions and native UA resets explicit.
            for key, default in {
                "position": "static", "float": "none", "clear": "none",
                "order": "0", "flex-wrap": "nowrap",
            }.items():
                if props.get(key) == default and not (
                        key == "flex-wrap" and "flex-flow" in props):
                    del props[key]
            if "flex" not in props:
                for key, default in (("flex-grow", "0"), ("flex-shrink", "1")):
                    if props.get(key) == default:
                        del props[key]
            if props.get("overflow") == "visible" and not any(
                    key in props for key in ("overflow-x", "overflow-y")):
                del props["overflow"]
            if tag in {"section", "span"}:
                for key in ("margin", "margin-top", "margin-right",
                            "margin-bottom", "margin-left"):
                    if props.get(key) in {"0", "0px"} and (
                            (key == "margin" and not any(
                                name.startswith("margin-") for name in props)) or
                            (key != "margin" and "margin" not in props and not any(
                                name.startswith(("margin-inline", "margin-block"))
                                for name in props))):
                        del props[key]
            if tag in {"section", "span", "p"} and (
                    props.get("border") in {"0", "0px", "none"} or
                    re.fullmatch(r"0(?:px)? solid #[\da-fA-F]{6}", props.get("border", ""))):
                # These tags have no native border. Do not drop resets that
                # interact with side borders or border-image painting.
                if not any(key.startswith("border-") and key != "border-radius"
                           for key in props):
                    del props["border"]
        if re.fullmatch(r"0(?:px)? solid #[\da-fA-F]{6}", props.get("border", "")):
            if not any(key.startswith("border-") and key != "border-radius"
                       for key in props):
                props["border"] = "0"
        if (props.get("flex") == "0 1 auto" and
                all(props.get(key, default) == default for key, default in
                    (("flex-grow", "0"), ("flex-shrink", "1"), ("flex-basis", "auto")))):
            del props["flex"]
        if props.get("flex-direction") == "row":
            del props["flex-direction"]
        if props.get("flex") == "0 0 auto":
            props["flex"] = "none"
            if props.get("flex-shrink") == "0":
                del props["flex-shrink"]
        if props.get("border-radius") in {"0", "0px"}:
            del props["border-radius"]
        if tag == "section":
            if props.get("display") == "block":
                del props["display"]
            if props.get("padding") in {"0", "0px"}:
                del props["padding"]
        if tag == "span":
            for key in ("padding", "margin", "margin-top", "margin-bottom"):
                if (props.get(key) == "0" and not
                        (key in {"margin-top", "margin-bottom"} and
                         props.get("margin", "0") != "0")):
                    del props[key]
            geometry = ("width", "height", "min-width", "max-width",
                        "min-height", "max-height", "padding", "border-width",
                        "border-left", "border-bottom", "border-top", "border-right")
            if (not any(key in props and props[key] not in {"0", "auto", "none"}
                        for key in geometry) and props.get("border", "0") == "0" and
                    not any(key.startswith(("padding-", "border-")) for key in props)):
                props.pop("box-sizing", None)
        if "background-color" in props and not any(
                key.startswith("background") and key != "background-color" for key in props):
            props["background"] = props.pop("background-color")
        if (props.get("border-width") == "0 0 0 6px" and props.get("border-style") == "solid" and
                not any(key.startswith("border-image") for key in props)):
            colors = css_tokens(props.get("border-color", ""))
            if len(colors) == 4:
                del props["border-width"]
                del props["border-style"]
                del props["border-color"]
                props["border"] = "0"
                props["border-left"] = "6px solid " + colors[-1]
        # Auto-sized, borderless boxes have identical used dimensions regardless
        # of box-sizing. Keep explicit geometry and unknown longhands intact.
        if tag in {"section", "span", "p"}:
            geometry = ("width", "height", "min-width", "max-width",
                        "min-height", "max-height", "padding")
            if (props.get("border", "0") == "0" and
                    not any(key in props and props[key] not in {"0", "auto", "none"}
                            for key in geometry) and
                    not any(key.startswith(("padding-", "border-")) and key != "border-radius"
                            for key in props)):
                props.pop("box-sizing", None)
    return ";".join(key + ":" + compact_css_value(key, value)
                    for key, value in props.items()) + ";"


def short_box(values):
    top, right, bottom, left = values
    if right == left:
        if top == bottom:
            return top if top == right else top + " " + right
        return " ".join((top, right, bottom))
    return " ".join(values)


def minimize_template_declarations(value):
    """Final, bounded declaration folding; never optimize filled article HTML.

    Resolve physical spacing in declaration order, without inventing unspecified
    sides. Logical properties, CSS-wide values, functions and important rules
    deliberately keep their original serialization.
    """
    def minimize(match):
        original = html.unescape(match[1])
        pairs = declarations(original)
        if any(key in {"all", "direction", "writing-mode"} or key.startswith("--")
               or "!important" in val for key, val in pairs):
            return match[0]
        # Only identical simple solid colors: do not infer equivalence for
        # gradients, images, CSS-wide values or other background longhands.
        backgrounds = [(i, val) for i, (key, val) in enumerate(pairs)
                       if key == "background"]
        if len(backgrounds) == 1:
            index, color = backgrounds[0]
            if re.fullmatch(r"#[\da-fA-F]{3,8}", color):
                pairs = [(key, val) for i, (key, val) in enumerate(pairs)
                         if not (key == "background-color" and
                                 i < index and val.lower() == color.lower())]
        for base in ("margin", "padding"):
            keys = [base + "-" + side for side in ("top", "right", "bottom", "left")]
            relevant = [(i, key, val) for i, (key, val) in enumerate(pairs)
                        if key == base or key.startswith(base + "-")]
            if not relevant or any(key not in [base] + keys for _, key, _ in relevant):
                continue
            resolved = {}
            valid = True
            for _, key, val in relevant:
                tokens = val.split()
                if (not 1 <= len(tokens) <= (4 if key == base else 1) or
                        not all(re.fullmatch(r"(?:auto|0|[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:px|em|rem|%))",
                                             token) for token in tokens) or
                        (base == "padding" and any(
                            token == "auto" or token.startswith("-") for token in tokens))):
                    valid = False
                    break
                if key == base:
                    top = tokens[0]
                    right = tokens[1] if len(tokens) > 1 else top
                    bottom = tokens[2] if len(tokens) > 2 else top
                    left = tokens[3] if len(tokens) > 3 else right
                    resolved.update(zip(keys, (top, right, bottom, left)))
                else:
                    resolved[key] = val
            if not valid or len(resolved) != 4:
                continue
            replacement = (base, short_box([resolved[key] for key in keys]))
            # Do not expand already shorter forms or change unrelated ordering.
            old_size = sum(len(key) + len(val) + 2 for _, key, val in relevant)
            if len(replacement[0]) + len(replacement[1]) + 2 >= old_size:
                continue
            indices = {i for i, _, _ in relevant}
            last = relevant[-1][0]
            pairs = [replacement if i == last else pair
                     for i, pair in enumerate(pairs) if i not in indices or i == last]

        # A complete, known flex shorthand resets all three longhands. Remove
        # earlier overrides, or later ones only when they equal the shorthand.
        flexes = [(i, val) for i, (key, val) in enumerate(pairs) if key == "flex"]
        if len(flexes) == 1:
            index, flex = flexes[0]
            tokens = flex.split()
            if flex == "none":
                tokens = ["0", "0", "auto"]
            elif flex == "auto":
                tokens = ["1", "1", "auto"]
            if (len(tokens) == 3 and
                    all(re.fullmatch(r"\d+(?:\.\d+)?", t) for t in tokens[:2]) and
                    re.fullmatch(r"auto|0|(?:\d+(?:\.\d+)?|\.\d+)(?:px|%)", tokens[2])):
                contract = dict(zip(("flex-grow", "flex-shrink", "flex-basis"), tokens))
                pairs = [(key, val) for i, (key, val) in enumerate(pairs)
                         if key not in contract or not (i < index or val == contract[key])]
        result = ";".join(key + ":" + val for key, val in pairs) + ";"
        # Style attributes can be entity-encoded; compare the actual serialized
        # sizes so a nominal CSS win cannot make the HTML larger.
        replacement = 'style="' + escape_style_attribute(result) + '"'
        return replacement if len(replacement) < len(match[0]) else match[0]

    # SVG is provenance-sensitive and has a separate geometry/paint contract.
    return re.sub(r"<svg\b.*?</svg>|\bstyle=\"([^\"]*)\"",
                  lambda m: m[0] if m[1] is None else minimize(m), value, flags=re.S)


def allocate_template_fonts(value, property_name="font-family"):
    """Allocate independent inherited typography before slot fill.

    Dynamic slots and inline/native elements are observation points: their exact
    original font property must survive. Only inert block ancestors may change it.
    Unknown inherited fonts are symbolic, never guessed from a local machine.
    SVG and native font boundaries remain opaque.
    """
    if property_name not in {"font-family", "font-weight", "font-style",
                             "letter-spacing", "color"}:
        raise ValueError("Only independent inherited typography is supported")
    for match in re.finditer(r'\bstyle="([^"]*)"', value):
        pairs = declarations(html.unescape(match[1]))
        if any(k in {"font", "all"} or "!important" in v or
               (k == property_name and (v.lower() in {
                   "inherit", "initial", "unset", "revert", "revert-layer",
                   "currentcolor", "bolder", "lighter"
               } or "var(" in v.lower() or
                   (property_name == "letter-spacing" and
                    v != "normal" and not re.fullmatch(r"(?:0|[-+]?[\d.]+px)", v))))
               for k, v in pairs):
            return value
    class Tree(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.root = {"children": [], "font": None, "pairs": []}
            self.stack = [self.root]

        def handle_starttag(self, tag, attrs):
            raw = self.get_starttag_text()
            pairs = declarations(dict(attrs).get("style", ""))
            props = dict(pairs)
            parent = self.stack[-1]
            node = dict(tag=tag, raw=raw, pairs=pairs, children=[],
                        font=props.get(property_name, parent["font"]), end="",
                        flex_item=dict(parent["pairs"]).get("display") in {"flex", "inline-flex"})
            parent["children"].append(node)
            if tag not in VOID:
                self.stack.append(node)

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if tag not in VOID:
                self.stack.pop()

        def handle_endtag(self, tag):
            self.stack[-1]["end"] = "</" + tag + ">"
            self.stack.pop()

        def handle_data(self, text):
            self.stack[-1]["children"].append(text)

        def handle_entityref(self, name):
            self.handle_data("&" + name + ";")

        def handle_charref(self, name):
            self.handle_data("&#" + name + ";")

        def handle_comment(self, text):
            self.handle_data("<!--" + text + "-->")

    # Work on static fragments only. Keeping native subtrees opaque also avoids
    # relying on UA font defaults or reserializing SVG.
    fragments = []
    def protect(match):
        fragments.append(match[0])
        return "GZH_FONT_OPAQUE_%d_TOKEN" % (len(fragments) - 1)
    value = re.sub(r"<(svg|table|h[1-6]|pre|code|strong|b|em|i|small|sub|sup)\b[^>]*>.*?</\1>",
                   protect, value, flags=re.S)
    tree = Tree()
    tree.feed(value)
    if len(tree.stack) != 1:
        raise ValueError("Unbalanced static component")
    root_ids = {id(n) for n in tree.root["children"] if isinstance(n, dict)}
    unknown_font = any(n["font"] is None for n in tree.root["children"]
                       if isinstance(n, dict))

    memo = {}
    def solve(node, inherited):
        if isinstance(node, str):
            return node
        cache_key = (id(node), inherited)
        if cache_key in memo:
            return memo[cache_key]
        # A block without direct text has no font-sensitive inline line box.
        props = dict(node["pairs"])
        movable = (id(node) not in root_ids and (node["tag"] == "section" or
                    (node["tag"] == "span" and not node["children"] and
                     (props.get("display") == "block" or node["flex_item"]))) and not any(
            isinstance(c, str) and c.strip() for c in node["children"]) and
            not any(k in props for k in ("font", "all")) and
            not any(re.search(r"[\d.](?:em|ex|ch|lh)\b|%|!important|var\(", v)
                    for k, v in node["pairs"] if k != property_name))
        if property_name == "color":
            # A textless box can still paint with currentColor. Keep its color
            # fixed unless every border is absent and shadow color is explicit.
            movable = movable and not any(
                "currentcolor" in v.lower() or
                (k.startswith("border") and k != "border-radius" and
                 v not in {"0", "none"}) or
                k in {"outline", "outline-color", "text-decoration",
                      "text-decoration-color", "filter"} or
                (k == "box-shadow" and v != "none" and
                 not re.search(r"#[\da-fA-F]+|rgba?\(", v))
                for k, v in node["pairs"])
        candidates = {node["font"]}
        if movable and not unknown_font:
            candidates.add(inherited)
            def fonts(n):
                if isinstance(n, dict):
                    candidates.add(n["font"])
                    for c in n["children"]:
                        fonts(c)
            fonts(node)
        options = []
        for font in candidates:
            if font is None and inherited is not None:
                continue  # no CSS spelling for an unknown ancestor font
            pairs = [(k, v) for k, v in node["pairs"] if k != property_name]
            if font != inherited:
                pairs.append((property_name, font))
            style = ";".join(k + ":" + v for k, v in pairs)
            raw = re.sub(r'\sstyle="[^"]*"', "", node["raw"], count=1)
            if style:
                raw = raw[:-1] + ' style="' + escape_style_attribute(style + ";") + '">'
            result = raw + "".join(solve(c, font) for c in node["children"]) + node["end"]
            options.append(result)
        memo[cache_key] = min(options, key=lambda s: (len(s.encode()), s))
        return memo[cache_key]

    result = "".join(solve(n, None) if isinstance(n, dict) else n
                     for n in tree.root["children"])
    for index, fragment in enumerate(fragments):
        result = result.replace("GZH_FONT_OPAQUE_%d_TOKEN" % index, fragment)
    return result


class TemplateStyleCleaner(HTMLParser):
    """Reuse typography only inside one static component, never across slots."""

    def __init__(self, minimal=False, inherited=None):
        super().__init__(convert_charrefs=False)
        self.minimal = minimal
        self.output = []
        self.stack = []
        self.layouts = []
        self.inherited = inherited or {}

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text()
        style = dict(attrs).get("style")
        inherited = dict(self.stack[-1][1]) if self.stack else dict(self.inherited)
        effective = dict(inherited)
        if tag in TYPOGRAPHY_BOUNDARIES:
            # Unknown native defaults must not be propagated to descendants.
            effective = {}
        if style is not None:
            compact = compact_template_style(style, tag=tag, minimal=self.minimal)
            pairs = declarations(compact)
            props = dict(pairs)
            original_display = props.get("display")
            if self.minimal:
                # A flex item is blockified by its parent. Do not apply this to
                # arbitrary descendants or change inline-flex/internal layout.
                if (self.layouts and self.layouts[-1] in {"flex", "inline-flex"}
                        and props.get("display") == "block" and
                        props.get("position", "static") == "static" and
                        props.get("float", "none") == "none"):
                    props.pop("display")
                # With no padding or border, border/content-box have identical
                # geometry even when a width/min-width/height is specified.
                if (tag in {"section", "span", "p"} and props.get("border", "0") == "0"
                        and props.get("padding", "0") == "0"
                        and not any(k.startswith("padding-") or
                                    (k.startswith("border-") and k != "border-radius")
                                    for k in props)
                        and not any(k in props for k in ("all", "aspect-ratio"))
                        and not any("!important" in v for v in props.values())):
                    props.pop("box-sizing", None)
                pairs = list(props.items())
            if not any(key in props for key in ("font", "all")) and not any(
                "!important" in value or "var(" in value or value in {
                    "inherit", "initial", "unset", "revert", "revert-layer"
                } for _, value in pairs
            ):
                effective.update({key: value for key, value in pairs
                                  if key in INHERITED_TYPOGRAPHY})
                if tag not in TYPOGRAPHY_BOUNDARIES:
                    pairs = [(key, value) for key, value in pairs
                             if key not in INHERITED_TYPOGRAPHY or
                             value != inherited.get(key) or
                             (key in {"font-size", "letter-spacing", "line-height"}
                              and re.search(r"(?:em|ex|ch|lh)\b|%", value))]
                compact = ";".join(key + ":" + value for key, value in pairs) + ";"
            else:
                effective = {}
            raw = re.sub(r"\sstyle\s*=\s*(\"[^\"]*\"|'[^']*')",
                         lambda _: (' style="' + escape_style_attribute(compact) + '"'
                                    if compact.strip(";") else ""),
                         raw, count=1)
        self.output.append(raw)
        if tag not in VOID:
            self.stack.append((tag, effective))
            self.layouts.append(original_display if style is not None else None)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()
            self.layouts.pop()

    def handle_endtag(self, tag):
        self.output.append("</" + tag + ">")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                del self.layouts[index:]
                break

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append("&" + name + ";")

    def handle_charref(self, name):
        self.output.append("&#" + name + ";")

    def handle_comment(self, data):
        self.output.append("<!--" + data + "-->")


def clean_template_styles(value, minimal=False, inherited=None):
    # Protect complete SVG source, including formatting of closing tags.
    fragments, ranges, depth, start = [], [], 0, None
    for match in re.finditer(r"</?svg\b[^>]*>", value):
        if match[0].startswith("</"):
            depth -= 1
            if depth == 0:
                ranges.append((start, match.end()))
        else:
            if depth == 0:
                start = match.start()
            depth += 1
    protected = value
    for start, end in reversed(ranges):
        index = len(fragments)
        fragments.append(value[start:end])
        protected = protected[:start] + f"<!--GZH_SVG_PRESERVE_{index}-->" + protected[end:]
    parser = TemplateStyleCleaner(minimal=minimal, inherited=inherited)
    parser.feed(protected)
    parser.close()
    # Only empty leaf nodes, never wrappers with meaningful typography/layout.
    result = re.sub(r'<span leaf=""></span>', "", "".join(parser.output))
    for index, fragment in enumerate(fragments):
        result = result.replace(f"<!--GZH_SVG_PRESERVE_{index}-->", fragment)
    return result


def merge_component_spacing(value):
    """Fold the compiler's spacing wrapper into one zero-margin block.

    Only the wrapper introduced by compile_templates is eligible. Keep source
    markup (including SVG and dynamic slots) untouched; do not reserialize it.
    Explicit widths, positioning and nonzero margins retain their wrappers.
    """
    prefix = '<section style="margin:0 0 24px;">'
    if not value.startswith(prefix) or not value.endswith("</section>"):
        return value
    inner = value[len(prefix):-len("</section>")]
    root = re.match(r'<(?P<tag>section|figure) style="(?P<style>[^"]*)">', inner)
    if not root:
        return value
    # One root, not two siblings accidentally matched by the final closing tag.
    depth = 0
    for token in re.finditer(r'</?(?:section|figure)\b[^>]*>', inner):
        depth += -1 if token[0].startswith("</") else 1
        if depth == 0 and token.end() != len(inner):
            return value
    if depth != 0:
        return value
    pairs = declarations(html.unescape(root["style"]))
    props = dict(pairs)
    if props.get("display") not in {"block", "flex"}:
        return value
    if any(key in props for key in (
            "width", "min-width", "max-width", "height", "min-height",
            "max-height", "position", "float", "transform")):
        return value
    margins = [(key, val) for key, val in pairs if key.startswith("margin")]
    if any(val not in {"0", "0px"} for key, val in margins):
        return value
    if props.get("margin-top", props.get("margin")) not in {"0", "0px"}:
        return value
    if props.get("margin-bottom", props.get("margin")) not in {"0", "0px"}:
        return value
    # Preserve the original serialization of all other properties, notably fonts.
    style = re.sub(r'(?:^|;)(margin(?:-top|-bottom|-left|-right)?):(?:0|0px)(?=;|$)',
                   "", root["style"])
    style = style.strip(";") + ";margin:0 0 24px;"
    return (f'<{root["tag"]} style="{style}">' + inner[root.end():])


def merge_quote_layout(value):
    """Move a quote's undecorated flex row onto its surrounding card."""
    match = re.fullmatch(
        r'<section style="([^"]*)"><section style="([^"]*)">(.*)</section></section>',
        value, flags=re.S)
    if not match:
        return value
    outer = dict(declarations(html.unescape(match[1])))
    child = dict(declarations(html.unescape(match[2])))
    expected = {
        "box-sizing": "border-box", "display": "flex", "gap": "12px",
        "flex-direction": "row", "flex": "0 1 auto", "margin-top": "0",
        "margin-bottom": "0", "border-radius": "0",
        "border": "0 solid #e5e7eb", "padding": "0",
    }
    if outer.get("display") != "block" or child != expected:
        return value
    # Do not match sibling sections as though they were one enclosing row.
    depth = 0
    for token in re.finditer(r'</?section\b[^>]*>', match[3]):
        depth += -1 if token[0].startswith("</") else 1
        if depth < 0:
            return value
    if depth:
        return value
    style = match[1].replace("display:block;", "display:flex;gap:12px;flex-direction:row;")
    return '<section style="' + style + '">' + match[3] + '</section>'


def merge_table_spacing(value):
    """A full-width border-box scroll frame can own its block spacing.

    Unlike arbitrary explicit-width cards, this exact frame fills the same
    containing block before and after merging. Never generalize to figures or
    frames with padding, horizontal margins, or alternative width constraints.
    """
    prefix = '<section style="margin:0 0 24px;">'
    if not value.startswith(prefix) or not value.endswith("</section>"):
        return value
    inner = value[len(prefix):-len("</section>")]
    match = re.match(r'<section style="([^"]*)">', inner)
    if not match or len(re.findall(r"<table\b", inner)) != 1:
        return value
    props = dict(declarations(html.unescape(match[1])))
    if (props.get("width") != "100%" or props.get("box-sizing") != "border-box"
            or props.get("overflow-x") != "auto" or props.get("margin") != "0"
            or any(k.startswith(("padding", "min-", "max-")) or
                   k in {"position", "float", "transform", "height", "display"} for k in props)
            or any(k.startswith("margin-") for k in props)):
        return value
    style = match[1].replace("margin:0;", "margin:0 0 24px;")
    return '<section style="' + style + '">' + inner[match.end():]


def optimize_template_structure(value):
    """Remove text-only span wrappers without altering the styled element."""
    value = merge_text_leaf_spans(value)
    # Same SVG primitives and geometry; only serialize equivalent attributes.
    def svg(match):
        source = match[0]
        source = re.sub(r'fill="rgb\((\d+),\s*(\d+),\s*(\d+)\)"',
                        lambda m: 'fill="#%02x%02x%02x"' % tuple(map(int, m.groups())),
                        source)
        source = re.sub(r'\sfill-opacity="1(?:\.0+)?"', "", source)
        source = re.sub(r'(<rect\b[^>]*?)\sy="0"', r'\1', source)
        source = re.sub(r'(<rect\b[^>]*?)\sx="0"', r'\1', source)
        return source
    value = re.sub(r'<svg\b.*?</svg>', svg, value, flags=re.S)
    return merge_component_spacing(value)


class Node:
    def __init__(self, tag, attrs=(), children=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = children or []

    def nodes(self, tag=None):
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.nodes(tag)

    def text(self):
        return "".join(c.text() if isinstance(c, Node) else c for c in self.children)

    def elements(self):
        return [c for c in self.children if isinstance(c, Node)]


class Parser(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]
        self.feed(text)
        for node in self.root.nodes():
            node.source_key = (node.tag, node.attrs.get("class", ""), node.attrs.get("style", ""), node.text().strip()[:80])

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def load(slug):
    return Parser((SOURCE / (slug + ".html")).read_text(encoding="utf-8")).root


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def extract_catalog():
    rows = list(load("color-gallery").nodes("tr"))[1:]
    themes = []
    for i, row in enumerate(rows):
        cells = [n.text().strip() for n in row.elements()]
        if len(cells) != 8:
            raise ValueError("Design color table schema changed")
        _, name, slug, primary, accent, surface, deep, scene = cells
        themes.append(dict(
            id=slug, name=name.replace("【", "").replace("】", ""),
            primary=primary.upper(), accent=accent.upper(),
            surface=surface.upper(), deep=deep.upper(), scene=scene,
            layout=("ruler", "overprint", "pure")[i % 3],
        ))
    if len(themes) != 15:
        raise ValueError("Expected exactly 15 source colorways")
    return themes


def original_tokens():
    text = (SOURCE / "ruler.html").read_text(encoding="utf-8")
    section = text.split('colors: {', 1)[1].split('}, borderRadius', 1)[0]
    return dict(re.findall(r'"([a-z-]+)": "(#[a-f0-9]+)"', section))


def resolved_styles(viewport=390):
    provenance = json.loads((SOURCE / "resolved-manifest.json").read_text())
    for files in provenance["sources"].values():
        for name, digest in files.items():
            if hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Resolved style provenance mismatch: " + name)
    result = {}
    for slug in ("components", "pure", "overprint", "ruler"):
        for item in json.loads((SOURCE / ("resolved-" + slug + ("-desktop" if viewport == 677 else "") + ".json")).read_text()):
            result[(item["tag"], item["class"], item["inline"], item["text"])] = item["css"]
    return result


RESOLVED = resolved_styles()
RESOLVED_DESKTOP = resolved_styles(677)


def icon_svg(name, size, color):
    if name == "engagement_bookmark":
        # Stroke-based SVG returned by Stitch, separate from bundled glyphs.
        source = (SOURCE / "engagement-bookmark" / "bookmark.svg").read_text().strip()
        source = source.replace('width="24"', 'width="%s"' % size)
        source = source.replace('height="24"', 'height="%s"' % size)
        return source.replace('stroke="currentColor"', 'stroke="%s"' % color).replace(
            '<svg ', '<svg style="display:block;flex-shrink:0;" ', 1)
    source = (SOURCE / "icons" / (name + ".svg")).read_text()
    source = re.sub(r'width="24"', 'width="%s"' % size, source)
    source = re.sub(r'height="24"', 'height="%s"' % size, source)
    return source.replace('<svg ', '<svg style="display:block;flex-shrink:0;" fill="%s" ' % color, 1)


def semantic_palette(theme):
    """Derive distinct semantic roles without changing the source color catalog."""
    def mix(first, second, weight):
        a = [int(first[i:i+2], 16) for i in (1, 3, 5)]
        b = [int(second[i:i+2], 16) for i in (1, 3, 5)]
        return "#" + "".join("%02X" % round(x * weight + y * (1 - weight))
                             for x, y in zip(a, b))
    return {
        "card_surface": theme["surface"],
        "emphasis_surface": mix(theme["accent"], theme["surface"], .55),
        "highlight_surface": mix(theme["accent"], theme["surface"], .35),
        "on_deep_muted": mix(theme["accent"], "#FFFFFF", .35),
    }


class Compiler:
    """A deliberately bounded compiler for the utilities used by these exports."""

    def __init__(self, theme, viewport=390):
        self.theme = theme
        self.viewport = viewport
        self.resolved = RESOLVED_DESKTOP if viewport == 677 else RESOLVED
        self.colors = original_tokens()
        self.colors.update(white="#FFFFFF", transparent="transparent")
        self.original = theme["id"] == "__source"
        if not self.original:
            palette = semantic_palette(theme)
            for key in ("primary", "primary-container", "secondary", "on-primary-fixed-variant", "on-secondary-fixed-variant", "surface-tint"):
                self.colors[key] = theme["primary"]
            for key in ("secondary-fixed-dim", "primary-fixed-dim", "inverse-primary"):
                self.colors[key] = theme["accent"]
            self.colors["surface-container-low"] = palette["card_surface"]
            self.colors["secondary-container"] = palette["emphasis_surface"]
            for key in ("secondary-fixed", "primary-fixed"):
                self.colors[key] = palette["highlight_surface"]
            for key in ("on-secondary-container", "on-secondary-fixed", "on-primary-fixed"):
                self.colors[key] = theme["deep"]
        self.colors.update({"#e6f4ea": "#e6f4ea" if self.original else theme["surface"],
                            "#a3e0be": "#a3e0be" if self.original else theme["accent"],
                            "#047857": "#047857" if self.original else theme["primary"]})

    def remap(self, value):
        if self.original:
            return value
        replacements = {color: self.colors[token]
                        for token, color in original_tokens().items()}
        replacements.update({"#062e24": self.theme["deep"], "#059669": self.theme["primary"],
                             "#10b981": self.theme["accent"], "#f2faf6": self.theme["surface"],
                             "#005236": self.theme["primary"],
                             "#a7f3d0": semantic_palette(self.theme)["on_deep_muted"],
                             "#34d399": self.theme["accent"], "#064e3b": self.theme["deep"],
                             "#e6f4ea": self.theme["surface"], "#a3e0be": self.theme["accent"],
                             "#047857": self.theme["primary"]})
        def change(match):
            v = match[0]
            if v.startswith("rgb"):
                nums = [float(x) for x in re.findall(r"[\d.]+", v)]
                key = "#%02x%02x%02x" % tuple(int(n) for n in nums[:3])
                new = replacements.get(key, key)
                if len(nums) == 4:
                    rgb = [int(new[i:i+2], 16) for i in (1,3,5)]
                    return "rgba(%s,%s)" % (",".join(map(str,rgb)), nums[3])
                return new
            return replacements.get(v.lower(), v)
        return re.sub(r"rgba?\([^)]*\)|#[a-fA-F0-9]{6}", change, value)

    def gradient_svg(self, value):
        colors = re.findall(r"rgba?\([^)]*\)|#[a-fA-F0-9]{6}|transparent", value)
        if len(colors) < 2:
            return ""
        def rgba(c):
            if c == "transparent": return (0,0,0,0)
            if c.startswith("#"): return tuple(int(c[i:i+2],16) for i in (1,3,5)) + (1,)
            nums = tuple(float(n) for n in re.findall(r"[\d.]+",c))
            return nums if len(nums)==4 else nums+(1,)
        stops = [rgba(c) for c in colors]
        parts = []
        for i in range(64):
            t = i / 63 * (len(stops)-1); k = min(int(t),len(stops)-2); f=t-k
            v = [stops[k][j]*(1-f)+stops[k+1][j]*f for j in range(4)]
            parts.append('<rect x="%s" y="0" width="1.05" height="1" fill="rgb(%s)" fill-opacity="%.4f"/>' % (i, ",".join(str(round(x)) for x in v[:3]),v[3]))
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 1" preserveAspectRatio="none" width="100%%" height="100%%" style="display:block;">%s</svg>' % "".join(parts)

    def color(self, value):
        value = value.replace("[", "").replace("]", "")
        key, _, alpha = value.partition("/")
        color = self.colors.get(key, key if key.startswith("#") else None)
        if color is None:
            raise ValueError("Unknown source color: " + value)
        if alpha and color.startswith("#"):
            rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
            alpha = alpha.strip("[]")
            opacity = float(alpha) if "." in alpha else float(alpha) / 100
            return "rgba(%s,%s)" % (",".join(map(str, rgb)), format(opacity, ".3g"))
        return color

    def utility(self, c):
        if ":" in c and not c.startswith("["):
            return {}
        fixed = {
            "flex": {"display": "flex"}, "inline-flex": {"display": "inline-flex"},
            "grid": {"display": "flex", "flex-direction": "column"},
            "flex-col": {"flex-direction": "column"}, "flex-row": {"flex-direction": "row"},
            "flex-wrap": {"flex-wrap": "wrap"}, "flex-1": {"flex": "1", "min-width": "0"},
            "shrink-0": {"flex-shrink": "0"}, "items-center": {"align-items": "center"},
            "items-start": {"align-items": "flex-start"}, "self-end": {"align-self": "flex-end"},
            "justify-between": {"justify-content": "space-between"},
            "justify-center": {"justify-content": "center"}, "justify-end": {"justify-content": "flex-end"},
            "overflow-hidden": {"overflow": "hidden"}, "overflow-x-auto": {"overflow-x": "auto"},
            "rounded": {"border-radius": "4px"}, "rounded-lg": {"border-radius": "8px"},
            "rounded-xl": {"border-radius": "12px"}, "rounded-2xl": {"border-radius": "16px"},
            "rounded-full": {"border-radius": "9999px"}, "rounded-l-xl": {"border-radius": "12px 0 0 12px"},
            "border": {"border": "1px solid #E4E4E7"}, "border-b": {"border-bottom": "1px solid #E4E4E7"},
            "border-t": {"border-top": "1px solid #E4E4E7"},
            "font-medium": {"font-weight": "500"}, "font-semibold": {"font-weight": "600"},
            "font-bold": {"font-weight": "700"}, "font-extrabold": {"font-weight": "800"},
            "italic": {"font-style": "italic"}, "opacity-80": {"opacity": "0.8"},
            "leading-none": {"line-height": "1"}, "leading-tight": {"line-height": "1.25"},
            "leading-snug": {"line-height": "1.375"}, "leading-normal": {"line-height": "1.5"},
            "leading-relaxed": {"line-height": "1.625"}, "leading-loose": {"line-height": "2"},
            "tracking-tighter": {"letter-spacing": "-0.05em"}, "tracking-tight": {"letter-spacing": "-0.025em"},
            "tracking-wide": {"letter-spacing": "0.025em"}, "tracking-wider": {"letter-spacing": "0.05em"},
            "tracking-widest": {"letter-spacing": "0.1em"}, "list-none": {"list-style": "none"},
            "shadow-xs": {"box-shadow": "0 1px 2px rgba(0,0,0,0.04)"},
            "shadow-sm": {"box-shadow": "0 1px 3px rgba(0,0,0,0.08)"},
            "shadow-md": {"box-shadow": "0 4px 6px rgba(0,0,0,0.08)"},
            "mx-auto": {"margin-left": "auto", "margin-right": "auto"},
        }
        if c in fixed:
            return fixed[c]
        if c in {"relative", "absolute", "top-0", "bottom-0", "left-0", "right-0", "left-1/2",
                 "-top-3", "-bottom-0.5", "-translate-x-1/2", "z-10", "group", "grid-cols-1",
                 "grid-cols-3", "animate-pulse", "pointer-events-none", "select-none", "antialiased",
                 "line-clamp-2", "truncate", "no-scrollbar", "cursor-pointer", "material-symbols-outlined"}:
            return {}
        if c.startswith(("transition-", "from-", "via-", "to-")):
            return {}
        if c.startswith("bg-gradient-"):
            return {"background": self.theme["primary"]}
        if c.startswith("shadow-["):
            return {"box-shadow": c[8:-1].replace("_", " ")}
        if c in {"text-left", "text-right", "text-center"}:
            return {"text-align": c[5:]}
        if c.startswith("font-"):
            return {"font-family": MONO if c == "font-code" else FONT}
        sizes = {
            "body-editorial": ("14px", "26.6px"), "body-lg": ("15px", "28px"),
            "body-sm": ("13px", "20px"), "caption": ("12px", "18px"), "code": ("13px", "22px"),
            "headline-hero-mobile": ("26px", "34px"), "headline-hero": ("36px", "44px"),
            "headline-lg": ("22px", "32px"), "headline-md": ("18px", "28px"),
            "headline-sm": ("16px", "24px"), "label-pill": ("12px", "16px"),
        }
        if c.startswith("text-"):
            val = c[5:]
            if val in sizes:
                result = dict(zip(("font-size", "line-height"), sizes[val]))
                if val == "body-editorial": result.update({"letter-spacing":"0.5px", "font-weight":"400"})
                return result
            if val.startswith("[") and re.match(r"\[\d+px\]", val):
                return {"font-size": val[1:-1]}
            return {"color": self.color(val)}
        if c.startswith("bg-"):
            return {"background": self.color(c[3:])}
        if c.startswith("border-"):
            return {"border-color": self.color(c[7:])}
        match = re.fullmatch(r"(-?)(p[xytrbl]?|m[xytrbl]?|gap|w|h|min-w|max-w)-(.+)", c)
        if match:
            sign, prop, val = match.groups()
            named = {"margin": "16px", "space-xs": "4px", "space-sm": "8px", "space-md": "16px",
                     "space-lg": "24px", "space-xl": "32px"}
            if val in named:
                amount = named[val]
            elif val.startswith("["):
                amount = val[1:-1]
            elif val == "full":
                amount = "100%"
            else:
                amount = "%gpx" % (float(val) * 4)
            if sign:
                amount = "-" + amount
            if prop in {"w", "h", "min-w", "max-w", "gap"}:
                return {{"w": "width", "h": "height", "min-w": "min-width", "max-w": "max-width", "gap": "gap"}[prop]: amount}
            base = "padding" if prop[0] == "p" else "margin"
            suffix = prop[1:]
            if not suffix:
                return {base: amount}
            sides = {"x": ("left", "right"), "y": ("top", "bottom"),
                     "t": ("top",), "r": ("right",), "b": ("bottom",), "l": ("left",)}[suffix]
            return {base + "-" + side: amount for side in sides}
        raise ValueError("Unknown source utility: " + c)

    def render(self, node, grid_child=False, ornament=None):
        if isinstance(node, str):
            text = re.sub(r"\s+", " ", node).strip()
            return '<span leaf="">%s</span>' % html.escape(text) if text else ""
        if node.tag in {"script", "style", "link"}:
            return ""
        classes = node.attrs.get("class", "").split()
        text = node.text().strip()
        if "absolute" in classes and not text and "bg-gradient-to-r" not in classes:
            return ""
        styles = {"box-sizing": "border-box"}
        if node.tag in {"p", "h1", "h2", "h3", "h4", "figure", "blockquote", "pre"}:
            styles["margin"] = "0"
        for c in classes:
            styles.update(self.utility(c))
        inline = node.attrs.get("style", "")
        resolved = self.resolved.get(getattr(node, "source_key", None))
        if resolved:
            styles.update(resolved)
            if styles.get("display") == "grid":
                styles.update(display="flex", **{"flex-direction":"row" if self.viewport == 677 else "column"})
            # Neutral computed border colours have no visual effect without a border.
            for side in ("top", "right", "bottom", "left"):
                styles["border-" + side + "-style"] = "solid"
            styles.pop("background", None)
            styles["font-family"] = (styles["font-family"] if self.original or "monospace" in styles["font-family"] else MONO if "Mono" in styles["font-family"] else
                                      "'Plus Jakarta Sans'," + FONT if "Jakarta" in styles["font-family"] else "Inter," + FONT)

        for decl in inline.split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                if k.strip() not in {"position", "inset", "left", "right", "top", "bottom",
                                      "transform", "white-space", "scrollbar-width",
                                      "scroll-snap-type", "scroll-padding-left", "scroll-snap-align"}:
                    styles[k.strip()] = v.strip()
        for key, value in list(styles.items()):
            styles[key] = self.remap(value)
        # Normal article typography belongs to the global container, not to
        # each exported design node. Keep deliberate monospace exceptions.
        # The source-comparison renderer must still reproduce the source fonts.
        if not self.original and "monospace" not in styles.get("font-family", "").lower():
            styles.pop("font-family", None)
        if grid_child:
            styles.update({"flex":"1 1 0%", "min-width":"0"})
        # Preserve ornament geometry without unsupported absolute positioning.
        for child in node.elements():
            cc = child.attrs.get("class", "").split()
            if "absolute" in cc and "bottom-0" in cc and "w-1.5" in cc:
                styles["border-left"] = "6px solid " + self.colors["primary"]
                styles["padding-left"] = "%gpx" % max(0, float(styles.get("padding-left", "20px").replace("px", ""))-6)
            if "absolute" in cc and "-bottom-0.5" in cc:
                styles["border-bottom"] = "2px solid " + self.colors["primary"]
        if "absolute" in classes and text:
            styles.update(display="block", **{"text-align": "left", "margin-top": "-28px", "height": "68px" if self.viewport == 677 else "58px",
                                            "margin-bottom": "-40px" if self.viewport == 677 else "-30px", "line-height": "1", "pointer-events": "none"})
        if "absolute" in classes and not text and "bg-gradient-to-r" in classes:
            padding, gap = ornament or (20, 0)
            height = float(styles.get("height", "6px").replace("px", ""))
            styles.update({"margin-top": "%gpx" % -padding, "margin-left": "%gpx" % -padding,
                           "margin-right": "%gpx" % -padding, "margin-bottom": "%gpx" % (padding-height-gap), "width": "auto"})
        gradient = styles.pop("background-image", "none")
        if node.tag == "img":
            styles.update({"max-width": "100%", "display": "block"})
            if "QR Code" not in node.attrs.get("alt", ""):
                styles.pop("width", None)
                styles.update({"height": "auto", "margin": "0 auto"})
        if node.tag == "pre":
            # Source demo is horizontally scrollable, not soft-wrapped. The user
            # Markdown renderer supplies its own safe rows instead of this path.
            font = html.escape(styles.get("font-family", MONO), quote=True)
            size = styles.get("font-size", "13px")
            leading = styles.get("line-height", "21.125px")
            color = styles.get("color", self.colors["surface-container"])
            rows = ''.join('<p style="margin:0;white-space:nowrap;font-family:%s;font-size:%s;line-height:%s;letter-spacing:.5px;color:%s;"><span leaf="">%s</span></p>' %
                           (font, size, leading, color, html.escape(line.expandtabs(4).replace(" ", "\u00a0")) or "&nbsp;")
                           for line in node.text().strip("\n").splitlines())
            return '<section style="width:max-content;flex-shrink:0;">' + rows + '</section>'
        tag = node.tag
        if tag in {"div", "header", "nav", "article", "footer", "details", "summary", "button", "a"}:
            tag = "section" if tag != "button" else "span"
        if tag in {"code", "kbd", "del", "sup"}:
            if tag == "del":
                styles["text-decoration"] = "line-through"
            if tag == "kbd":
                styles.update({"border": "1px solid #D4D4D8", "padding": "1px 4px", "border-radius": "3px"})
            tag = "span"
        attrs = ' style="%s"' % html.escape(";".join(k + ":" + v for k, v in styles.items()) + ";", quote=True)
        if tag == "img":
            attrs += ' src="%s" alt="%s"' % (
                html.escape(node.attrs.get("src", ""), quote=True),
                html.escape(node.attrs.get("alt", ""), quote=True),
            )
        def px(value):
            value = value.split()[0]
            return float(value[:-2]) if re.fullmatch(r"-?[\d.]+px", value) else 0
        context = (px(styles.get("padding-top", styles.get("padding", "0px"))), px(styles.get("gap", "0px")))
        body = "".join(self.render(c, grid_child=("grid" in classes and self.viewport == 677), ornament=context) for c in node.children)
        if gradient != "none":
            body = self.gradient_svg(gradient) + body
        if "material-symbols-outlined" in classes:
            if text.startswith("{{"):
                body = '<span leaf="">%s</span>' % text
            else:
                body = icon_svg(text, styles.get("font-size", "24px").replace("px", ""), styles.get("color", self.colors["primary"]))
            # Material ligatures use 1em rather than the inherited body line-height.
            attrs = attrs.replace(' style="', ' style="line-height:1;display:inline-flex;align-items:center;', 1)
        if tag in VOID:
            return "<%s%s>" % (tag, attrs)
        return "<%s%s>%s</%s>" % (tag, attrs, body, tag)


def slot(node, name):
    node.children = ["{{" + name + "}}"]


def text_slots(node, replacements):
    for n in [node] + list(node.nodes()):
        for i, child in enumerate(n.children):
            if isinstance(child, str):
                for original, placeholder in replacements.items():
                    child = child.replace(original, "{{" + placeholder + "}}")
                n.children[i] = child


def leaf_slots(node, fields):
    """Replace selected text-bearing leaf elements, preserving source containers."""
    leaves = [n for n in node.nodes() if any(isinstance(c, str) and c.strip() for c in n.children)]
    for index, name in fields.items():
        target = leaves[index]
        replaced = False
        children = []
        for child in target.children:
            if isinstance(child, str) and child.strip():
                if not replaced:
                    children.append("{{" + name + "}}")
                    replaced = True
            else:
                children.append(child)
        target.children = children


def source_components():
    b = next(load("components").nodes("main")).elements()[0]
    sections = [n for n in b.elements() if n.tag == "section"]
    articles = [[n for n in s.elements() if n.tag == "article"] for s in sections]

    def demo(section, article=0):
        return copy.deepcopy(articles[section][article].elements()[1])

    result = {}
    result["hero"] = demo(0)
    leaf_slots(result["hero"], {0: "category", 1: "meta", 2: "title", 3: "subtitle"})
    result["step"] = demo(0, 2)
    leaf_slots(result["step"], {0: "number", 1: "title", 2: "subtitle"})
    result["quote"] = demo(2)
    # Keep the source quotation/highlight geometry; replace only the content.
    q = list(result["quote"].nodes("p"))[0]
    q.tag = "section"
    slot(q, "body_html")
    quote_leaves = [n for n in result["quote"].nodes() if n.text().strip().startswith("——")]
    slot(quote_leaves[-1], "attribution")
    result["pullquote"] = demo(2, 1)
    pull = next(result["pullquote"].nodes("p"))
    pull.tag = "section"
    slot(pull, "body_html")
    result["paragraph"] = Node("p", {"class": "font-body-editorial text-body-editorial text-on-surface-variant",
                                    "style": "margin:0 0 16px;overflow-wrap:anywhere;"}, ["{{body_html}}"])
    result["warning"] = demo(5)
    leaf_slots(result["warning"], {1: "title"})
    warning_body = next(result["warning"].nodes("p"))
    warning_body.tag = "section"
    slot(warning_body, "body_html")
    result["metric"] = demo(6).elements()[0]
    leaf_slots(result["metric"], {0: "title", 1: "number", 2: "body_html"})
    result["code"] = demo(4)
    # Exported syntax-color tokens are sample-specific. Keep the macOS frame.
    top, body = result["code"].elements()
    leaves = [n for n in top.nodes() if any(isinstance(c, str) and c.strip() for c in n.children)]
    slot(leaves[-2], "filename")
    slot(leaves[-1], "language")
    body.children = ["{{rows_html}}"]
    body.attrs["style"] = "display:block;padding:14px;overflow-wrap:anywhere;"
    result["code_row"] = Node("p", {"style": "margin:0;font-family:" + MONO +
                                 ";font-size:13px;line-height:1.6;overflow-wrap:anywhere;"},
                              ["{{line}}"])
    lists = demo(7).elements()
    for key, index in (("unordered_item", 0), ("ordered_item", 1), ("task_item", 2)):
        panel = lists[index]
        listing = next(panel.nodes("ul"), None) or next(panel.nodes("ol"), None)
        item = copy.deepcopy(listing.elements()[0] if listing else panel.elements()[1].elements()[0])
        item.tag = "section"  # Rich-text list presentation; no orphan <li>.
        leaves = [n for n in [item] + list(item.nodes()) if any(isinstance(c, str) and c.strip() for c in n.children)]
        slot(leaves[-1], "body_html")
        if key == "ordered_item":
            slot(leaves[0], "number")
        if key == "task_item":
            slot(leaves[0], "state")
            item.attrs["class"] = item.attrs.get("class", "").replace("text-outline", "text-on-surface")
            for n in item.nodes():
                n.attrs.pop("style", None)
        result[key] = item
    result["list"] = Node("section", {"style": "display:flex;flex-direction:column;gap:10px;margin:0 0 20px;"}, ["{{items_html}}"])
    result["table"] = demo(8)
    table = next(result["table"].nodes("table"))
    table.children = ["{{rows_html}}"]
    table.attrs["style"] = "border-collapse:collapse;min-width:320px;width:100%;table-layout:auto;"
    result["table_cell"] = Node("td", {"style": "padding:10px 12px;border-bottom:1px solid #E4E4E7;font-size:13px;line-height:1.7;overflow-wrap:anywhere;"}, ["{{body_html}}"])
    result["image"] = demo(9)
    figure = result["image"]
    figure.children[figure.children.index(figure.elements()[0])] = Node("img", {"src": "{{url}}", "alt": "{{alt}}"})
    caption = next(figure.nodes("figcaption"))
    slot(caption, "caption")
    result["link"] = demo(10)
    # A display card, not an inert browser copy button.
    result["link"].children = [Node("p", {"class": "font-body-sm text-primary font-semibold"}, ["{{title}}"]),
                               Node("p", {"style": "font-size:12px;color:#71717A;overflow-wrap:anywhere;margin:4px 0 0;"}, ["{{url}}"])]
    result["link"].attrs["style"] = "display:block;margin:12px 0;"
    result["footnote"] = Node("p", {"class": "font-caption text-outline", "style": "margin:8px 0;line-height:1.7;"}, ["{{number}}　{{body_html}}"])
    result["divider"] = Node("p", {"class": "text-center text-outline", "style": "margin:24px 0;letter-spacing:8px;"}, ["· · ·"])
    result["details"] = demo(10, 1)
    details = articles[10][1].elements()[2]
    result["details"] = copy.deepcopy(details)
    summary = result["details"].elements()[0]
    slot(summary, "title")
    slot(result["details"].elements()[1], "body_html")
    # Width is for an index card, not an image; allow a small horizontal scroller.
    for slug in ("ruler", "overprint", "pure"):
        main = next(load(slug).nodes("main")).elements()[0]
        blocks = main.elements()
        for name, index in (("hero",0),("quote",1),("toc",2),("signature",6),("engagement",7)):
            value = copy.deepcopy(blocks[index])
            if name == "hero":
                leaf_slots(value, {0:"category",1:"credit",2:"title",3:"subtitle"} if slug == "overprint" else {0:"category",1:"meta",2:"credit",3:"title",4:"subtitle"})
            elif name == "quote":
                para = next(value.nodes("p")); para.tag="section"; slot(para,"body_html")
                attribution = [n for n in value.nodes() if n.text().strip().startswith("——")][-1]
                slot(attribution,"attribution")
            elif name == "toc":
                item = copy.deepcopy(value.elements()[1].elements()[0])
                leaf_slots(item,{0:"number",2:"title",3:"description"})
                result["toc_item_"+slug] = item
                value.elements()[1].children=["{{items_html}}"]
                text_slots(value,{"横滑浏览":"toc_hint"})
            elif name == "signature":
                text_slots(value,{"Jacob":"author", "致力于分享一些AI技术、AI干货内容。":"bio",
                                  "长按右侧二维码关注专栏":"signature_note", "扫码关注":"qr_caption"})
                for n in [value]+list(value.nodes()):
                    for i,c in enumerate(n.children):
                        if isinstance(c,str) and c.strip()=="J": n.children[i]="{{initial}}"
                next(value.nodes("img")).attrs["src"]="{{qr_url}}"
                no_qr = copy.deepcopy(value)
                no_qr.children = [no_qr.elements()[0]]
                left = no_qr.elements()[0]
                left.children = left.elements()[:2]
                result["signature_no_qr_"+slug] = no_qr
            elif name == "engagement":
                # Preserve the approved source card and icon/action row.
                # Compiler converts buttons to static rich-text spans;
                # these ornaments do not invoke native WeChat actions.
                slot(next(value.nodes("p")), "message")
                # Rename only the static action label, never author content.
                for action in value.elements()[2].elements():
                    for label in action.elements():
                        if label.text().strip() == "转发":
                            label.children = ["分享"]
                        elif label.text().strip() == "在看":
                            label.children = ["收藏"]
                        elif label.text().strip() == "visibility":
                            label.children = ["engagement_bookmark"]
                credit = value.elements()[-1]
                credit.children = ["感谢阅读"]
            result[name+"_"+slug]=value
        heading = next(main.nodes("h2"))
        container = heading
        def parent_of(root, target):
            for child in root.elements():
                if child is target:
                    return root
                found = parent_of(child, target)
                if found:
                    return found
            return None
        container = parent_of(main, heading)
        while parent_of(main, container).tag != "article":
            container = parent_of(main, container)
        if slug == "ruler":
            prose = copy.deepcopy(blocks[3].elements()[1])
            prose.children = ["{{body_html}}"]
            result["prose_card"] = prose
        result["chapter_" + slug] = copy.deepcopy(container)
        slot(next(result["chapter_" + slug].nodes("h2")), "title")
        for n in result["chapter_" + slug].nodes():
            if not n.elements() and n.text().strip() == "01":
                slot(n, "number")
            if not n.elements() and "第一章" in n.text():
                slot(n, "label")
            if not n.elements() and "视觉杂乱与套版依赖" in n.text():
                slot(n, "subtitle")
        # Uniform API slots even in the unnumbered pure layout.
    for name in ("hero", "quote", "toc", "toc_item", "signature", "engagement"):
        result[name] = result[name+"_ruler"]
    return result


def compile_templates(theme, nodes):
    compiler = Compiler(theme)
    result = {key: compiler.render(value) for key, value in nodes.items()}
    # Step headings have no outer card; preserve the numbered badge and text.
    # The source-comparison renderer remains untouched.
    def unframe_step(match):
        pairs = declarations(html.unescape(match[1]))
        style = ";".join(key + ":" + value for key, value in pairs
                         if key != "box-sizing" and not key.startswith(
                             ("background", "border", "padding", "box-shadow"))) + ";"
        return 'style="' + escape_style_attribute(style) + '"'
    result["step"] = re.sub(r'style="([^"]*)"', unframe_step, result["step"], count=1)
    # Dynamic markup must replace the wrapping leaf span, not nest block HTML in it.
    for key, value in result.items():
        result[key] = re.sub(r'<span leaf="">(\{\{[a-z_]+_html\}\})</span>', r"\1", value)
    result["container"] = '<section style="max-width:677px;margin:0 auto;padding:20px 16px;background:#FFFFFF;color:#3d4a42;font-family:%s;font-size:14px;font-weight:400;line-height:26.6px;letter-spacing:.5px;box-sizing:border-box;overflow-wrap:anywhere;">{{body_html}}</section>' % FONT
    # The original article uses gap-6; only top-level blocks get this gap.
    for key in list(result):
        if key not in {"container", "paragraph", "code_row", "table_cell", "footnote", "divider", "list"} and not key.startswith(("toc_item", "unordered_item", "ordered_item", "task_item")):
            result[key] = '<section style="margin:0 0 24px;">' + result[key] + "</section>"
    result = {key: optimize_template_structure(clean_template_styles(value))
              for key, value in result.items()}
    for key in ("quote", "quote_ruler", "quote_overprint", "quote_pure"):
        result[key] = merge_quote_layout(result[key])
    # The public standalone row keeps its complete typography. The in-frame
    # variant explicitly relies only on the known code-body font contract.
    def frame_row_style(match):
        pairs = declarations(html.unescape(match[1]))
        style = ";".join(key + ":" + value for key, value in pairs
                         if key not in {"font-family", "font-size", "overflow-wrap"}) + ";"
        return 'style="' + escape_style_attribute(style) + '"'
    result["code_row_in_frame"] = re.sub(
        r'style="([^"]*)"', frame_row_style, result["code_row"], count=1)
    result = {key: clean_template_styles(value, minimal=True)
              for key, value in result.items()}
    result["table"] = merge_table_spacing(result["table"])
    # Static-tree font placement is independent of Markdown content. Preserve
    # dynamic slots' effective fonts while sharing stacks on inert ancestors.
    result = {key: clean_template_styles(allocate_template_fonts(value), minimal=True)
              for key, value in result.items()}
    for property_name in ("font-weight", "font-style", "letter-spacing", "color"):
        result = {key: clean_template_styles(
            allocate_template_fonts(value, property_name=property_name), minimal=True)
                  for key, value in result.items()}
    # The deterministic code assembler supplies plain paragraphs. Own their
    # shared line-height in the existing scrolling body, not in every row.
    # Leave the standalone frame and standalone row contracts unchanged.
    def code_body(match):
        return match[0].replace("line-height:22px;", "line-height:1.6;")
    result["code_with_rows"] = re.sub(
        r'<section style="[^"]*">\{\{rows_html\}\}</section>',
        code_body, result["code"])
    result["code_row_in_rows"] = result["code_row_in_frame"].replace(
        "line-height:1.6;", "")
    # The two labels share a font, but their existing size/line-height/color
    # remain separate. Only move it inside the known textless flex header:
    # never across the dynamic code-body slot or onto arbitrary author HTML.
    def share_code_header_font(header):
        fonts = re.findall(r"font-family:([^;]+);", header)
        if len(fonts) != 2 or fonts[0] != fonts[1] or "monospace" not in fonts[0]:
            raise ValueError("Unexpected code header font contract")
        header = re.sub(r"font-family:[^;]+;", "", header)
        return header.replace('style="', 'style="font-family:' + fonts[0] + ';', 1)
    for key in ("code", "code_with_rows"):
        header_start = result[key].find("<section", result[key].find(">") + 1)
        header_end = result[key].find("{{language}}</span></section>") + len(
            "{{language}}</span></section>")
        if header_start < 0 or header_end <= header_start:
            raise ValueError("Unexpected code header structure")
        header = result[key][header_start:header_end]
        result[key] = (result[key][:header_start] +
                       share_code_header_font(header) +
                       result[key][header_end:])
    # Dedicated table/cell assembly contract. Keep standalone templates intact:
    # th has native bold styling and the renderer still owns its header override.
    cell_pairs = declarations(html.unescape(
        re.search(r'style="([^"]*)"', result["table_cell"])[1]))
    cell_shared = {key: val for key, val in cell_pairs
                   if key in {"font-size", "line-height", "overflow-wrap"}}
    def table_typography(match):
        pairs = declarations(html.unescape(match[1]))
        pairs = [(key, val) for key, val in pairs if key not in cell_shared]
        pairs += list(cell_shared.items())
        return '<table style="' + escape_style_attribute(
            ";".join(key + ":" + val for key, val in pairs) + ";") + '">'
    result["table_with_cells"] = re.sub(
        r'<table style="([^"]*)">', table_typography, result["table"], count=1)
    # Known static table, no side border/image overrides: retain the width
    # reset, but discard the unused solid/color paint at zero width.
    def zero_table_border(match):
        pairs = declarations(html.unescape(match[1]))
        borders = [(key, val) for key, val in pairs if key.startswith("border")]
        if (all(key in {"border", "border-collapse"} for key, _ in borders) and
                sum(key == "border" for key, _ in borders) == 1):
            pairs = [(key, "0" if key == "border" and
                      re.fullmatch(r"0 solid rgba\([\d.,]+\)", val) else val)
                     for key, val in pairs]
        return '<table style="' + escape_style_attribute(
            ";".join(key + ":" + val for key, val in pairs) + ";") + '">'
    result["table_with_cells"] = re.sub(
        r'<table style="([^"]*)">', zero_table_border,
        result["table_with_cells"], count=1)
    result["table_cell_in_table"] = re.sub(
        r'style="([^"]*)"',
        lambda _: 'style="' + escape_style_attribute(
            ";".join(key + ":" + val for key, val in cell_pairs
                     if key not in cell_shared) + ";") + '"',
        result["table_cell"], count=1)
    def inherited_variant(value, contract):
        return clean_template_styles(value, minimal=True, inherited={
            key: val for key, val in contract.items() if key in INHERITED_TYPOGRAPHY})
    contract = dict(declarations(html.unescape(
        re.search(r'style="([^"]*)"', result["container"])[1])))
    direct = ["paragraph", "prose_card", "footnote"]
    for layout in ("ruler", "overprint", "pure"):
        direct += [name + "_" + layout for name in (
            "hero", "quote", "chapter", "toc", "signature", "signature_no_qr", "engagement")]
        # Toc items use the complete inherited typography at their insertion slot.
        value = result["toc_item_" + layout]
        toc_contract = dict(declarations(html.unescape(
            re.search(r'style="([^"]*)"', result["toc_" + layout])[1])))
        result["toc_item_" + layout + "_in_toc"] = inherited_variant(value, toc_contract)
    for key in direct:
        result[key + "_in_article"] = inherited_variant(result[key], contract)
    # This named container is only assembled with these three item variants.
    # Move declarations common to every item to the parent once per list.
    # Center the ordered badge against the FIRST text line, not the whole
    # multiline item. The wrapper takes the item's own compiled line height.
    ordered = result["ordered_item"]
    ordered_style = dict(declarations(html.unescape(
        re.search(r'style="([^"]*)"', ordered)[1])))
    badge = re.search(r'<span style="([^"]*)"><span leaf="">'
                      r'\{\{number\}\}</span></span>', ordered)
    if not badge:
        raise ValueError("Ordered-list badge template not found")
    badge_style = ";".join(k + ":" + v for k, v in
                          declarations(html.unescape(badge[1]))
                          if k != "margin-top") + ";"
    replacement = (
        '<span style="height:%s;display:flex;align-items:center;flex:none;">'
        '<span style="%s"><span leaf="">{{number}}</span></span></span>'
        % (ordered_style["line-height"], escape_style_attribute(badge_style)))
    result["ordered_item"] = ordered[:badge.start()] + replacement + ordered[badge.end():]
    item_names = ("unordered_item", "ordered_item", "task_item")
    roots = [dict(declarations(html.unescape(
        re.search(r'style="([^"]*)"', result[key])[1]))) for key in item_names]
    shared = {key: val for key, val in roots[0].items()
              if key in INHERITED_TYPOGRAPHY and all(root.get(key) == val for root in roots)}
    extra = ";".join(key + ":" + val for key, val in shared.items()) + ";"
    result["list_with_items"] = result["list"].replace(
        'style="', 'style="' + escape_style_attribute(extra), 1)
    for key in item_names:
        result[key + "_in_list"] = inherited_variant(result[key], shared)
    # All normal components inherit the single global system-font stack.
    # Standalone components should be placed inside this container as well.
    result["container_in_article"] = result["container"]
    direct += ["step", "code", "code_with_rows", "image", "table", "table_with_cells",
               "divider", "list_with_items"]
    for key in direct:
        value = result[key]
        result[key + "_in_article"] = inherited_variant(value, contract)
    # A sole ordinary paragraph can own the card's painted box. Use a named
    # assembly contract, never flatten arbitrary cards or mixed block content.
    card = re.fullmatch(r'<section style="([^"]*)">\{\{body_html\}\}</section>',
                        result["prose_card_in_article"])
    if not card:
        raise ValueError("Unexpected prose card structure")
    pairs = declarations(html.unescape(card[1]))
    props = dict(pairs)
    if props.get("display") != "flex" or props.get("flex-direction") != "column":
        raise ValueError("Unexpected prose card layout")
    style = ";".join(k + ":" + v for k, v in pairs
                     if k not in {"display", "flex-direction", "gap"}) + ";"
    result["prose_card_single_in_article"] = (
        '<p style="' + escape_style_attribute(style) + '">{{body_html}}</p>')
    # Run only after structural matching and all named inheritance variants.
    # Runtime assembly must not normalize user content or template slot values.
    return {key: minimize_template_declarations(value) for key, value in result.items()}


DISPLAY = {
    "container": "全局容器", "hero": "封面折页", "chapter_ruler": "墨规·立体标尺",
    "chapter_overprint": "浮光·透叠数字", "chapter_pure": "素墨·克制留白",
    "step": "步骤标题", "quote": "双向引号沉思卡", "pullquote": "强调金句",
    "paragraph": "正文段落", "warning": "暖黄警示", "metric": "灰阶诊断卡",
    "prose_card_single": "单段正文卡片",
    "code": "macOS 代码视窗", "code_row": "独立逐行代码",
    "code_row_in_frame": "代码视窗内逐行代码",
    "code_with_rows": "文章代码视窗（与共享行高的代码行配套）",
    "code_row_in_rows": "文章代码行（继承代码正文行高）",
    "unordered_item": "方标列表项",
    "ordered_item": "数字列表项", "task_item": "任务列表项", "list": "列表容器",
    "list_with_items": "列表容器（与列表内变体配套）",
    "table": "横滑安全表格", "table_cell": "表格单元格", "image": "相框与图注",
    "table_with_cells": "表格（与共享字体单元格配套）",
    "table_cell_in_table": "表格内单元格（继承配套表格字体）",
    "link": "外链展示卡", "footnote": "脚注", "divider": "微点分割线",
    "details": "静态补充阅读（展开）", "signature": "文末压舱名片",
    "engagement": "文末互动卡片（静态图标动作行）", "toc": "横滑目录", "toc_item": "目录项",
}


def reference(theme, templates):
    lines = [
        "# 公众号排版组件库 —— " + theme["name"], "",
        "> 设计基于 Magazine Markdown Converter 的来源稿；配色取自 15 款色系表。",
        "> 三版式取自 ruler / overprint / pure；通用语法组件取自组件设计稿。原稿保存在 assets/stitch/。",
        "> 下列 HTML 已内联、叶节点封装、移除网页交互；不要直接复制原始 HTML。",
        "> 普通字体仅在全局 `container` 定义，组件需放在该容器内继承；代码与刻意等宽的编号保留局部字体。字号、字重和行高仍按组件设计。",
        "> 普通正文直接使用 `paragraph_in_article`，不默认套用背景、边框、阴影卡片；`prose_card` 仅为显式卡片需求保留。",
        "> 表格装配用 `table_with_cells` + `table_cell_in_table`（文章中使用前者的 `_in_article` 变体）；独立 `table_cell` 保留完整字体，不与共享字体变体混用。",
        "> `*_html` 字段仅放入已转换且校验通过的组件，其余字段按纯文本转义。", "",
        "## 设计变量速查表", "",
        "| 角色 | 值 |", "|---|---|",
        "| 主色 | `" + theme["primary"] + "` |",
        "| 轻高光 | `" + theme["accent"] + "` |",
        "| 纸质底色 | `" + theme["surface"] + "` |",
        "| 压舱深色 | `" + theme["deep"] + "` |",
        "| 标题 / 正文 / 弱文字 | `#121C2A` / `#3D4A42` / `#6D7A72` |",
        "| 正文字号 / 行高 / 安全宽度 | `14px` / `1.9` / `677px` |",
        "| 默认章节版式 | " + LAYOUT_NAMES[theme["layout"]] + "（可在三版式中明确切换） |",
        "| 正文下划线 CSS | `border-bottom:2px solid " + theme["accent"] + ";font-weight:600;` |", "",
        "## 各组件完整 HTML", "",
    ]
    for key, value in templates.items():
        label = DISPLAY.get(key, key)
        for suffix, context in (("_in_article", "（文章容器内）"), ("_in_toc", "（目录容器内）"),
                                ("_in_list", "（列表容器内）")):
            if key.endswith(suffix):
                base = key.removesuffix(suffix)
                label = DISPLAY.get(base, base) + context
        lines += ["### " + label + " · `" + key + "`", "", "```html", value, "```", ""]
    lines += [
        "## 完整文章模板骨架", "",
        "`container` → `hero` → 开头原文引言（若有，`quote`）→ `toc`（精选最多 3 项）→",
        "`chapter_" + theme["layout"] + "` + 原文段落/列表/代码/表格/图片 → `signature` → `engagement`。",
        "目录放在封面和开头引言之后；正文不得用组件库演示文案替换。",
        "签名与互动各仅一次；已有署名沿用原文，未给署名保留 `{{作者名}}` / `{{简介}}`。",
        "原稿二维码为演示素材，仅画廊与对照页显式使用；生成文章用 --qr-url 提供真实二维码，保留 88px 右栏、72px 图片与关注提示。无二维码时使用明确的无二维码名片变体。",
        "纯净版不强塞可见章节编号；墨规与浮光按 H2 顺序使用 01/02/03。", "",
        "## 文章类型 → 组件组合配方表", "",
        "| 类型 | 核心组合 | 点缀上限 |", "|---|---|---|",
        "| 教程 / 工程解析 | 墨规章节 + step + code + list + warning | metric ≤ 3 种；有原文才使用 |",
        "| 人物 / 商业特刊 | 浮光章节 + quote + image + paragraph | pullquote ≤ 3 处 |",
        "| 随笔 / 文学 / 极简 | 素墨章节 + paragraph + quote | divider ≤ 3 处；不添加多余标签 |",
        "| 数据 / 报告 | 默认章节 + table + metric + paragraph | warning / pullquote 各 ≤ 2 处 |", "",
        "## Markdown → 组件映射规则表", "",
        "| Markdown | 组件 / 规则 |", "|---|---|",
        "| `#` | hero，纯文本主标题不添演示副标题 |",
        "| `##` / `###` | chapter（默认版式）/ step |",
        "| 段落 / 加粗 / 高亮 / 下划线 | paragraph；主色加粗 / 纸底高亮 / 轻高光下划线 |",
        "| 删除线 | 真实删除线；不要改成荧光笔 |",
        "| 引用 / `::: quote` | quote / pullquote |",
        "| 围栏代码 / 行内代码 | code + code_row / 等宽 span；保留代码半角和缩进 |",
        "| 无序 / 有序 / 任务列表 | list + 对应 item；保留嵌套层级和完成态 |",
        "| 表格 | table + table_cell；横滑包裹，单元格完整保留 |",
        "| 图片 / GIF | image；无 alt 则删除 figcaption；GIF 图注标注动图 |",
        "| 外链 | link 展示完整 URL；不假装按钮可点击 |",
        "| 脚注 / 分割线 / 补充阅读 | footnote / divider / details 静态展开 |",
        "| `::: warning/info/tip` | warning（按语义改标题） |", "",
        "源头检查：`python3 scripts/component_lint.py .`。",
        "产物检查：`python3 scripts/validate_gzh_html.py <正文文件>`。",
        "离线确定性转换：`python3 scripts/render_stitch_article.py <文章.md> --theme " + theme["id"] + " --output <正文.html>`。", "",
    ]
    return "\n".join(lines)


def build():
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    for screen in manifest["screens"]:
        path = ROOT / screen["source"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != screen["sha256"]:
            raise ValueError("Source checksum mismatch: " + str(path))
    themes = extract_catalog()
    nodes = source_components()
    write(SOURCE / "themes.json", json.dumps(themes, ensure_ascii=False, indent=2) + "\n")
    for theme in themes:
        templates = compile_templates(theme, nodes)
        write(SOURCE / "templates" / (theme["id"] + ".json"), json.dumps(templates, ensure_ascii=False, indent=2) + "\n")
        write(ROOT / "references" / ("theme-" + theme["id"] + ".md"), reference(theme, templates))
    index = [
        "# 内置主题索引与选择决策表", "",
        "当前主题的唯一注册表。原本 6 套旧主题已删除，不再作为生成候选。",
        "设计来源与适配：[设计来源与兼容说明](stitch-design-system.md)。15 色系 × 3 章节版式；默认「墨规·翡翠林木」。",
        "色系 ID 与主题画廊一致；版式不混色。", "",
        "| 主题 | 主色 | 适用场景 | 组件库文件 | 正文下划线 CSS |",
        "|---|---|---|---|---|",
    ]
    for t in themes:
        index.append("| %s | `%s` | %s（默认%s） | `references/theme-%s.md` | `border-bottom:2px solid %s;font-weight:600;` |" %
                     (t["name"], t["primary"], t["scene"], LAYOUT_NAMES[t["layout"]], t["id"], t["accent"]))
    index += ["", "## 选择规则", "",
              "- 普通模式与全自动模式均采用固定默认参数：主题和版式均省略时，直接使用【墨规】· 翡翠林木（theme=emerald，layout=ruler），不询问确认，不按题材自动换主题。",
              "- 仅指定主题时使用该主题及其登记的默认版式；仅指定版式时使用 emerald 色系及指定版式；两者均指定时使用指定组合。",
              "- 用户明确要求推荐或比较时才按适用场景给建议；指定浮光/透叠用 overprint，指定墨规/标尺用 ruler，指定素墨/纯净用 pure。",
              "- 不把色系与版式混为同一个参数；例如 mineral-blue + overprint 仍然全篇为沧浪色系。",
              "- 用户指定已删除的旧主题时提示选择当前内置主题，不默默回退或复活旧库。",
              "- 自定义主题仍按 theme-generator.md 登记，当前主题专属组件优先于通用库。", ""]
    write(ROOT / "references/theme-index.md", "\n".join(index))
    print("Built %d colorways, 3 layouts and %d components per colorway." % (len(themes), len(templates)))


if __name__ == "__main__":
    build()
