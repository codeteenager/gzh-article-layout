"""Bounded inert-style cleanup must preserve layout and dynamic slot contracts."""
import unittest

from build_stitch_themes import remove_inert_template_styles as clean


class InertStyleTests(unittest.TestCase):
    def test_normal_block_gap_only(self):
        self.assertEqual(
            clean('<section style="gap:16px;row-gap:4px;column-gap:8px;padding:16px;">{{rows_html}}</section>'),
            '<section style="padding:16px;">{{rows_html}}</section>')
        for style in ("display:flex;gap:8px;", "display:grid;gap:8px;",
                      "display:inline-flex;gap:8px;", "columns:2;gap:8px;",
                      "column-count:2;gap:8px;", "column-width:100px;gap:8px;",
                      "all:initial;gap:8px;", "gap:8px!important;",
                      "display:inherit;gap:8px;"):
            value = '<section style="' + style + '">{{body_html}}</section>'
            self.assertEqual(clean(value), value)

    def test_bare_image_only(self):
        value = '<img src="{{url}}" style="box-sizing:border-box;max-width:100%;height:auto;margin:0 auto;">'
        self.assertEqual(clean(value), value.replace("box-sizing:border-box;", ""))
        for extra in ("padding:1px;", "border:1px solid red;", "all:unset;",
                      "aspect-ratio:1;", "width:100px;"):
            modified = value.replace("box-sizing:", extra + "box-sizing:")
            self.assertEqual(clean(modified), modified)
        native = '<input style="box-sizing:border-box;max-width:100%;height:auto;">'
        self.assertEqual(clean(native), native)

    def test_caption_requires_exact_single_plain_text_slot(self):
        value = '<figcaption style="display:flex;gap:6px;padding:4px 0;"><span leaf="">{{caption}}</span></figcaption>'
        self.assertEqual(clean(value), value.replace("gap:6px;", ""))
        for modified in (
                value.replace("{{caption}}", "{{body_html}}"),
                value.replace("</figcaption>", '<span leaf="">extra</span></figcaption>'),
                value.replace("display:flex;", "display:flex;flex-wrap:wrap;")):
            self.assertEqual(clean(modified), modified)

    def test_svg_and_other_styles_untouched_and_idempotent(self):
        svg = '<svg><section style="gap:8px;"></section></svg>'
        self.assertEqual(clean(svg), svg)
        value = '<section style="gap:8px;box-shadow:0 1px 2px #000;padding:16px;"><p style="margin:0;">{{body_html}}</p></section>'
        result = clean(value)
        self.assertEqual(result, value.replace("gap:8px;", ""))
        self.assertEqual(clean(result), result)


if __name__ == "__main__":
    unittest.main()
