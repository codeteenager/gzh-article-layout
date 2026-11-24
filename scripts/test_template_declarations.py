"""Conservative final-pass CSS folding and boundary regressions."""
import unittest

from build_stitch_themes import minimize_template_declarations


def fragment(style):
    return '<p style="' + style + '">{{body_html}}</p>'


class DeclarationTests(unittest.TestCase):
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
