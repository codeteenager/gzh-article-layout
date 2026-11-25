"""Markdown authority, fail-closed loading and legacy overwrite protection."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import stitch_themes as themes


class MarkdownSourceTests(unittest.TestCase):
    def tearDown(self):
        themes.catalog.cache_clear()
        themes.templates.cache_clear()

    def test_editing_markdown_changes_loaded_component_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            refs = root / "references"
            refs.mkdir()
            index = (themes.ROOT / "references/theme-index.md").read_text(encoding="utf-8")
            row = next(line for line in index.splitlines() if "`references/theme-emerald.md`" in line)
            (refs / "theme-index.md").write_text(row + "\n", encoding="utf-8")
            original = (themes.ROOT / "references/theme-emerald.md").read_text(encoding="utf-8")
            path = refs / "theme-emerald.md"
            path.write_text(original, encoding="utf-8")
            with patch.object(themes, "ROOT", root):
                themes.catalog.cache_clear()
                themes.templates.cache_clear()
                self.assertEqual(themes.catalog()[0]["id"], "emerald")
                before = themes.templates("emerald")["paragraph"]
                path.write_text(original.replace("{{body_html}}", "编辑生效{{body_html}}"), encoding="utf-8")
                themes.templates.cache_clear()
                self.assertEqual(themes.templates("emerald")["paragraph"],
                                 before.replace("{{body_html}}", "编辑生效{{body_html}}"))
                self.assertFalse((root / "assets").exists())

    def test_invalid_component_definitions_fail_closed(self):
        header = "## 各组件完整 HTML\n\n"
        for body in (
            "",
            "### 无效标题\n\n```html\n<p></p>\n```\n",
            "### a · `a`\n\n```html\n<p></p>\n",
            "### a · `a`\n\nHTML 同组件：`missing`。\n",
            "### a · `a`\n\nHTML 同组件：`a`。\n",
            "### a · `a`\n\n```html\n<p></p>\n```\n"
            "### b · `b`\n\nHTML 同组件：`a`。\n"
            "### c · `c`\n\nHTML 同组件：`b`。\n",
            "### a · `a`\n\n```html\n<p></p>\n```\n"
            "### a · `a`\n\nHTML 同组件：`a`。\n",
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                themes.read_components(header + body)

    def test_forward_reference_and_exact_html_are_preserved(self):
        text = ("## 各组件完整 HTML\n\n### alias · `alias`\n\n"
                "HTML 同组件：`base`。\n\n### base · `base`\n\n"
                "```html\n<p>  {{body_html}} </p>\n```\n\n"
                "## 完整文章模板骨架\n说明。\n")
        self.assertEqual(themes.read_components(text),
                         {"alias": "<p>  {{body_html}} </p>",
                          "base": "<p>  {{body_html}} </p>"})

    def test_duplicate_index_and_missing_source_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            refs = root / "references"
            refs.mkdir()
            source = (themes.ROOT / "references/theme-emerald.md").read_text(encoding="utf-8")
            row = next(line for line in (themes.ROOT / "references/theme-index.md").read_text(encoding="utf-8").splitlines()
                       if "`references/theme-emerald.md`" in line)
            index = refs / "theme-index.md"
            index.write_text(row + "\n", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                themes.read_catalog(root)
            (refs / "theme-emerald.md").write_text(source, encoding="utf-8")
            index.write_text(row + "\n" + row + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "重复主题"):
                themes.read_catalog(root)
            index.write_text(row.replace("#059669", "#000000") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "主色不一致"):
                themes.read_catalog(root)

    def test_legacy_build_cannot_overwrite_markdown(self):
        paths = [themes.ROOT / "references/theme-index.md"]
        paths += list((themes.ROOT / "references").glob("theme-*.md"))
        before = {path: path.read_bytes() for path in paths}
        result = subprocess.run([sys.executable, str(themes.ROOT / "scripts/build_stitch_themes.py")],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Markdown 唯一源码", result.stderr)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        self.assertFalse((themes.ROOT / "assets/stitch/themes.json").exists())
        self.assertFalse((themes.ROOT / "assets/stitch/templates").exists())


if __name__ == "__main__":
    unittest.main()
