"""Storage deduplication must never change resolved component HTML."""
import re
import unittest

from stitch_themes import (ROOT, catalog, templates, compact_templates,
                           expand_templates)


class TemplateStorageTests(unittest.TestCase):
    def test_exact_strings_only_and_roundtrip(self):
        values = {"base": "<p>内容 {{body_html}}</p>",
                  "alias": "<p>内容 {{body_html}}</p>",
                  "different": "<p>内容 {{body_html}} </p>"}
        packed = compact_templates(values)
        self.assertEqual(packed["alias"], {"$ref": "base"})
        self.assertIsInstance(packed["different"], str)
        self.assertEqual(expand_templates(packed), values)
        self.assertEqual(expand_templates(values), values)
        self.assertEqual(compact_templates(expand_templates(packed)), packed)

    def test_invalid_aliases_fail(self):
        for values in (
                [], {"a": 1}, {"a": {"$ref": "missing"}},
                {"a": {"$ref": "a"}},
                {"a": {"$ref": "b"}, "b": {"$ref": "a"}},
                {"a": "html", "b": {"$ref": "a"}, "c": {"$ref": "b"}},
                {"a": "html", "b": {"$ref": "a", "extra": 1}},
                {"a": {"$ref": []}}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                expand_templates(values)

    def test_markdown_sources_have_no_duplicate_literals(self):
        for theme in catalog():
            with self.subTest(theme=theme["id"]):
                # Packing is only an in-memory test helper, never a second source.
                stored = compact_templates(templates(theme["id"]))
                text = (ROOT / "references" / ("theme-" + theme["id"] + ".md")).read_text(encoding="utf-8")
                literals = re.findall(r"```html\n(.*?)\n```", text, re.S)
                self.assertEqual(len(literals), len(set(literals)))
                self.assertEqual(expand_templates(stored), templates(theme["id"]))
                self.assertEqual(compact_templates(templates(theme["id"])), stored)


if __name__ == "__main__":
    unittest.main()
