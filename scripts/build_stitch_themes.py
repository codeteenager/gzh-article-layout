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

from stitch_themes import ROOT, LAYOUT_NAMES

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


def declarations(style):
    """Split declarations without breaking quoted values, URLs or functions."""
    parts, start, depth, quote, escaped = [], 0, 0, None, False
    for i, char in enumerate(style):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == ";" and depth == 0:
            parts.append(style[start:i])
            start = i + 1
    parts.append(style[start:])
    return [tuple(map(str.strip, part.split(":", 1)))
            for part in parts if ":" in part]


def compact_template_style(style):
    pairs = declarations(style)
    # Unknown/custom CSS is not rewritten: these optimizations target the built-in
    # templates, not arbitrary cascading styles or important declarations.
    if any("!important" in value or key.startswith("--") for key, value in pairs):
        return style
    props = dict(pairs)
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
    # Font-family lists may be formatted over multiple lines. No quote contents
    # or code/text nodes are minified.
    def min_value(key, value):
        if key == "font-family":
            value = re.sub(r"\s*,\s*", ",", value)
            return value.strip()
        return value
    return ";".join(key + ":" + min_value(key, value) for key, value in props.items()) + ";"


def short_box(values):
    top, right, bottom, left = values
    if right == left:
        if top == bottom:
            return top if top == right else top + " " + right
        return " ".join((top, right, bottom))
    return " ".join(values)


