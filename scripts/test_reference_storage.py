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
    def test_workflow_rules_do_not_conflict(self):
        """Check documentation consistency, not AI semantic execution."""
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cases = (ROOT / "references/eval-cases.md").read_text(encoding="utf-8")
        self.assertIn("### 2. 读组件库（两份）", skill)
        self.assertIn("仅用户明确要求精选时才另选最多 3 个", skill)
        self.assertIn("名片可选、互动卡片唯一", skill)
        self.assertIn("将引导原样移入唯一互动卡片", skill)
        self.assertNotIn("默认用 `{{作者名}}` 占位", cases)
        for theme in catalog():
            text = reference(theme, templates(theme["id"]))
            self.assertIn("配方只决定组件组合，不覆盖已确定主题与版式", text)
            self.assertIn("可选同版式 `signature`", text)
            self.assertIn("默认前 3 个 H2，不足则全部", text)
            self.assertNotRegex(text, r"(?:墨规|浮光|素墨)章节 \+")

    def test_agent_theme_selection_policy_is_synchronized(self):
        """Guard routing docs; these assertions do not simulate AI judgment."""
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        index = (ROOT / "references/theme-index.md").read_text(encoding="utf-8")
        cases = (ROOT / "references/eval-cases.md").read_text(encoding="utf-8")
        generator = (ROOT / "scripts/build_stitch_themes.py").read_text(encoding="utf-8")
        self.assertIn("选主题与版式（自动推荐制）", skill)
        self.assertIn("等待用户答复后再读取所选主题组件库", skill)
        self.assertIn("只指定版式时也推荐色系，但保留指定版式", skill)
        self.assertIn("无明显倾向时使用索引第一行", skill)
        for text in (skill, index, cases, generator):
            self.assertNotIn("固定默认参数", text)
            self.assertNotIn("不按题材自动换主题", text)
        self.assertIn("等待用户确认后再读取所选主题组件库并生成", index)
        self.assertIn("离线 CLI 仍默认 emerald + ruler", index)
        self.assertIn("确认前不读取候选主题组件库、不生成 HTML", cases)

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
