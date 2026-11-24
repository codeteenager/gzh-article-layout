"""Documentation aliases preserve every component and its exact HTML."""
import re
import unittest

from build_stitch_themes import reference
from component_lint import lint_file
from stitch_themes import ROOT, catalog, templates


def read_components(text):
    """Read headings and direct aliases independently of the generator."""
    literals, aliases, keys = {}, {}, []
    for section in re.split(r"(?=^### )", text, flags=re.M)[1:]:
        heading, body = section.split("\n", 1)
        key = re.search(r" · `([^`]+)`$", heading).group(1)
        if key in keys:
            raise ValueError("Duplicate heading: " + key)
        keys.append(key)
        block = re.search(r"```html\n(.*?)\n```", body, re.S)
        alias = re.search(r"^HTML 同组件：`([^`]+)`。", body, re.M)
        if bool(block) == bool(alias):
            raise ValueError("Expected exactly one definition: " + key)
        if block:
            literals[key] = block.group(1)
        else:
            aliases[key] = alias.group(1)
    for key, target in aliases.items():
        if target not in literals:
            raise ValueError("Missing or indirect target: " + key)
    resolved = dict(literals)
    resolved.update({key: literals[target] for key, target in aliases.items()})
    return keys, literals, aliases, resolved


class ReferenceStorageTests(unittest.TestCase):
    def test_all_theme_documents_preserve_exact_templates(self):
        for theme in catalog():
            with self.subTest(theme=theme["id"]):
                values = templates(theme["id"])
                path = ROOT / "references" / ("theme-" + theme["id"] + ".md")
                text = path.read_text(encoding="utf-8")
                self.assertEqual(reference(theme, values), text)
                keys, literals, aliases, resolved = read_components(text)
                self.assertEqual(keys, list(values))
                self.assertEqual(resolved, values)
                self.assertTrue(aliases)
                self.assertEqual(len(literals), len(set(values.values())))
                # Every alias resolves to a fenced literal scanned by the linter.
                self.assertEqual(lint_file(path)[1], [])
                self.assertNotIn("{{作者名}}", text)
                self.assertIn("默认不传作者、不生成名片", text)

    def test_only_exact_matches_and_direct_local_references(self):
        values = {"base": "<p>{{body_html}}</p>",
                  "alias": "<p>{{body_html}}</p>",
                  "another_alias": "<p>{{body_html}}</p>",
                  "different": "<p>{{body_html}} </p>"}
        _, literals, aliases, resolved = read_components(reference(catalog()[0], values))
        self.assertEqual(set(literals), {"base", "different"})
        self.assertEqual(aliases, {"alias": "base", "another_alias": "base"})
        self.assertEqual(resolved, values)

    def test_broken_or_chained_document_references_rejected(self):
        for body in (
            "### a · `a`\n\nHTML 同组件：`missing`。\n",
            "### a · `a`\n\nHTML 同组件：`a`。\n",
            "### a · `a`\n\n```html\n<p></p>\n```\n"
            "### b · `b`\n\nHTML 同组件：`a`。\n"
            "### c · `c`\n\nHTML 同组件：`b`。\n",
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                read_components(body)


if __name__ == "__main__":
    unittest.main()