class TemplateStyleCleaner(HTMLParser):
    """Reuse typography only inside one static component, never across slots."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text()
        style = dict(attrs).get("style")
        inherited = dict(self.stack[-1][1]) if self.stack else {}
        effective = dict(inherited)
        if tag in TYPOGRAPHY_BOUNDARIES:
            # Unknown native defaults must not be propagated to descendants.
            effective = {}
        if style is not None:
            compact = compact_template_style(style)
            pairs = declarations(compact)
            props = dict(pairs)
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
            raw = re.sub(r"\bstyle\s*=\s*(\"[^\"]*\"|'[^']*')",
                         lambda _: 'style="' + html.escape(compact, quote=True) + '"',
                         raw, count=1)
        self.output.append(raw)
        if tag not in VOID:
            self.stack.append((tag, effective))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        self.output.append("</" + tag + ">")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append("&" + name + ";")

    def handle_charref(self, name):
        self.output.append("&#" + name + ";")

    def handle_comment(self, data):
        self.output.append("<!--" + data + "-->")


def clean_template_styles(value):
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
    parser = TemplateStyleCleaner()
    parser.feed(protected)
    parser.close()
    # Only empty leaf nodes, never wrappers with meaningful typography/layout.
    result = re.sub(r'<span leaf=""></span>', "", "".join(parser.output))
    for index, fragment in enumerate(fragments):
        result = result.replace(f"<!--GZH_SVG_PRESERVE_{index}-->", fragment)
    return result


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
    source = (SOURCE / "icons" / (name + ".svg")).read_text()
    source = re.sub(r'width="24"', 'width="%s"' % size, source)
    source = re.sub(r'height="24"', 'height="%s"' % size, source)
    return source.replace('<svg ', '<svg style="display:block;flex-shrink:0;" fill="%s" ' % color, 1)


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
            for key in ("primary", "primary-container", "secondary", "on-primary-fixed-variant", "on-secondary-fixed-variant", "surface-tint"):
                self.colors[key] = theme["primary"]
            for key in ("secondary-fixed-dim", "primary-fixed-dim", "inverse-primary"):
                self.colors[key] = theme["accent"]
            for key in ("surface-container-low", "secondary-container", "secondary-fixed", "primary-fixed"):
                self.colors[key] = theme["surface"]
            for key in ("on-secondary-container", "on-secondary-fixed", "on-primary-fixed"):
                self.colors[key] = theme["deep"]
        self.colors.update({"#e6f4ea": "#e6f4ea" if self.original else theme["surface"],
                            "#a3e0be": "#a3e0be" if self.original else theme["accent"],
                            "#047857": "#047857" if self.original else theme["primary"]})

    def remap(self, value):
        if self.original:
            return value
        replacements = dict(zip(original_tokens().values(), self.colors.values()))
        replacements.update({"#062e24": self.theme["deep"], "#059669": self.theme["primary"],
                             "#10b981": self.theme["accent"], "#f2faf6": self.theme["surface"],
                             "#005236": self.theme["primary"], "#a7f3d0": self.theme["surface"],
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
    result["code_row"] = Node("p", {"style": "margin:0;display:flex;gap:12px;font-family:" + MONO +
                                 ";font-size:13px;line-height:1.6;overflow-wrap:anywhere;"},
                              [Node("span", {"style": "color:#94A3B8;min-width:24px;flex-shrink:0;"}, ["{{number}}"]),
                               Node("span", {"style": "min-width:0;overflow-wrap:anywhere;"}, ["{{line}}"])])
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
                text_slots(value,{"甲木 × 摸鱼小李":"author", "专注富文本工程规范与纸质卡片审美，杜绝廉价排版。":"bio",
                                  "长按右侧二维码关注专栏":"signature_note", "扫码关注":"qr_caption"})
                for n in [value]+list(value.nodes()):
                    for i,c in enumerate(n.children):
                        if isinstance(c,str) and c.strip()=="甲": n.children[i]="{{initial}}"
                next(value.nodes("img")).attrs["src"]="{{qr_url}}"
                no_qr = copy.deepcopy(value)
                no_qr.children = [no_qr.elements()[0]]
                left = no_qr.elements()[0]
                left.children = left.elements()[:2]
                result["signature_no_qr_"+slug] = no_qr
            elif name == "engagement":
                text_slots(value,{"如果觉得有用，随手点个赞、在看、转发三连吧。":"message"})
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
    # Dynamic markup must replace the wrapping leaf span, not nest block HTML in it.
    for key, value in result.items():
        result[key] = re.sub(r'<span leaf="">(\{\{[a-z_]+_html\}\})</span>', r"\1", value)
    result["container"] = '<section style="max-width:677px;margin:0 auto;padding:20px 16px;background:#FFFFFF;color:#3d4a42;font-family:%s;font-size:14px;line-height:26.6px;letter-spacing:.5px;box-sizing:border-box;overflow-wrap:anywhere;">{{body_html}}</section>' % FONT
    # The original article uses gap-6; only top-level blocks get this gap.
    for key in list(result):
        if key not in {"container", "paragraph", "code_row", "table_cell", "footnote", "divider", "list"} and not key.startswith(("toc_item", "unordered_item", "ordered_item", "task_item")):
            result[key] = '<section style="margin:0 0 24px;">' + result[key] + "</section>"
    return {key: clean_template_styles(value) for key, value in result.items()}


DISPLAY = {
    "container": "全局容器", "hero": "封面折页", "chapter_ruler": "墨规·立体标尺",
    "chapter_overprint": "浮光·透叠数字", "chapter_pure": "素墨·克制留白",
    "step": "步骤标题", "quote": "双向引号沉思卡", "pullquote": "强调金句",
    "paragraph": "正文段落", "warning": "暖黄警示", "metric": "灰阶诊断卡",
    "code": "macOS 代码视窗", "code_row": "逐行代码", "unordered_item": "方标列表项",
    "ordered_item": "数字列表项", "task_item": "任务列表项", "list": "列表容器",
    "table": "横滑安全表格", "table_cell": "表格单元格", "image": "相框与图注",
    "link": "外链展示卡", "footnote": "脚注", "divider": "微点分割线",
    "details": "静态补充阅读（展开）", "signature": "文末压舱名片",
    "engagement": "互动微胶囊", "toc": "横滑目录", "toc_item": "目录项",
}


def reference(theme, templates):
    lines = [
        "# 公众号排版组件库 —— " + theme["name"], "",
        "> 设计基于 Magazine Markdown Converter 的来源稿；配色取自 15 款色系表。",
        "> 三版式取自 ruler / overprint / pure；通用语法组件取自组件设计稿。原稿保存在 assets/stitch/。",
        "> 下列 HTML 已内联、叶节点封装、移除网页交互；不要直接复制原始 HTML。",
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
        lines += ["### " + DISPLAY.get(key, key) + " · `" + key + "`", "", "```html", value, "```", ""]
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
    print("Built %d colorways, 3 layouts and %d source-derived components per colorway." % (len(themes), len(nodes) + 1))


if __name__ == "__main__":
    build()
