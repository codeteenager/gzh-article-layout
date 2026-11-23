#!/usr/bin/env python3
"""Offline built-in theme catalog and safe, parameterized component templates."""

import html
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYOUTS = ("ruler", "overprint", "pure")
LAYOUT_NAMES = {"ruler": "墨规", "overprint": "浮光", "pure": "素墨"}


def declarations(style):
    """Split decoded CSS without breaking quoted values, URLs or functions."""
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


def escape_style_attribute(value):
    """Escape double-quoted HTML attributes; literal apostrophes are safe."""
    return html.escape(value, quote=False).replace('"', "&quot;")


def merge_text_leaf_spans(value):
    """Fuse only an ordinary span and its sole, unstyled text leaf.

    Call on assembled inline markup or static templates, never across block
    component boundaries. Flex/grid leaves remain separate layout items.
    """
    pattern = re.compile(r'<span(?P<attrs>\s[^<>]*?)?>'
                         r'<span leaf="">(?P<text>[^<>]*)</span></span>')

    def merge(match):
        attrs = match["attrs"] or ""
        style = re.search(r'\bstyle="([^"]*)"', attrs)
        props = dict(declarations(html.unescape(style[1]))) if style else {}
        if (props.get("display") in {"flex", "inline-flex", "grid", "inline-grid",
                                     "contents"} or
                re.search(r"\bleaf\s*=", attrs)):
            return match[0]
        return '<span leaf=""' + attrs + '>' + match["text"] + '</span>'

    while True:
        optimized = pattern.sub(merge, value)
        if optimized == value:
            return value
        value = optimized


@lru_cache(maxsize=1)
def catalog():
    return json.loads((ROOT / "assets/stitch/themes.json").read_text(encoding="utf-8"))


def theme_by_id(theme_id):
    for theme in catalog():
        if theme["id"] == theme_id:
            return theme
    raise ValueError("未注册的内置主题：" + theme_id)


@lru_cache(maxsize=32)
def templates(theme_id):
    theme_by_id(theme_id)
    return json.loads(
        (ROOT / "assets/stitch/templates" / (theme_id + ".json")).read_text(encoding="utf-8")
    )


def component(theme_id, name, **fields):
    """Text is escaped by default; explicitly named *_html slots accept safe markup."""
    value = templates(theme_id)[name]
    slots = set(re.findall(r"\{\{([a-z_]+)\}\}", value))
    missing = slots - set(fields)
    if missing:
        raise ValueError("组件 %s 缺少字段：%s" % (name, ", ".join(sorted(missing))))
    # WeChat inserts <br> into empty leaves. In a flex column that creates
    # an extra line and offsets the visible title from its number badge.
    # Remove the optional slot before substitution, not arbitrary user spans.
    if name in ("step", "step_in_article") and not str(fields["subtitle"]).strip():
        value = re.sub(r'<span\b[^>]*>\{\{subtitle\}\}</span>', "", value)
    if name == "hero" or name.startswith("hero_"):
        for slot in ("meta", "credit"):
            if slot in fields and not str(fields[slot]).strip():
                # Remove the whole optional badge, not just its text leaf.
                value = re.sub(
                    r'<span\b[^>]*><span leaf="">\{\{' + slot +
                    r'\}\}</span></span>', "", value)
                value = re.sub(
                    r'<span\b[^>]*>\{\{' + slot + r'\}\}</span>', "", value)
    # Single substitution pass: user text cannot inject a second template slot.
    result = re.sub(
        r"\{\{([a-z_]+)\}\}",
        lambda m: str(fields[m[1]]) if m[1].endswith("_html")
        else html.escape(str(fields[m[1]]), quote=True),
        value,
    )
    # Optional subtitle is absent content, not a forced empty line.
    return re.sub(r'<p\b[^>]*><span leaf=""></span></p>', "", result)


def chapter(theme_id, title, number, layout=None, subtitle="", in_article=False):
    theme = theme_by_id(theme_id)
    layout = layout or theme["layout"]
    if layout not in LAYOUTS:
        raise ValueError("未知版式：" + layout)
    return component(
        theme_id, "chapter_" + layout + ("_in_article" if in_article else ""), title=title,
        number=str(number).zfill(2), subtitle=subtitle,
        label="第" + ("一二三四五六七八九十"[int(number)-1] if 1 <= int(number) <= 10 else str(number)) + "章",
    )
