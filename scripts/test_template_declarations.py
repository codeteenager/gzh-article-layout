"""Conservative final-pass CSS folding and boundary regressions."""
import unittest
import re

from build_stitch_themes import minimize_template_declarations
from stitch_themes import catalog, templates, LAYOUTS
from render_stitch_article import Renderer


def fragment(style):
    return '<p style="' + style + '">{{body_html}}</p>'


class DeclarationTests(unittest.TestCase):
    def test_identical_background_before_shorthand_is_redundant(self):
        self.assertEqual(minimize_template_declarations(fragment(
            "background-color:#fff;color:red;background:#fff;")),
            fragment("color:red;background:#fff;"))
        for style in (
            "background-color:#f00;background:#fff;",
            "background:#fff;background-color:#fff;",
            "background-color:inherit;background:inherit;",
            "background-color:#fff;background:#fff!important;",
            "background-color:#fff;background:url(image.png);",
        ):
            self.assertEqual(minimize_template_declarations(fragment(style)),
                             fragment(style))

    def test_table_assembly_contract_preserves_standalone(self):
        for theme in catalog():
            data = templates(theme["id"])
            self.assertIn("font-size:13px;", data["table_cell"])
            self.assertIn("line-height:1.7;", data["table_cell"])
            self.assertNotIn("font-size:", data["table_cell_in_table"])
            self.assertNotIn("line-height:", data["table_cell_in_table"])
            self.assertNotIn("overflow-wrap:", data["table_cell_in_table"])
            self.assertIn("font-size:16px;", data["table"])
            self.assertIn("font-size:13px;line-height:1.7;overflow-wrap:anywhere;",
                          data["table_with_cells"])
            for layout in LAYOUTS:
                source = "# 标题\n\n| 左 | 中 | 右 |\n| :--- | :---: | ---: |\n| 内容 | **强调** | `code` |"
                output = Renderer(theme["id"], layout).render(source)
                self.assertEqual(output.count("<th "), 3)
                self.assertEqual(output.count("<td "), 3)
                for align in ("left", "center", "right"):
                    self.assertEqual(len(re.findall(
                        r'<t[hd] style="[^"]*text-align:' + align + r';', output)),
                        1 if align == "left" else 2)
                self.assertEqual(output.count("font-size:13px;line-height:1.7;overflow-wrap:anywhere;"), 1)

    def test_code_header_shares_font_without_crossing_body(self):
        for theme in catalog():
            data = templates(theme["id"])
            for key in ("code", "code_with_rows", "code_in_article",
                        "code_with_rows_in_article"):
                value = data[key]
                header = value[value.find("<section", value.find(">") + 1):
                               value.index("{{language}}</span></section>") +
                               len("{{language}}</span></section>")]
                self.assertEqual(header.count("font-family:"), 1)
                self.assertIn('style="font-family:', header)
                self.assertIn("font-family:", value[value.index(
                    "{{language}}</span></section>") + len("{{language}}</span></section>"):])
            self.assertIn("font-family:", data["code_row"])

    def test_table_border_and_native_header_alignment(self):
        for theme in catalog():
            data = templates(theme["id"])
            self.assertIn("border:0 solid rgba(", data["table"])
            self.assertNotIn("border:0 solid rgba(", data["table_with_cells"])
            self.assertIn("border:0;", data["table_with_cells"])
            for source in ("| 左 | 右 |\n| --- | --- |\n| 甲 | 乙 |",
                           "| 左 | 右 |\n| :--- | ---: |\n| 甲 | 乙 |"):
                value = Renderer(theme["id"]).blocks(source.splitlines())
                self.assertRegex(value, r'<th style="[^"]*text-align:left;')
                self.assertNotRegex(value, r'<td style="[^"]*text-align:left;')

    def test_article_weight_contract_not_standalone_removal(self):
        for theme in catalog():
            data = templates(theme["id"])
            self.assertIn("font-weight:400;", data["container"])
            self.assertIn("font-weight:400;", data["paragraph"])
            self.assertNotIn("font-weight:", data["paragraph_in_article"])
            self.assertIn("font-weight:800;", data["chapter_ruler"])

    def test_spacing_follows_last_declaration(self):
        self.assertEqual(minimize_template_declarations(fragment(
            "margin:0;margin-top:4px;display:flow-root;margin-bottom:0;")),
            fragment("display:flow-root;margin:4px 0 0;"))
        self.assertEqual(minimize_template_declarations(fragment(
            "margin-top:4px;margin:0;")), fragment("margin:0;"))
        self.assertEqual(minimize_template_declarations(fragment(
            "padding:8px 12px;padding-left:4px;")),
            fragment("padding:8px 12px 8px 4px;"))

    def test_unspecified_sides_and_logical_interactions_are_preserved(self):
        for style in (
            "margin-top:0;margin-bottom:0;",
            "margin:0;margin-inline:12px;margin-left:4px;",
            "padding:0;padding-block-start:8px;",
            "margin:0;margin-top:inherit;",
            "margin:0;margin-top:calc(1px + 2px);",
            "margin:0;margin-top:var(--space);",
            "margin:0;margin-top:4px!important;",
            "all:initial;margin:0;margin-top:4px;",
            "--space:4px;margin:0;margin-top:4px;",
            "direction:rtl;margin:0;margin-top:4px;",
            "padding:8px;padding-top:-1px;",
        ):
            with self.subTest(style=style):
                self.assertEqual(minimize_template_declarations(fragment(style)),
                                 fragment(style))

    def test_flex_shorthand_order(self):
        for style in ("flex-shrink:0;flex:0 0 230px;",
                      "flex:0 0 230px;flex-shrink:0;"):
            self.assertEqual(minimize_template_declarations(fragment(style)),
                             fragment("flex:0 0 230px;"))
        for style in ("flex:0 1 auto;flex-shrink:0;",
                      "flex:var(--flex);flex-shrink:0;",
                      "flex:1;flex-shrink:0;",
                      "flex:none;flex:auto;flex-shrink:1;"):
            self.assertEqual(minimize_template_declarations(fragment(style)),
                             fragment(style))

    def test_content_svg_and_other_properties_unchanged(self):
        source = ('<svg style="margin:0;margin-top:4px;">'
                  '<path style="margin:0;margin-top:4px;" /></svg>'
                  '<p style="background:url(&quot;a;b.png&quot;);color:red;">'
                  '<span leaf="">代码 &lt;tag&gt; {{title}}\n  content</span></p>')
        self.assertEqual(minimize_template_declarations(source), source)

    def test_idempotent_and_never_longer(self):
        source = fragment("margin:0;margin-top:4px;flex-shrink:0;flex:0 0 230px;")
        result = minimize_template_declarations(source)
        self.assertLess(len(result.encode()), len(source.encode()))
        self.assertEqual(minimize_template_declarations(result), result)


if __name__ == "__main__":
    unittest.main()
