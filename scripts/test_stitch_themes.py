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
                    self.assertNotIn("Jacob", text)
                    self.assertNotIn("许多创作者在刚接触排版时", text)
                    self.assertIn('src="https://example.com/plain.png"', output)
                    self.assertEqual(output.count("<figcaption"), 2)
                    self.assertNotIn("material-symbols", output)
                    self.assertNotIn("{{body_html}}", output)
                    self.assertNotIn("{{作者名}}", text)
                    self.assertNotIn("{{简介}}", text)
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
            self.assertNotIn("Jacob", Text(output).text())
        with self.assertRaises(ValueError):
            Renderer(qr_url="javascript:alert(1)")

    def test_signature_requires_author_and_has_no_placeholder_or_empty_bio(self):
        for layout in LAYOUTS:
            for author in (None, "", " \t"):
                output = Renderer("emerald", layout, author=author,
                                  bio="只有简介", qr_url="https://example.com/qr.png").render("# 标题")
                self.assertNotIn("只有简介", output)
                self.assertNotIn("https://example.com/qr.png", output)
                self.assertIn("收藏方便回看", output)
            for bio in (None, "", " \t"):
                output = Renderer("emerald", layout, author="张三", bio=bio).render("# 标题")
                self.assertIn("张三", output)
                self.assertNotIn("{{简介}}", output)
                self.assertNotIn("{{作者名}}", output)
                self.assertNotRegex(output, r'<p\b[^>]*><span leaf=""></span></p>')
                self.assertNotIn("扫码关注", output)

    def test_engagement_restores_source_card_as_static_rich_text(self):
        for layout in LAYOUTS:
            value = component("emerald", "engagement_"+layout, message="正文提示")
            text = Text(value).text()
            self.assertIn("正文提示", text)
            self.assertIn("既然看到这里了", text)
            for label in ("点赞", "收藏", "分享"):
                self.assertEqual(text.count(label), 1)
            for unwanted in ("<button", "<a ", "<script", "onclick="):
                self.assertNotIn(unwanted, value)
            for restored in ("<svg", "border-radius:", "background:"):
                self.assertIn(restored, value)
            self.assertEqual(validate(value)[:2], ([], []))
            self.assertIn('stroke-width="1.8"', value)
            self.assertIn('d="M19 21l-7-5-7 5V5', value)
            self.assertNotIn("在看", text)
            output = Renderer("emerald", layout).render("# 标题\n\n正文。")
            for label in ("点赞", "分享", "收藏"):
                self.assertEqual(Text(output).text().count(label), 1 if label == "点赞" else 2)
            self.assertNotIn("转发", Text(output).text())
            self.assertNotIn("三连", output)

    def test_explicit_engagement_copy_is_preserved_inside_restored_card(self):
        for layout in LAYOUTS:
            output = Renderer("emerald", layout).render(
                "# 标题\n\n::: engagement\n欢迎转发给同事，也欢迎留言讨论。\n:::")
            self.assertEqual(Text(output).text().count("欢迎转发给同事，也欢迎留言讨论。"), 1)
            self.assertNotIn("如果这篇对你有帮助", output)
            self.assertNotIn("收藏方便回看", output)
            self.assertEqual(Text(output).text().count("点赞"), 1)

    def test_original_palette_comparison_has_the_same_source_content(self):
        from build_stitch_comparison import ORIGINAL
        from build_stitch_themes import load
        for layout in LAYOUTS:
            main = next(load(layout).nodes("main")).elements()[0]
            compiled = Compiler(ORIGINAL).render(main)
            self.assertIn("为什么之前的排版总觉得", Text(compiled).text())
            self.assertIn("Jacob", Text(compiled).text())
            self.assertIn("rgb(6, 46, 36)", compiled)
            self.assertIn("rgb(0, 105, 72)", compiled)

    def test_signature_is_merged_not_duplicated(self):
        source = "# 标题\n\n正文内容。\n\n我是张三，研究排版。如果这篇有用，请转发。"
        output = Renderer(author="张三").render(source)
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

    def test_hero_hides_default_meta_and_credit_without_empty_badges(self):
        for theme in catalog():
            for layout in LAYOUTS:
                output = Renderer(theme["id"], layout).render("# 测试标题")
                self.assertNotIn("深度排版实战", output)
                self.assertNotIn("原创思考", output)
                hero = component(theme["id"], "hero_" + layout + "_in_article",
                                 category="主题", meta="", credit="",
                                 title="测试标题", subtitle="")
                self.assertIn("主题", Text(hero).text())
                self.assertIn("测试标题", Text(hero).text())
                self.assertNotRegex(hero, r'<span leaf=""[^>]*>\s*</span>')
                self.assertNotRegex(hero, r'<span\b[^>]*><span leaf=""></span></span>')

    def test_step_omits_empty_subtitle_without_changing_real_content(self):
        for theme in catalog():
            for key in ("step", "step_in_article"):
                for subtitle in ("", " \t\n"):
                    output = component(theme["id"], key, number=1,
                                       title="{{subtitle}}", subtitle=subtitle)
                    self.assertEqual(output.count("<span"), 2)
                    self.assertIn("{{subtitle}}", Text(output).text())
                    self.assertNotRegex(output, r'<span\b[^>]*>\s*</span>')
                output = component(theme["id"], key, number=1,
                                   title="标题", subtitle="真实副标题")
                self.assertEqual(output.count("<span"), 3)
                self.assertIn("真实副标题", Text(output).text())


