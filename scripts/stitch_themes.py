#!/usr/bin/env python3
"""Read authoritative Markdown themes and safely fill their component slots."""

import html
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
    return read_catalog(ROOT)


def read_components(text):
    """Read component definitions and one-hop, same-document aliases."""
    match = re.search(r"^## 各组件完整 HTML\s*\n(.*?)(?=^## |\Z)",
                      text, re.M | re.S)
    if not match:
        raise ValueError("缺少各组件完整 HTML 章节")
    literals, aliases, order = {}, {}, []
    # Ignore heading-like text inside fenced HTML.
    heading = None
    body = []
    sections = []
    fenced = False
    for line in match[1].splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("### "):
            if heading is not None:
                sections.append((heading, "\n".join(body)))
            heading, body = line, []
        else:
            body.append(line)
    if fenced:
        raise ValueError("组件 HTML 围栏未闭合")
    if heading is not None:
        sections.append((heading, "\n".join(body)))
    for heading, body in sections:
        key_match = re.search(r" · `([a-z][a-z0-9_]*)`$", heading)
        if not key_match:
            raise ValueError("无效组件标题：" + heading)
        key = key_match[1]
        if key in order:
            raise ValueError("重复组件：" + key)
        order.append(key)
        blocks = re.findall(r"^```html\n(.*?)\n```[ \t]*$", body, re.M | re.S)
        refs = re.findall(r"^HTML 同组件：`([^`]+)`。", body, re.M)
        if len(blocks) + len(refs) != 1:
            raise ValueError("组件须有且仅有一个 HTML 定义或引用：" + key)
        if blocks:
            literals[key] = blocks[0]
        else:
            aliases[key] = refs[0]
    if not order:
        raise ValueError("组件库为空")
    for key, target in aliases.items():
        if target not in literals:
            raise ValueError("无效或链式组件引用：" + key + " → " + target)
    return {key: literals[key] if key in literals else literals[aliases[key]]
            for key in order}


def read_catalog(root):
    """Index is the registry; semantic palette values come from each library."""
    themes, seen = [], set()
    index = (root / "references/theme-index.md").read_text(encoding="utf-8")
    for line in index.splitlines():
        if not line.startswith("|") or "references/theme-" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            raise ValueError("无效主题登记行：" + line)
        name, primary, scene, path, underline = cells
        path_match = re.fullmatch(r"`references/theme-([a-z0-9]+(?:-[a-z0-9]+)*)\.md`", path)
        if not path_match:
            raise ValueError("无效主题路径：" + path)
        theme_id = path_match[1]
        if theme_id in seen:
            raise ValueError("重复主题：" + theme_id)
        seen.add(theme_id)
        text = (root / "references" / ("theme-" + theme_id + ".md")).read_text(encoding="utf-8")
        palette = {}
        for role, field in (("主色", "primary"), ("轻高光", "accent"),
                            ("纸质底色", "surface"), ("压舱深色", "deep")):
            value = re.search(r"^\| " + role + r" \| `(?P<color>#[0-9A-Fa-f]{6})` \|$", text, re.M)
            if not value:
                raise ValueError("主题 %s 缺少色值：%s" % (theme_id, role))
            palette[field] = value["color"].upper()
        layout = re.search(r"^\| 默认章节版式 \| (墨规|浮光|素墨)", text, re.M)
        if not layout:
            raise ValueError("主题缺少默认章节版式：" + theme_id)
        layout_id = {value: key for key, value in LAYOUT_NAMES.items()}[layout[1]]
        if primary != "`" + palette["primary"] + "`":
            raise ValueError("索引与组件库主色不一致：" + theme_id)
        expected = "border-bottom:2px solid %s;font-weight:600;" % palette["accent"]
        if underline != "`" + expected + "`":
            raise ValueError("索引与组件库下划线不一致：" + theme_id)
        scene = re.sub(r"（默认(墨规|浮光|素墨)）$", "", scene)
        themes.append(dict(id=theme_id, name=name, **palette, scene=scene, layout=layout_id))
    if not themes:
        raise ValueError("主题索引为空")
    return themes


def theme_by_id(theme_id):
    for theme in catalog():
        if theme["id"] == theme_id:
            return theme
    raise ValueError("未注册的内置主题：" + theme_id)


@lru_cache(maxsize=32)
def templates(theme_id):
    theme_by_id(theme_id)
    return read_components(
        (ROOT / "references" / ("theme-" + theme_id + ".md")).read_text(encoding="utf-8"))


def compact_templates(values):
    """Store byte-identical HTML once; aliases always target a literal string."""
    result, owners = {}, {}
    for name, value in values.items():
        if not isinstance(value, str):
            raise ValueError("模板必须为 HTML 字符串：" + name)
        if value in owners:
            result[name] = {"$ref": owners[value]}
        else:
            owners[value] = name
            result[name] = value
    return result


def expand_templates(values):
    """Preserve the public string mapping and accept legacy uncompressed files.

    References are one-hop and local to this file, never paths or template slots.
    Reject chains, cycles, missing targets and malformed entries explicitly.
    """
    if not isinstance(values, dict):
        raise ValueError("模板文件必须为对象")
    result = {}
    for name, value in values.items():
        if isinstance(value, str):
            result[name] = value
        elif (isinstance(value, dict) and set(value) == {"$ref"}
              and isinstance(value["$ref"], str)
              and isinstance(values.get(value["$ref"]), str)):
            result[name] = values[value["$ref"]]
        else:
            raise ValueError("无效模板或引用：" + name)
    return result


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
    if name.startswith("signature") and not str(fields.get("bio", "")).strip():
        value = re.sub(r'<p\b[^>]*><span leaf="">\{\{bio\}\}</span></p>', "", value)
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
