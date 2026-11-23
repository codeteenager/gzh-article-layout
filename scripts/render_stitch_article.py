#!/usr/bin/env python3
"""Deterministic, offline Markdown → themed WeChat HTML.

No model or network dependency. Unknown/raw HTML is escaped rather than executed.
The skill may add semantic keyword markings to the Markdown before this step.
"""

import argparse
import html
import re
from pathlib import Path

from stitch_themes import LAYOUTS, catalog, chapter, component, theme_by_id
from validate_gzh_html import validate


def chinese_punctuation(text):
    """Normalize punctuation in Chinese prose, not code/URLs or English names."""
    text = re.sub(r"([一-鿿])[,:;!?]", lambda m: m[0][0] + {
        ",": "，", ":": "：", ";": "；", "!": "！", "?": "？"
    }[m[0][1]], text)
    text = re.sub(r'["\']([^"\']*[\u4e00-\u9fff][^"\']*)["\']', r"“\1”", text)
    if re.search(r"[一-鿿]", text):
        text = text.replace('"', "”").replace("'", "’")
    return text


def leaf(text):
    return '<span leaf="">%s</span>' % html.escape(text, quote=False)


def safe_url(url):
    url = url.strip()
    if re.match(r"(?i)^(javascript|data|vbscript):", url):
        raise ValueError("不允许的资源地址：" + url[:40])
    return url


def inherit_paragraphs(value):
    """Use source card/quotation typography instead of nesting generic prose styles."""
    def opening(match):
        style = re.sub(r"(?:font-family|font-size|font-weight|line-height|letter-spacing|color):[^;]*;", "", match[1])
        style = re.sub(r"margin:[^;]*;", "margin:0;", style)
        return '<p style="' + style + '">'
    return re.sub(r'<p style="([^"]*)">', opening, value)