class TemplateStyleTests(unittest.TestCase):
    def test_sample_identity_is_jacob_and_does_not_leak_into_templates(self):
        sample = (ROOT / "assets/sample-article.md").read_text()
        self.assertIn("我是Jacob，致力于分享一些AI技术、AI干货内容。", sample)
        for layout in LAYOUTS:
            output = Renderer("emerald", layout).render(sample)
            self.assertEqual(Text(output).text().count("Jacob"), 1)
            self.assertIn("致力于分享一些AI技术、AI干货内容。", Text(output).text())
            self.assertIn("{{initial}}", templates("emerald")["signature_" + layout])
            self.assertNotIn("Jacob", Renderer("emerald", layout).render("# 无署名\n\n正文。"))

    def test_engagement_has_no_design_credit(self):
        for theme in catalog():
            for layout in LAYOUTS:
                output = templates(theme["id"])["engagement_" + layout]
                self.assertNotIn("感谢阅读 · 原创排版设计分享", output)
                self.assertEqual(Text(output).text(),
                                 "既然看到这里了{{message}}点赞收藏分享感谢阅读")
                self.assertNotIn("三连", output)

    def test_skill_has_no_default_identity_and_cards_require_author(self):
        skill = (ROOT / "SKILL.md").read_text()
        self.assertNotIn('--author "Jacob" --bio "致力于分享一些AI技术、AI干货内容。"', skill)
        for source in ("# 标题\n\n我是张三，研究排版。",
                       "# 标题\n\n::: author 张三\n研究排版。\n:::"):
            output = Renderer().render(source)
            self.assertIn("张三", Text(output).text())
            self.assertEqual(Text(output).text().count("张三"), 1)
            self.assertNotIn("{{作者名}}", output)
            self.assertNotIn("扫码关注", output)
            self.assertEqual(validate(output)[:2], ([], []))
        for layout in LAYOUTS:
            output = Renderer("emerald", layout, author="Jacob",
                              bio="致力于分享一些AI技术、AI干货内容。").render("# 标题\n\n正文。")
            text = Text(output).text()
            self.assertEqual(text.count("Jacob"), 1)
            self.assertEqual(text.count("致力于分享一些AI技术、AI干货内容。"), 1)
            self.assertEqual(text.count("既然看到这里了"), 1)
            self.assertNotIn("<img", output)
            self.assertEqual(validate(output)[:2], ([], []))

    def test_semantic_colors_keep_distinct_background_and_deep_text_roles(self):
        from build_stitch_themes import semantic_palette
        for theme in catalog():
            palette = semantic_palette(theme)
            self.assertEqual(len(set(palette.values())), 4)
            compiler = Compiler(theme)
            self.assertEqual(compiler.remap("#eff3ff"), theme["surface"])
            self.assertEqual(compiler.remap("#6cf8bb"), palette["emphasis_surface"])
            self.assertEqual(compiler.remap("#a7f3d0"), palette["on_deep_muted"])
            self.assertEqual(compiler.remap("rgba(108,248,187,0.4)"),
                             "rgba(%s,0.4)" % ",".join(str(int(
                                 palette["emphasis_surface"][i:i+2], 16))
                                 for i in (1, 3, 5)))
            data = templates(theme["id"])
            for layout in LAYOUTS:
                signature = data["signature_" + layout + "_in_article"].lower()
                self.assertIn("color:" + palette["on_deep_muted"].lower(), signature)

    def test_ordered_badge_centers_on_first_line_not_entire_item(self):
        from html import unescape
        from stitch_themes import declarations
        for theme in catalog():
            data = templates(theme["id"])
            root = dict(declarations(unescape(
                re.search(r'style="([^"]*)"', data["ordered_item"])[1])))
            for key in ("ordered_item", "ordered_item_in_list"):
                value = data[key]
                self.assertIn("align-items:flex-start;", value)
                self.assertNotIn("margin-top:", value)
                self.assertIn('height:' + root["line-height"] +
                              ';display:flex;align-items:center;flex:none;', value)
                self.assertEqual(value.count("{{number}}"), 1)
                self.assertEqual(value.count("{{body_html}}"), 1)

    def test_spacing_wrapper_merges_without_reserializing_content(self):
        from build_stitch_themes import merge_component_spacing
        body = '<svg viewBox="0 0 1 1"><rect width="1"/></svg>{{body_html}}'
        card = ('<section style="display:flex;font-family:&#x27;PingFang SC&#x27;;'
                'margin-top:0;margin-bottom:0;padding:14px;">' + body + '</section>')
        source = '<section style="margin:0 0 24px;">' + card + '</section>'
        result = merge_component_spacing(source)
        self.assertEqual(result.count('<section'), 1)
        self.assertIn('font-family:&#x27;PingFang SC&#x27;;', result)
        self.assertIn('padding:14px;margin:0 0 24px;', result)
        self.assertIn(body, result)
        self.assertEqual(merge_component_spacing(result), result)

    def test_card_paragraph_parses_entities_and_preserves_effective_wrapping(self):
        from render_stitch_article import inherit_paragraphs
        source = ('<p style="box-sizing:border-box;margin:12px 0;'
                  'font-family:&#x27;PingFang SC&#x27;,sans-serif;'
                  'font-size:14px;color:red;overflow-wrap:anywhere;'
                  'background:url(&quot;a;b.png&quot;);">'
                  '<span leaf="">正文。</span></p>')
        result = inherit_paragraphs(source)
        self.assertNotIn('PingFang', result)
        self.assertNotIn('font-size:', result)
        self.assertNotIn('overflow-wrap:', result)
        self.assertIn('margin:0;', result)
        self.assertIn('background:url(&quot;a;b.png&quot;);', result)
        self.assertEqual(Text(source).text(), Text(result).text())
        self.assertEqual(inherit_paragraphs(result), result)
        self.assertIn('overflow-wrap:anywhere;', inherit_paragraphs(
            '<p style="margin:12px;overflow-wrap:anywhere;">正文。</p>'))
        self.assertIn('overflow-wrap:anywhere;', inherit_paragraphs(
            '<p style="font-family:sans-serif;overflow-wrap:anywhere;">正文。</p>'))

    def test_spacing_wrapper_retains_unsafe_geometry_and_siblings(self):
        from build_stitch_themes import merge_component_spacing
        for extra in ('width:100%;', 'position:relative;', 'margin:12px 0;',
                      'margin-left:auto;', 'transform:translateX(1px);'):
            card = ('<section style="display:block;margin-top:0;'
                    'margin-bottom:0;' + extra + '">{{body_html}}</section>')
            source = '<section style="margin:0 0 24px;">' + card + '</section>'
            self.assertEqual(merge_component_spacing(source), source)
        source = ('<section style="margin:0 0 24px;">'
                  '<section style="display:block;margin:0;">甲</section>'
                  '<section>乙</section></section>')
        self.assertEqual(merge_component_spacing(source), source)

    def test_quote_row_merges_only_exact_undecorated_layout(self):
        from build_stitch_themes import merge_quote_layout
        outer = '<section style="display:block;padding:20px;border-left:6px solid red;">'
        row = ('<section style="box-sizing:border-box;display:flex;gap:12px;'
               'flex-direction:row;flex:0 1 auto;margin-top:0;margin-bottom:0;'
               'border-radius:0;border:0 solid #e5e7eb;padding:0;">')
        body = '<section>引号</section><section>{{text_html}}</section>'
        source = outer + row + body + '</section></section>'
        result = merge_quote_layout(source)
        self.assertEqual(result.count('<section'), source.count('<section') - 1)
        self.assertIn('display:flex;gap:12px;flex-direction:row;', result)
        self.assertIn(body, result)
        for changed in ('padding:1px;', 'margin-bottom:1px;', 'width:100%;padding:0;'):
            unsafe = source.replace('padding:0;', changed)
            self.assertEqual(merge_quote_layout(unsafe), unsafe)

    def test_text_leaf_merges_but_flex_leaf_keeps_layout(self):
        from build_stitch_themes import optimize_template_structure
        source = '<span style="display:block;color:red;"><span leaf="">文字</span></span>'
        self.assertEqual(optimize_template_structure(source),
                         '<span leaf="" style="display:block;color:red;">文字</span>')
        flex = '<span style="display:flex;"><span leaf="">文字</span></span>'
        self.assertEqual(optimize_template_structure(flex), flex)

    def test_svg_keeps_primitive_geometry(self):
        from build_stitch_themes import optimize_template_structure
        source = '<svg viewBox="0 0 64 1"><rect x="0" y="0" width="1.05" height="1" fill="rgb(5,150,105)" fill-opacity="1.0000"/></svg>'
        result = optimize_template_structure(source)
        self.assertIn('width="1.05" height="1" fill="#059669"', result)
        self.assertNotIn("fill-opacity", result)
        self.assertNotIn(' y="0"', result)

    def test_code_frame_contract_and_standalone_fallback(self):
        data = templates("emerald")
        self.assertIn("font-family:", data["code_row"])
        self.assertNotIn("font-family:", data["code_row_in_frame"])
        self.assertNotIn("monospace;", data["code_row_in_frame"])
        self.assertIn("line-height:1.6;", data["code_row_in_frame"])
        self.assertIn('leaf=""', data["code_row_in_frame"])
        for theme in catalog():
            for name in ("code_row", "code_row_in_frame", "code_row_in_rows"):
                row = templates(theme["id"])[name]
                self.assertTrue(row.startswith("<p "))
                self.assertNotIn("{{number}}", row)
                for prop in ("display:flex", "gap:", "min-width:", "flex-shrink:"):
                    self.assertNotIn(prop, row)
                self.assertEqual(row.count("<span"), 1)
        value = Renderer().code("    first\n\nlast < & >", "txt", in_article=True)
        self.assertEqual(value.count("<p "), 3)
        self.assertIn("\u00a0" * 4 + "first", value)
        self.assertIn('leaf="">\u00a0</span>', value)
        self.assertIn("last\u00a0&lt;\u00a0&amp;\u00a0&gt;", value)
        self.assertNotIn('leaf="">01</span>', value)

    def test_step_has_no_outer_card_but_keeps_number_badge(self):
        from html import unescape
        from stitch_themes import declarations
        for theme in catalog():
            for key in ("step", "step_in_article"):
                value = templates(theme["id"])[key]
                styles = [dict(declarations(unescape(s)))
                          for s in re.findall(r'style="([^"]*)"', value)]
                card = next(s for s in styles if s.get("display") == "flex")
                self.assertFalse(any(k.startswith(
                    ("background", "border", "padding", "box-shadow")) for k in card))
                self.assertTrue(any(s.get("background") == theme["primary"]
                                    and s.get("width") == "28px" for s in styles))

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
        self.assertIn("font-family:PingFang SC;", result)
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
        self.assertEqual(result, "box-shadow:rgba(0,0,0,.05) 0 1px 2px 0;")
        self.assertEqual(compact_template_style(result), result)
        mixed = "box-shadow:rgba(0,0,0,0.0) 0 0px 0 0px, rgba(0,0,0,.1) 0 1px 2px 0;"
        self.assertNotIn("rgba(0,0,0,0.0)", compact_template_style(mixed))
        visible = "box-shadow:rgba(0,0,0,0.1) 0 0 0 0;"
        self.assertEqual(compact_template_style(visible), visible.replace("0.1", ".1"))

    def test_final_default_pass_is_tag_scoped_and_keeps_resets(self):
        style = ("display:block;flex:0 1 auto;flex-direction:row;"
                 "border:0 solid #e5e7eb;border-radius:0;padding:0;"
                 "margin-top:0;margin-bottom:0;box-sizing:border-box;")
        result = compact_template_style(style, tag="section", minimal=True)
        self.assertEqual(result, ";")
        paragraph = compact_template_style(style, tag="p", minimal=True)
        self.assertIn("display:block;", paragraph)
        self.assertIn("padding:0;", paragraph)
        self.assertIn("margin-top:0;", paragraph)
        self.assertNotIn("margin:0;", paragraph)
        side = "border:0 solid #e5e7eb;border-left:6px solid red;"
        self.assertNotIn("border:0;", compact_template_style(side, minimal=True))
        unsafe = "flex-shrink:0;flex:0 1 auto;"
        self.assertIn("flex:0 1 auto;", compact_template_style(unsafe, minimal=True))
        important = "border-radius:0!important;display:block;"
        self.assertEqual(compact_template_style(important, tag="section", minimal=True),
                         important)

    def test_shared_style_parser_and_attribute_escape_round_trip(self):
        from stitch_themes import declarations, escape_style_attribute
        from html import unescape
        style = '''font-family:'A;B',sans-serif;background:url("a;b.png");padding:0;'''
        self.assertEqual(declarations(style), [
            ("font-family", "'A;B',sans-serif"),
            ("background", 'url("a;b.png")'), ("padding", "0")])
        self.assertEqual(unescape(escape_style_attribute(style)), style)
        self.assertNotIn("&#x27;", escape_style_attribute(style))

    def test_compiled_minimal_templates_are_idempotent_and_keep_quote_layout(self):
        for theme in catalog():
            data = templates(theme["id"])
            for key, value in data.items():
                with self.subTest(theme=theme["id"], component=key):
                    self.assertEqual(clean_template_styles(value, minimal=True), value)
            for layout in LAYOUTS:
                quote = data["quote_" + layout]
                self.assertIn("display:flex;gap:12px;", quote)
                self.assertIn("border-left:6px solid ", quote)
                self.assertNotIn('<section style="margin:0 0 24px;"><section', quote)

    def test_table_retains_inheritance_boundary(self):
        result = clean_template_styles('<section style="color:red;line-height:24px;"><table style="color:red;line-height:24px;"><tr><td>text</td></tr></table></section>')
        self.assertIn('<table style="color:red;line-height:24px;">', result)

    def test_css_strings_and_important_not_broken(self):
        style = 'background:url("a;b.png");font-family:"A;B",sans-serif;'
        self.assertIn('a;b.png', compact_template_style(style))
        important = "color:red!important;color:blue;"
        self.assertEqual(compact_template_style(important), important)

    def test_css_lexical_compaction_preserves_urls_and_unknown_fonts(self):
        source = "font-family:'A;B',sans-serif;background:url('0.5-#ffffff.png');"
        result = compact_template_style(source)
        self.assertIn("'A;B'", result)
        self.assertIn("url('0.5-#ffffff.png')", result)
        result = compact_template_style(
            "color:#ffffff;letter-spacing:0.5px;font-family:'SF Mono',monospace;")
        self.assertIn("color:#fff;", result)
        self.assertIn("letter-spacing:.5px;", result)
        self.assertIn("font-family:SF Mono,monospace;", result)

    def test_span_sizing_only_removed_without_effective_box_geometry(self):
        for extra in ("min-width:24px;", "width:10px;", "padding:1px;",
                      "padding-left:1px;", "border-bottom:1px solid red;"):
            result = compact_template_style("box-sizing:border-box;" + extra,
                                            tag="span", minimal=True)
            self.assertIn("box-sizing:border-box;", result)
        result = compact_template_style(
            "box-sizing:border-box;min-width:0;border:0;padding:0;"
            "margin-top:0;margin-bottom:0;margin-left:4px;", tag="span", minimal=True)
        self.assertNotIn("box-sizing:", result)
        self.assertNotIn("padding:", result)
        self.assertIn("min-width:0;", result)
        self.assertIn("margin-left:4px;", result)
        result = compact_template_style("margin:4px;margin-top:0;",
                                        tag="span", minimal=True)
        self.assertIn("margin-top:0;", result)

    def test_background_shorthand_keeps_image_and_other_background_properties(self):
        result = compact_template_style("background-color:#ffffff;", minimal=True)
        self.assertEqual(result, "background:#fff;")
        for extra in ("background-image:url(image.png);", "background-size:cover;"):
            result = compact_template_style("background-color:#ffffff;" + extra,
                                            minimal=True)
            self.assertIn("background-color:#fff;", result)
            self.assertNotIn("background:#fff;", result)

    def test_article_variants_keep_standalone_contract_and_nested_overrides(self):
        for theme in catalog():
            data = templates(theme["id"])
            self.assertIn("font-size:14px;", data["hero_ruler"])
            self.assertNotIn("font-size:14px;", data["hero_ruler_in_article"].split(">", 1)[0])
            self.assertNotIn("font-family:", data["toc_item_ruler"].split(">", 1)[0])
            self.assertNotIn("font-family:", data["toc_item_ruler_in_toc"].split(">", 1)[0])
        standalone = Renderer().blocks(["## 章节"])
        article = Renderer().blocks(["## 章节"], prose_cards=True)
        self.assertIn("font-size:14px;", standalone.split(">", 1)[0])
        self.assertNotIn("font-size:14px;", article.split(">", 1)[0])
        # Nested quotes/headings are NOT direct children of the article container.
        nested = Renderer().blocks(["> ## 嵌套章节"], prose_cards=True)
        self.assertIn("font-size:14px;", nested[nested.find("<section", 1):])

    def test_list_slot_contract_retains_standalone_items(self):
        from stitch_themes import declarations
        for theme in catalog():
            data = templates(theme["id"])
            parent = dict(declarations(re.search(r'style="([^"]*)"',
                                                  data["list_with_items"])[1]))
            for key in ("unordered_item", "ordered_item", "task_item"):
                standalone = data[key].split(">", 1)[0]
                variant = data[key + "_in_list"].split(">", 1)[0]
                self.assertNotIn("font-family:", standalone)
                self.assertNotIn("font-family:", variant)
                self.assertNotIn("font-family", parent)
                self.assertIn("line-height", parent)
        output = Renderer().blocks(["- 项目", "  - 子项", "1. 数字", "- [x] 完成"])
        self.assertEqual(Text(output).text(), "项目子项01数字✓完成")
        # Only the intentionally monospace ordered-list number overrides it.
        self.assertNotIn("font-family:Inter,", output)
        self.assertIn("monospace;", output)

    def test_inherited_compiler_context_respects_native_boundaries(self):
        contract = {"font-family": "Inter,sans-serif", "color": "red",
                    "font-size": "14px"}
        source = ('<section><span style="color:red;font-family:Inter,sans-serif;">'
                  '<span leaf="">文字</span></span><h3 style="color:red;font-size:14px;">'
                  '<span leaf="">标题</span></h3></section>')
        value = clean_template_styles(source, minimal=True, inherited=contract)
        self.assertNotIn("font-family:", value)
        self.assertIn('<h3 style="color:red;font-size:14px;">', value)
        self.assertEqual(Text(source).text(), Text(value).text())

    def test_auto_geometry_cleanup_preserves_layout_resets(self):
        for tag in ("section", "span", "p"):
            for geometry in ("width:100%;", "height:10px;", "padding:2px;",
                             "padding-left:1px;", "border-left:2px solid red;"):
                value = compact_template_style(
                    "box-sizing:border-box;border:0;" + geometry,
                    tag=tag, minimal=True)
                self.assertIn("box-sizing:border-box;", value)
            value = compact_template_style("box-sizing:border-box;border:0;min-width:0;",
                                            tag=tag, minimal=True)
            self.assertNotIn("box-sizing:", value)
            self.assertNotIn("border:", value)
        self.assertEqual(compact_template_style(
            "flex:0 0 auto;flex-shrink:0;", minimal=True), "flex:none;")

    def test_font_allocation_preserves_slots_and_opaque_boundaries(self):
        from build_stitch_themes import allocate_template_fonts
        source = ('<section style="font-family:Inter,sans-serif;">'
                  '<section><span style="font-family:Consolas,monospace;">{{a}}</span>'
                  '<span style="font-family:Consolas,monospace;">{{b}}</span></section>'
                  '<h3 style="font-family:Inter,sans-serif;">标题</h3></section>')
        value = allocate_template_fonts(source)
        self.assertLess(len(value), len(source))
        self.assertEqual(value.count("font-family:Consolas,monospace;"), 1)
        self.assertIn('<h3 style="font-family:Inter,sans-serif;">标题</h3>', value)
        # Direct text, including a runtime slot, pins its exact original font.
        pinned = '<section style="font-family:Inter,sans-serif;">{{body_html}}</section>'
        self.assertEqual(allocate_template_fonts(pinned), pinned)
        unknown = '<section style="font:14px sans-serif;">{{body_html}}</section>'
        self.assertEqual(allocate_template_fonts(unknown), unknown)
        inherited = '<section><span>{{unknown_html}}</span></section>'
        self.assertEqual(allocate_template_fonts(inherited), inherited)
        self.assertEqual(allocate_template_fonts(value), value)

    def test_article_font_is_global_with_only_monospace_component_exceptions(self):
        for theme in catalog():
            data = templates(theme["id"])
            self.assertIn("font-family:-apple-system", data["container"])
            self.assertEqual(data["container"], data["container_in_article"])
            for key, value in data.items():
                if key in {"container", "container_in_article"}:
                    continue
                for font in re.findall(r"font-family:([^;]+);", value):
                    self.assertIn("monospace", font, (theme["id"], key, font))
            self.assertNotIn("font-family:", data["paragraph"])
            self.assertNotIn("font-family:", data["divider_in_article"])
            self.assertIn("monospace;", data["code_row"])
        output = Renderer().render(ARTICLE)
        self.assertEqual(output.count("font-family:-apple-system"), 1)
        from render_stitch_article import inherit_paragraphs
        self.assertNotIn("overflow-wrap:", inherit_paragraphs(
            component("emerald", "paragraph", body_html="正文")))

    def test_typography_allocation_keeps_paint_and_runtime_boundaries(self):
        from build_stitch_themes import allocate_template_fonts
        for prop, first, second in (
            ("color", "red", "blue"),
            ("letter-spacing", "1px", "2px"),
            ("font-style", "normal", "italic"),
        ):
            source = (f'<section style="{prop}:{first};"><section>'
                      f'<span style="{prop}:{second};">{{{{a}}}}</span>'
                      f'<span style="{prop}:{second};">{{{{b_html}}}}</span>'
                      '</section></section>')
            value = allocate_template_fonts(source, prop)
            self.assertLess(len(value), len(source))
            self.assertEqual(value.count(f"{prop}:{second};"), 1)
            self.assertEqual(allocate_template_fonts(value, prop), value)
        painted = ('<section style="color:red;"><section style="border:1px solid;">'
                   '<span style="color:blue;">{{a}}</span>'
                   '<span style="color:blue;">{{b}}</span></section></section>')
        self.assertEqual(allocate_template_fonts(painted, "color"), painted)
        for prop, relative in (("letter-spacing", ".2em"), ("color", "currentColor"),
                               ("font-weight", "bolder")):
            source = f'<section style="{prop}:{relative};"><span>text</span></section>'
            self.assertEqual(allocate_template_fonts(source, prop), source)
        # Relative line-height is dependent on each node's size: not eligible.
        with self.assertRaises(ValueError):
            allocate_template_fonts(painted, "line-height")

    def test_runtime_inline_leaf_fusion_preserves_nested_markup(self):
        from stitch_themes import merge_text_leaf_spans
        renderer = Renderer()
        for text, expected in (("**重点**", "重点"), ("`a < b`", "a < b"),
                               ("*斜体*", "斜体"), ("++关键词++", "关键词"),
                               ("<kbd>Ctrl</kbd>", "Ctrl")):
            value = renderer.inline(text)
            self.assertNotIn('<span leaf=""></span>', value)
            self.assertEqual(value.count("<span"), 1)
            self.assertEqual(Text(value).text(), expected)
            self.assertIn('leaf=""', value)
        nested = renderer.inline("**前面 *斜体* 后面**")
        self.assertEqual(Text(nested).text(), "前面 斜体 后面")
        for display in ("flex", "inline-flex", "grid", "contents"):
            source = f'<span style="display:{display};"><span leaf="">文字</span></span>'
            self.assertEqual(merge_text_leaf_spans(source), source)
        self.assertIn("font-size:11px;vertical-align:super;",
                      renderer.inline("[^note]"))

    def test_plain_article_paragraphs_have_no_card_and_preserve_inline_markup(self):
        for theme in catalog():
            for layout in LAYOUTS:
                renderer = Renderer(theme["id"], layout)
                value = renderer.blocks(
                    ["正文 **强调** 与 `code`，[^note]。", "换行保留。"],
                    prose_cards=True)
                self.assertTrue(value.startswith("<p style="))
                self.assertEqual(value.count("<p "), 1)
                self.assertNotIn("<section", value)
                self.assertIn("<br>", value)
                opening = value.split(">", 1)[0]
                for prop in ("background:", "border:", "box-shadow:", "padding:", "border-radius:"):
                    self.assertNotIn(prop, opening)
                self.assertIn("margin:0 0 16px;", opening)
                self.assertNotIn("font-size:", opening)
                self.assertIn("code", value)
                self.assertIn("font-weight:700;", value)
                self.assertNotIn("display:flex;", value)
                self.assertEqual(validate(value)[0], [])
                # Adjacent paragraphs stay independent with no grouping box.
                multiple = renderer.blocks(["第一段。", "", "第二段。"],
                                           prose_cards=True)
                self.assertNotIn("<section", multiple)
                self.assertNotIn("gap:", multiple)
                self.assertEqual(multiple.count("<p "), 2)
                self.assertEqual(multiple.count("margin:0 0 16px;"), 2)
                self.assertNotIn("box-shadow:", multiple)
                self.assertNotIn("background:", multiple)
                self.assertNotIn("border:", multiple)
                plain = renderer.blocks(["独立正文。"])
                self.assertIn("margin:0 0 16px;", plain)
                self.assertNotIn("box-shadow:", plain)

    def test_scroll_table_spacing_uses_one_frame(self):
        from build_stitch_themes import merge_table_spacing
        source = ('<section style="margin:0 0 24px;">'
                  '<section style="box-sizing:border-box;width:100%;overflow-x:auto;margin:0;">'
                  '<table>{{rows_html}}</table></section></section>')
        value = merge_table_spacing(source)
        self.assertEqual(value.count("<section"), 1)
        self.assertIn("margin:0 0 24px;", value)
        self.assertEqual(merge_table_spacing(source.replace("100%", "80%")),
                         source.replace("100%", "80%"))

    def test_layout_context_removes_only_blockified_display(self):
        source = ('<section style="display:flex;"><span style="display:block;">'
                  '<span style="display:block;">text</span></span></section>')
        value = clean_template_styles(source, minimal=True)
        self.assertIn('<span><span style="display:block;">', value)
        self.assertIn('display:inline-flex;', clean_template_styles(
            source.replace('display:block;', 'display:inline-flex;', 1), minimal=True))

    def test_dimensioned_boxes_keep_sizing_when_padding_or_border_present(self):
        for geometry in ("padding:1px;", "padding-left:1px;", "border-left:1px solid red;"):
            source = '<span style="box-sizing:border-box;width:24px;border:0;' + geometry + '">x</span>'
            self.assertIn("box-sizing:border-box;", clean_template_styles(source, minimal=True))
        source = '<span style="box-sizing:border-box;min-width:24px;border:0;">x</span>'
        value = clean_template_styles(source, minimal=True)
        self.assertNotIn("box-sizing:", value)
        self.assertNotIn("border:", value)

    def test_default_removal_preserves_native_resets_and_shorthand_boundaries(self):
        plain = ("margin:0;border:0;position:static;float:none;clear:none;"
                 "order:0;flex-wrap:nowrap;flex-grow:0;flex-shrink:1;overflow:visible;")
        self.assertEqual(compact_template_style(plain, tag="section", minimal=True), ";")
        for tag in ("h2", "p", "blockquote"):
            self.assertIn("margin:0;", compact_template_style(
                "margin:0;", tag=tag, minimal=True))
        for tag in ("img", "table", "button"):
            self.assertIn("border:0;", compact_template_style(
                "border:0;", tag=tag, minimal=True))
        for style, declaration in (
            ("border:0;border-left:2px solid red;", "border:0;"),
            ("border:0;border-image:url(a.png) 1;", "border:0;"),
            ("margin:8px;margin-left:0;", "margin-left:0;"),
            ("margin-left:8px;margin:0;", "margin:0;"),
            ("margin-inline:8px;margin-left:0;", "margin-left:0;"),
            ("flex:1;flex-grow:0;", "flex-grow:0;"),
            ("flex-flow:column wrap;flex-wrap:nowrap;", "flex-wrap:nowrap;"),
            ("overflow:visible;overflow-x:hidden;", "overflow:visible;"),
        ):
            self.assertIn(declaration, compact_template_style(
                style, tag="section", minimal=True))

    def test_assembled_code_and_list_have_explicit_parent_contracts(self):
        for theme in catalog():
            data = templates(theme["id"])
            self.assertIn("line-height:1.6;", data["code_with_rows"])
            self.assertNotIn("line-height:", data["code_row_in_rows"])
            self.assertIn("line-height:1.6;", data["code_row_in_frame"])
            self.assertIn("color:", data["unordered_item_in_list"])
            self.assertIn("color:", data["task_item_in_list"])
        # Quote paragraph normalization strips row line-height. Its original
        # fixed 22px code-body line-height must NOT be changed by the new variant.
        quoted = Renderer().blocks(["> ```txt", "> quoted", "> ```"], prose_cards=True)
        self.assertIn("line-height:22px;", quoted)
        direct = Renderer().blocks(["```txt", "direct", "```"], prose_cards=True)
        self.assertNotIn("line-height:22px;", direct)


if __name__ == "__main__":
    unittest.main()
