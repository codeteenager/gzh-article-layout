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
    # Single substitution pass: user text cannot inject a second template slot.
    result = re.sub(
        r"\{\{([a-z_]+)\}\}",
        lambda m: str(fields[m[1]]) if m[1].endswith("_html")
        else html.escape(str(fields[m[1]]), quote=True),
        value,
    )
    # Optional subtitle is absent content, not a forced empty line.
    return re.sub(r'<p\b[^>]*><span leaf=""></span></p>', "", result)


def chapter(theme_id, title, number, layout=None, subtitle=""):
    theme = theme_by_id(theme_id)
    layout = layout or theme["layout"]
    if layout not in LAYOUTS:
        raise ValueError("未知版式：" + layout)
    return component(
        theme_id, "chapter_" + layout, title=title,
        number=str(number).zfill(2), subtitle=subtitle,
        label="第" + ("一二三四五六七八九十"[int(number)-1] if 1 <= int(number) <= 10 else str(number)) + "章",
    )
