#!/usr/bin/env python3
"""Content-preservation, provenance, layout and WeChat regressions."""

import hashlib
import json
import re
import unittest
from html.parser import HTMLParser

from build_stitch_themes import clean_template_styles, compact_template_style, Compiler, Node, compile_templates, extract_catalog, source_components
from render_stitch_article import Renderer
from stitch_themes import ROOT, LAYOUTS, catalog, chapter, component, templates
from validate_gzh_html import validate


class Text(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.values = []
        self.feed(value)

    def handle_data(self, value):
        self.values.append(value)

    def text(self):
        return "".join(self.values).replace("\u00a0", " ")


ARTICLE = """# 原文完整性测试

> 引言中有==核心观点==。

这里保留**重点判断**、++关键短语++、~~原始删除线~~以及 `foo("x", 1)`。

## 第一章独特题目

第一段独特内容，不应被设计稿演示文案覆盖。

### 第一步独特标题

- 第一项保留
  - 嵌套第二项保留
- [x] 已完成事项保留
- [ ] 未完成事项保留

3. 有序第三项保留
4. 有序第四项保留

```python
if True:
    print("中文", {"a": 1})

print("最后一行")
```

| 字段 | 说明 |
| :--- | ---: |
| 列甲 | 列乙 |
| 有转义\\|分隔 | 保留数据 |

![原始图注](https://example.com/image.png)

![](https://example.com/plain.png)

![动态图注](https://example.com/demo.gif)

[原始链接](https://example.com/read?q=1&x=2) 与脚注[^1]。

::: warning 真实警示标题
真实警示正文保留。
:::

::: quote
真实强调金句保留。
:::

<details>
<summary>补充内容标题</summary>
补充段落保留。
</details>

[^1]: 脚注原始定义保留。

## 第二章独特题目

结尾内容保留。
"""


class StitchTests(unittest.TestCase):
    def test_15_exact_source_colorways(self):
        self.assertEqual(catalog(), extract_catalog())
        self.assertEqual(len(catalog()), 15)
        index = (ROOT / "references/theme-index.md").read_text()
        for theme in catalog():
            self.assertIn("theme-" + theme["id"] + ".md", index)
        self.assertNotIn("theme-moyu-green.md", index)

    def test_source_checksums(self):
        manifest = json.loads((ROOT / "assets/stitch/manifest.json").read_text())
        self.assertEqual(len(manifest["screens"]), 5)
        for source in manifest["screens"]:
            self.assertEqual(hashlib.sha256((ROOT / source["source"]).read_bytes()).hexdigest(), source["sha256"])

    def test_templates_are_reproducible_from_sources(self):
        nodes = source_components()
        for theme in catalog():
            self.assertEqual(templates(theme["id"]), compile_templates(theme, nodes))

    def test_all_45_combinations_pass_and_preserve_content(self):
        for theme in catalog():
            for layout in LAYOUTS:
                with self.subTest(theme=theme["id"], layout=layout):
                    output = Renderer(theme["id"], layout).render(ARTICLE)
                    errors, warnings, _ = validate(output)
                    self.assertEqual(errors + warnings, [])
                    text = Text(output).text()
                    for phrase in ["第一段独特内容", "嵌套第二项保留", "已完成事项保留",
                                   "未完成事项保留", "有序第三项保留", "有序第四项保留",
                                   'print("中文", {"a": 1})', 'print("最后一行")',
                                   "列甲", "列乙", "有转义|分隔", "保留数据", "原始图注",
                                   "动态图注", "GIF 动图", "真实警示正文", "真实强调金句",
                                   "补充段落", "脚注原始定义", "结尾内容", 'foo("x", 1)']:
                        self.assertIn(phrase, text)
                    self.assertIn("✓", text)
                    self.assertIn("□", text)
                    self.assertNotIn("甲木 × 摸鱼小李", text)
                    self.assertNotIn("许多创作者在刚接触排版时", text)
                    self.assertIn('src="https://example.com/plain.png"', output)
                    self.assertEqual(output.count("<figcaption"), 2)
                    self.assertNotIn("material-symbols", output)
                    self.assertNotIn("{{body_html}}", output)
                    self.assertIn("{{作者名}}", text)
                    self.assertIn("{{简介}}", text)
                    self.assertEqual(text.count("第一段独特内容"), 1)

    def test_layout_identity_not_just_palette(self):
        ruler = chapter("emerald", "本章标题", 1, "ruler")
        overprint = chapter("emerald", "本章标题", 1, "overprint")
        pure = chapter("emerald", "本章标题", 1, "pure")
        self.assertIn("width:44px", ruler)
        self.assertIn("font-size:58px", overprint)
        self.assertIn("margin-top:-28px", overprint)
        self.assertIn("margin-bottom:-30px", overprint)
        self.assertIn("text-align:left", overprint)
        self.assertNotIn("01", Text(pure).text())
        for value in (ruler, overprint, pure):
            self.assertNotIn("position:absolute", value)
            self.assertNotIn("演示", Text(value).text())

    def test_footer_geometry_and_genuine_qr_option(self):
        for layout in LAYOUTS:
            output = Renderer("emerald", layout, "真实作者", "真实简介", "https://example.com/real-qr.png").render("# 标题\n\n正文。")
            self.assertEqual(validate(output)[:2], ([], []))
            self.assertIn('src="https://example.com/real-qr.png"', output)
            self.assertIn("width:88px", output)
            self.assertIn("width:72px;height:72px", output)
            self.assertIn("长按右侧二维码关注专栏", Text(output).text())
            self.assertIn("扫码关注", Text(output).text())
            self.assertIn("width:36px;height:36px" if layout == "pure" else "width:32px;height:32px", output)
            self.assertNotIn("甲木 × 摸鱼小李", Text(output).text())
        with self.assertRaises(ValueError):
            Renderer(qr_url="javascript:alert(1)")

    def test_share_icons_and_labels_are_not_substituted(self):
        for layout in LAYOUTS:
            value = component("emerald", "engagement_"+layout, message="正文提示")
            text = Text(value).text()
            self.assertIn("点赞", text)
            self.assertIn("在看", text)
            self.assertIn("转发", text)
            self.assertNotIn("♡", text)
            self.assertTrue("padding-top:8px" in value or
                            "padding:8px 0px 0px;" in value or "padding:8px 0 0;" in value)
            for icon in ("thumb_up", "visibility", "share"):
                path = re.search(r'<path d="([^"]+)"', (ROOT/"assets/stitch/icons"/(icon+".svg")).read_text())[1]
                self.assertIn(path, value)
            self.assertIn("color:#121c2a", value)

    def test_original_palette_comparison_has_the_same_source_content(self):
        from build_stitch_comparison import ORIGINAL
        from build_stitch_themes import load
        for layout in LAYOUTS:
            main = next(load(layout).nodes("main")).elements()[0]
            compiled = Compiler(ORIGINAL).render(main)
            self.assertIn("为什么之前的排版总觉得", Text(compiled).text())
            self.assertIn("甲木 × 摸鱼小李", Text(compiled).text())
            self.assertIn("rgb(6, 46, 36)", compiled)
            self.assertIn("rgb(0, 105, 72)", compiled)

    def test_signature_is_merged_not_duplicated(self):
        source = "# 标题\n\n正文内容。\n\n我是张三，研究排版。如果这篇有用，请转发。"
        output = Renderer().render(source)
        text = Text(output).text()
        self.assertEqual(text.count("张三"), 1)
        self.assertIn("研究排版。", text)
        self.assertEqual(text.count("如果这篇有用"), 1)
        self.assertNotIn("{{作者名}}", text)
        self.assertNotIn("<img", output)

    def test_pure_neutral_theme_has_no_literal_sample_greens(self):
        output = Renderer("monochrome-zen", "pure").render(ARTICLE)
        for color in ("#059669", "#005137", "#A7F3D0", "#34D399", "#064E3B"):
            self.assertNotIn(color.lower(), output.lower())

    def test_unknown_theme_does_not_fall_back_to_old_library(self):
        with self.assertRaises(ValueError):
            Renderer("moyu-green")

    def test_unsafe_resource_url_rejected(self):
        with self.assertRaises(ValueError):
            Renderer().render("# 标题\n\n![图片](javascript:alert)")

    def test_raw_html_cannot_execute(self):
        output = Renderer().render("# 标题\n\n<script>alert(1)</script>")
        self.assertNotIn("<script", output)
        self.assertIn("&lt;script&gt;", output)

    def test_unclosed_code_does_not_silently_lose_content(self):
        with self.assertRaises(ValueError):
            Renderer().render("# 标题\n\n```js\nconst important = 1;")

    def test_new_source_utilities_fail_closed(self):
        with self.assertRaises(ValueError):
            Compiler(catalog()[0]).render(Node("div", {"class": "unrecognized-design-rule"}))

    def test_field_content_cannot_inject_placeholder(self):
        output = component("emerald", "step", number=1, title="{{subtitle}}", subtitle="REAL")
        self.assertIn("{{subtitle}}", Text(output).text())


class TemplateStyleTests(unittest.TestCase):
    def test_component_root_keeps_typography_and_children_inherit(self):
        source = '<section style="color:red;font-size:14px;"><p style="color:red;font-size:14px;"><span leaf="">正文。</span></p></section>'
        result = clean_template_styles(source)
        self.assertEqual(result.count("color:red;"), 1)
        self.assertEqual(result.count("font-size:14px;"), 1)

    def test_separate_component_roots_never_share_typography(self):
        source = '<section style="color:red;">{{body_html}}</section>'
        self.assertIn("color:red;", clean_template_styles(source))
        self.assertIn("color:red;", clean_template_styles(source))

    def test_heading_keeps_native_typography_and_child_overrides(self):
        source = '<section style="font-weight:400;color:red;"><h3 style="font-weight:400;color:red;"><span style="color:blue;">文字</span></h3></section>'
        result = clean_template_styles(source)
        self.assertIn('<h3 style="font-weight:400;color:red;">', result)
        self.assertIn('color:blue;', result)

    def test_relative_font_sizes_are_not_deduplicated(self):
        # Relative sizes compose; matching strings do not imply equal appearance.
        for value in ("1.2em", "120%"):
            source = f'<section style="font-size:{value};"><span style="font-size:{value};">文字</span></section>'
            self.assertEqual(clean_template_styles(source).count(f"font-size:{value};"), 2)

    def test_renderer_only_assembles_templates(self):
        import inspect
        import render_stitch_article
        self.assertNotIn("compact_html", inspect.getsource(render_stitch_article))

    def test_content_code_and_svg_are_untouched(self):
        svg = '<svg viewBox="0 0 1 1"><rect width="1" style="opacity:1;" /></svg>'
        source = '<section style="color:red;font-size:14px;"><p style="color:red;font-size:14px;opacity:1;"><span leaf="">正文。</span><span leaf=""></span></p><span style="font-family:monospace;"><span leaf="">A  B\n&lt;code&gt; &amp; "x"</span></span>' + svg + '</section>'
        result = clean_template_styles(source)
        self.assertEqual(Text(source).text(), Text(result).text())
        self.assertIn(svg, result)
        self.assertNotIn('<span leaf=""></span>', result)
        self.assertIn('A  B\n&lt;code&gt; &amp; "x"', result)
        self.assertEqual(validate(result)[:2], ([], []))
        self.assertEqual(clean_template_styles(result), result)

    def test_box_shorthands(self):
        style = "padding-top:8px;padding-right:0px;padding-bottom:0px;padding-left:0px;"
        self.assertEqual(compact_template_style(style), "padding:8px 0 0;")

    def test_shorthand_override_not_erased(self):
        style = "".join(f"border-{side}-{kind}:{value};" for side in ("top", "right", "bottom", "left")
                        for kind, value in (("width", "0px"), ("style", "solid"), ("color", "red")))
        style += "border-left:6px solid green;"
        result = compact_template_style(style)
        self.assertIn("border-width:0 0 0 6px;", result)
        self.assertIn("border-color:red red red green;", result)
        self.assertNotIn("border:0;", result)

    def test_border_resolution_follows_source_order(self):
        style = "border:1px solid red;border-color:blue;border-left:6px dashed green;"
        result = compact_template_style(style)
        # This short input is already smaller; keep it rather than expanding.
        self.assertEqual(result, style)
        long = style + "border-left-width:2px;"
        result = compact_template_style(long)
        self.assertEqual(result, long)

    def test_font_family_serialization_stays_compatible_with_renderer(self):
        source = '<p style="font-family:&#x27;PingFang SC&#x27;;"><span leaf="">正文。</span></p>'
        result = clean_template_styles(source)
        self.assertIn("font-family:&#x27;PingFang SC&#x27;;", result)
        quoted = '<p style="font-family:&quot;A&amp;B&quot;;">text</p>'
        self.assertIn('&quot;A&amp;B&quot;', clean_template_styles(quoted))

    def test_zero_units_do_not_touch_strings_urls_or_flex_basis(self):
        style = "padding:0px 12px;flex:1 1 0%;background:url('0px.png');"
        result = compact_template_style(style)
        self.assertIn("padding:0 12px;", result)
        self.assertIn("flex:1 1 0%;", result)
        self.assertIn("url('0px.png')", result)

    def test_only_transparent_shadow_layers_are_removed(self):
        style = "box-shadow:rgba(0,0,0,0.0) 0px 0px 0px 0px, rgba(0,0,0,0.05) 0px 1px 2px 0px;"
        result = compact_template_style(style)
        self.assertEqual(result, "box-shadow:rgba(0,0,0,0.05) 0 1px 2px 0;")

    def test_table_retains_inheritance_boundary(self):
        result = clean_template_styles('<section style="color:red;line-height:24px;"><table style="color:red;line-height:24px;"><tr><td>text</td></tr></table></section>')
        self.assertIn('<table style="color:red;line-height:24px;">', result)

    def test_css_strings_and_important_not_broken(self):
        style = 'background:url("a;b.png");font-family:"A;B",sans-serif;'
        self.assertIn('a;b.png', compact_template_style(style))
        important = "color:red!important;color:blue;"
        self.assertEqual(compact_template_style(important), important)


if __name__ == "__main__":
    unittest.main()
