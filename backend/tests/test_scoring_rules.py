import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.agent_runtime import CapabilityScoringAgent, InputParsingAgent


class ScoringRuleTests(unittest.TestCase):
    def test_unmapped_dimensions_use_neutral_prior(self):
        profile = InputParsingAgent()._run_rules(
            "前端开发工程师",
            "我负责开发 Vue 商品列表并完成接口联调，也使用 Git 提交代码。",
        )
        result = CapabilityScoringAgent()._run_rules("前端开发工程师", profile, [])
        values = {item["name"]: item["value"] for item in result["ability_vector"]}

        self.assertEqual(len(values), 16)
        self.assertGreaterEqual(values["操作系统"], 0.52)
        self.assertGreaterEqual(values["产品分析"], 0.52)
        self.assertGreater(result["overall_mastery"], 0.50)

    def test_action_evidence_scores_above_plain_mention(self):
        parser = InputParsingAgent()
        plain = parser._run_rules("前端开发工程师", "我了解 Vue。")
        action = parser._run_rules("前端开发工程师", "我使用 Vue 开发并完成商品列表组件。")

        self.assertEqual(plain.matched_skills["Vue"], 0.58)
        self.assertEqual(action.matched_skills["Vue"], 0.78)


if __name__ == "__main__":
    unittest.main()