class Renderer:
    def __init__(self, theme="emerald", layout=None, author=None, bio=None, qr_url=None):
        self.theme = theme_by_id(theme)
        self.id = theme
        self.layout = layout or self.theme["layout"]
        self.author = author
        self.bio = bio
        self.qr_url = safe_url(qr_url) if qr_url else None
        self.section_no = 0
        self.step_no = 0
        self.footnotes = {}
        self.references = {}

    def c(self, name, **fields):
        if name in {"hero", "quote", "toc", "toc_item", "signature", "engagement"}:
            name += "_" + self.layout
        return component(self.id, name, **fields)

    def inline(self, text):
        # Ordered scanner protects inline code before prose punctuation conversion.
        token = re.compile(
            r"(`+)([\s\S]*?)\1"
            r"|!\[([^\]]*)\]\(([^)]*)\)"
            r"|\[([^\]]+)\]\(([^)]*)\)"
            r"|\[([^\]]+)\]\[([^\]]*)\]"
            r"|\[\^([^\]]+)\]"
            r"|(\*\*|==|\+\+|~~)(.+?)\10"
            r"|(\*)([^*]+)\12"
            r"|<(u|kbd)>(.*?)</\14>",
            re.S,
        )
        out, pos = [], 0
        for m in token.finditer(text):
            out.append(leaf(chinese_punctuation(text[pos:m.start()])))
            if m[1] is not None:
                out.append('<span style="font-family:Consolas,Monaco,monospace;font-size:13px;background:%s;color:%s;padding:1px 5px;border-radius:4px;">%s</span>' %
                           (self.theme["surface"], self.theme["primary"], leaf(m[2])))
            elif m[3] is not None:
                out.append('<span><img src="%s" alt="%s" style="max-width:100%%;height:auto;display:block;margin:0 auto;"></span>' %
                           (html.escape(safe_url(m[4]), quote=True), html.escape(m[3], quote=True)))
            elif m[5] is not None or m[7] is not None:
                title = m[5] or m[7]
                url = m[6] if m[5] is not None else self.references.get((m[8] or title).lower())
                if url:
                    safe_url(url)
                    out.append('<span style="color:%s;border-bottom:1px solid %s;">%s</span>%s' %
                               (self.theme["primary"], self.theme["accent"], self.inline(title), leaf("（" + url + "）")))
                else:
                    out.append(leaf(m[0]))
            elif m[9] is not None:
                out.append('<span style="font-size:11px;vertical-align:super;color:%s;">%s</span>' %
                           (self.theme["primary"], leaf("[^" + m[9] + "]")))
            elif m[10] is not None:
                marker = m[10]
                style = {
                    "**": "font-weight:700;color:" + self.theme["primary"],
                    "==": "background:" + self.theme["surface"] + ";padding:1px 3px",
                    "++": "border-bottom:2px solid " + self.theme["accent"] + ";font-weight:600",
                    "~~": "text-decoration:line-through;color:#71717A",
                }[marker]
                out.append('<span style="%s;">%s</span>' % (style, self.inline(m[11])))
            elif m[12] is not None:
                out.append('<span style="font-style:italic;">%s</span>' % self.inline(m[13]))
            else:
                style = "border-bottom:2px solid " + self.theme["accent"]
                if m[14] == "kbd":
                    style = "border:1px solid #D4D4D8;border-radius:3px;padding:1px 4px;font-family:monospace"
                out.append('<span style="%s;">%s</span>' % (style, self.inline(m[15])))
            pos = m.end()
        out.append(leaf(chinese_punctuation(text[pos:])))
        return "".join(out)

    def paragraph(self, text):
        return self.c("paragraph", body_html=self.inline(text))

    def code(self, code, info):
        lines = code.splitlines()
        if not lines:
            lines = [""]
        rows = []
        for i, line in enumerate(lines, 1):
            line = line.expandtabs(4)
            # NBSPs preserve indentation and repeated spaces without white-space:pre.
            line = line.replace(" ", "\u00a0")
            rows.append(self.c("code_row_in_frame", number=str(i).zfill(2), line=line or "\u00a0"))
        return self.c("code", filename=info or "CODE", language=info, rows_html="".join(rows))

    def list_block(self, lines):
        """Keep nesting/continuations in the same semantic list item."""
        item_rx = re.compile(r"^(\s*)(?:([-+*])|(\d+)[.)])\s+(?:\[([ xX])\]\s+)?(.*)$")
        items, index = [], 0
        while index < len(lines):
            match = item_rx.match(lines[index])
            if not match:
                raise ValueError("Malformed list block")
            indent, bullet, number, state, text = match.groups()
            continuation, index = [], index + 1
            while index < len(lines):
                nxt = item_rx.match(lines[index])
                if nxt and len(nxt[1]) <= len(indent):
                    break
                continuation.append(lines[index])
                index += 1
            inner = self.inline(text)
            if continuation:
                trim = min(len(s) - len(s.lstrip()) for s in continuation if s.strip())
                inner += self.blocks([s[trim:] for s in continuation])
            if state is not None:
                if state.lower() == "x":
                    inner = '<span style="text-decoration:line-through;color:#71717A;">' + inner + "</span>"
                item = self.c("task_item", state="✓" if state.lower() == "x" else "□", body_html=inner)
            elif number is not None:
                item = self.c("ordered_item", number=number.zfill(2), body_html=inner)
            else:
                item = self.c("unordered_item", body_html=inner)
            items.append(item)
        return self.c("list", items_html="".join(items))

    @staticmethod
    def table_cells(line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|") and not line.endswith(r"\|"):
            line = line[:-1]
        return [c.strip().replace(r"\|", "|") for c in re.split(r"(?<!\\)\|", line)]

    @staticmethod
    def starts_block(line):
        return bool(re.match(r"^(#{1,6}\s|>|:::|```|~~~|[-+*]\s|\d+[.)]\s|!\[|<details>|<summary>|</details>)", line))

    def blocks(self, lines, prose_cards=False):
        out, i = [], 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            fence = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
            if fence:
                delimiter, info = fence.groups()
                i += 1
                code = []
                while i < len(lines) and not re.match(r"^\s*" + re.escape(delimiter[0]) + "{" + str(len(delimiter)) + r",}\s*$", lines[i]):
                    code.append(lines[i])
                    i += 1
                if i == len(lines):
                    raise ValueError("代码围栏未闭合")
                out.append(self.code("\n".join(code), info.strip()))
                i += 1
                continue
            heading = re.match(r"^(#{1,6})\s+(.+?)(?:\s+#+)?$", line)
            if heading:
                level, title = len(heading[1]), heading[2]
                if level == 1:
                    # An additional H1 remains visible; only the first document H1 is a cover.
                    out.append(chapter(self.id, title, self.section_no + 1, self.layout))
                elif level == 2:
                    self.section_no += 1
                    self.step_no = 0
                    out.append(chapter(self.id, title, self.section_no, self.layout))
                else:
                    self.step_no += 1
                    out.append(self.c("step", number=self.step_no, title=title, subtitle=""))
                i += 1
                continue
            if re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", line):
                out.append(self.c("divider"))
                i += 1
                continue
            if line.startswith(">"):
                quoted = []
                while i < len(lines) and lines[i].startswith(">"):
                    quoted.append(re.sub(r"^>\s?", "", lines[i]))
                    i += 1
                body = self.blocks(quoted)
                body = inherit_paragraphs(body)
                out.append(self.c("quote", body_html=body, attribution=""))
                continue
            extension = re.match(r"^:::\s*(warning|info|tip|quote|details|author|engagement)(?:\s+(.*))?$", line)
            if extension:
                kind, title = extension.groups()
                i += 1
                body = []
                while i < len(lines) and lines[i].strip() != ":::":
                    body.append(lines[i])
                    i += 1
                if i == len(lines):
                    raise ValueError("扩展语法块未闭合")
                i += 1
                if kind in {"author", "engagement"}:
                    # Preserve user-supplied block content in the sole footer.
                    if kind == "author":
                        self.author = title or self.author or "{{作者名}}"
                        self.bio = "\n".join(body)
                    else:
                        self.footer_message = "\n".join(body)
                else:
                    comp = "pullquote" if kind == "quote" else "details" if kind == "details" else "warning"
                    out.append(self.c(comp, title=title or {"warning": "注意", "info": "说明", "tip": "提示"}.get(kind, "补充阅读"), body_html=self.blocks(body)))
                continue
            if line.strip() == "<details>":
                i += 1
                title, body = "补充阅读", []
                while i < len(lines) and lines[i].strip() != "</details>":
                    summary = re.fullmatch(r"\s*<summary>(.*?)</summary>\s*", lines[i])
                    if summary:
                        title = summary[1]
                    else:
                        body.append(lines[i])
                    i += 1
                if i == len(lines):
                    raise ValueError("details 未闭合")
                out.append(self.c("details", title=title, body_html=self.blocks(body)))
                i += 1
                continue
            if i + 1 < len(lines) and "|" in line and re.match(r"^\s*\|?\s*:?-{3,}:?\s*\|", lines[i + 1]):
                head = self.table_cells(line)
                separator = self.table_cells(lines[i + 1])
                rows = [head]
                i += 2
                while i < len(lines) and "|" in lines[i] and lines[i].strip():
                    rows.append(self.table_cells(lines[i]))
                    i += 1
                rendered = []
                for row_index, row in enumerate(rows):
                    cells = []
                    for col, cell in enumerate(row):
                        value = self.c("table_cell", body_html=self.inline(cell))
                        alignment = separator[col] if col < len(separator) else ""
                        align = "center" if alignment.startswith(":") and alignment.endswith(":") else "right" if alignment.endswith(":") else "left"
                        value = value.replace("padding:10px", "text-align:" + align + ";padding:10px")
                        if row_index == 0:
                            value = value.replace("<td ", "<th ").replace("</td>", "</th>")
                            value = value.replace("padding:10px", "background:" + self.theme["surface"] + ";font-weight:700;padding:10px")
                        cells.append(value)
                    rendered.append("<tr>" + "".join(cells) + "</tr>")
                out.append(self.c("table", rows_html="".join(rendered)))
                continue
            image = re.fullmatch(r"\s*!\[([^\]]*)\]\((.+?)\)\s*", line)
            if image:
                caption = image[1] + (" · GIF 动图" if image[1] and ".gif" in image[2].lower() else "")
                value = self.c("image", url=safe_url(image[2]), alt=image[1], caption=caption)
                if not image[1]:
                    value = re.sub(r"<figcaption\b.*?</figcaption>", "", value, flags=re.S)
                out.append(value)
                i += 1
                continue
            if re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", line):
                listing = [line]
                i += 1
                while i < len(lines) and lines[i].strip() and (
                    re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", lines[i]) or lines[i].startswith(("  ", "\t"))
                ):
                    listing.append(lines[i])
                    i += 1
                out.append(self.list_block(listing))
                continue
            foot = re.match(r"^\[\^([^\]]+)\]:\s*(.*)$", line)
            if foot:
                self.footnotes[foot[1]] = foot[2]
                i += 1
                continue
            reference = re.match(r"^\[([^\]]+)\]:\s*(\S+)\s*$", line)
            if reference:
                i += 1
                continue
            paragraph = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not self.starts_block(lines[i]) and not re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", lines[i]):
                if i + 1 < len(lines) and "|" in lines[i] and re.match(r"^\s*\|?\s*:?-{3,}:?\s*\|", lines[i + 1]):
                    break
                if re.match(r"^\[\^?[^\]]+\]:", lines[i]):
                    break
                paragraph.append(lines[i])
                i += 1
            joined = "\n".join(paragraph)
            rendered = self.inline(joined)
            rendered = rendered.replace("\n", "<br>")
            paragraph_html = self.c("paragraph", body_html=rendered)
            out.append("<!--prose-->" + paragraph_html + "<!--/prose-->" if prose_cards else paragraph_html)
        result = "".join(out)
        if prose_cards:
            def card(match):
                inner = match[0].replace("<!--prose-->", "").replace("<!--/prose-->", "")
                inner = inherit_paragraphs(inner)
                return self.c("prose_card", body_html=inner)
            result = re.sub(r"(?:<!--prose-->.*?<!--/prose-->)+", card, result, flags=re.S)
        return result

    def render(self, markdown):
        self.section_no = self.step_no = 0
        lines = markdown.replace("\r\n", "\n").splitlines()
        for line in lines:
            ref = re.match(r"^\[([^\]^]+)\]:\s*(\S+)\s*$", line)
            if ref:
                self.references[ref[1].lower()] = ref[2]
        title = "未命名文章"
        first = next((i for i, line in enumerate(lines) if line.strip()), None)
        if first is not None and re.match(r"^#\s+", lines[first]):
            title = re.sub(r"^#\s+", "", lines.pop(first))
        # Merge an original terminal signature, never duplicate it.
        self.footer_message = "如果觉得有用，欢迎点赞、在看、转发三连，我们下篇见。"
        tail = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
        if tail is not None and re.match(r"^我是[^，,。]+", lines[tail]):
            signature = lines.pop(tail)
            match = re.match(r"^我是([^，,。]+)[，,]?(.*)$", signature)
            if match:
                self.author = self.author or match[1]
                bio = match[2]
                split = re.search(r"如果", bio)
                if split:
                    self.footer_message = bio[split.start():]
                    bio = bio[:split.start()]
                self.bio = self.bio or bio
        chapters = [re.sub(r"^##\s+", "", line) for line in lines if line.startswith("## ")][:3]
        cover = self.c("hero", category=self.theme["name"], meta="深度排版实战", credit="原创思考",
                       title=title, subtitle="")
        content = self.blocks(lines, prose_cards=True)
        toc = ""
        if chapters:
            items = "".join(self.c("toc_item", number=str(i).zfill(2), title=t,
                                  description="") for i, t in enumerate(chapters, 1))
            toc = self.c("toc", items_html=items, toc_hint="精选看点")
        # Opening quote precedes TOC, matching the source article.
        if content.startswith("<section") and lines and next((l for l in lines if l.strip()), "").startswith(">"):
            # blocks already preserves the quote; do not relocate/split its nested HTML.
            # Put the directory after that leading quote using a balanced tag scan.
            depth, end = 0, None
            for m in re.finditer(r"</?section\b[^>]*>", content):
                depth += -1 if m[0].startswith("</") else 1
                if depth == 0:
                    end = m.end()
                    break
            if end:
                content = content[:end] + toc + content[end:]
                toc = ""
        author = self.author or "{{作者名}}"
        fields = dict(author=author, initial=author[0] if self.author else "作",
                      bio=chinese_punctuation(self.bio or "{{简介}}"))
        if self.qr_url:
            footer = self.c("signature", qr_url=self.qr_url, qr_caption="扫码关注",
                            signature_note="长按右侧二维码关注专栏", **fields)
        else:
            footer = self.c("signature_no_qr_" + self.layout, **fields)
        notes = "".join(self.c("footnote", number="[^" + n + "]", body_html=self.inline(text))
                        for n, text in self.footnotes.items())
        result = self.c("container", body_html=cover + toc + content + notes + footer +
                        self.c("engagement", message=chinese_punctuation(self.footer_message)))
        errors, warnings, _ = validate(result)
        if errors or warnings:
            raise ValueError("输出未通过校验：\n" + "\n".join(errors + warnings))
        return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", nargs="?", type=Path)
    ap.add_argument("--theme", default="emerald")
    ap.add_argument("--layout", choices=LAYOUTS)
    ap.add_argument("--author")
    ap.add_argument("--bio")
    ap.add_argument("--qr-url", help="用户提供的真实关注二维码；不默认冒用设计稿示例二维码")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--list-themes", action="store_true")
    args = ap.parse_args()
    if args.list_themes:
        for theme in catalog():
            print("%-18s %s" % (theme["id"], theme["name"]))
        return
    if not args.input or not args.output:
        ap.error("需要 input 和 --output")
    try:
        result = Renderer(args.theme, args.layout, args.author, args.bio, args.qr_url).render(
            args.input.read_text(encoding="utf-8")
        )
    except ValueError as exc:
        ap.exit(1, str(exc) + "\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")
    print("已生成公众号主题正文（0 ERROR / 0 WARNING）：" + str(args.output.resolve()))


if __name__ == "__main__":
    main()
