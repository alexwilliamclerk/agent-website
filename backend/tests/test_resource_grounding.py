import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import agent_runtime, guardrail
from adapters.agent_runtime import ResourceAgent, sanitize_learning_path_steps


class _Retriever:
    def search(self, query, target_job, top_k=5):
        return [{
            "source_chunk_id": "frontend.vue.lifecycle.001",
            "title": "Vue 生命周期与接口联调",
            "content": (
                "Vue 组件在挂载阶段完成响应式状态与事件初始化。"
                "接口联调时应记录请求参数、响应状态、异常分支和可复现结果。"
                "性能优化需要结合网络请求、渲染次数和构建产物进行验证。"
            ),
            "score": 0.82,
            "candidate_requirement_ids": ["frontend.vue"],
        }]


class ResourceGroundingTests(unittest.TestCase):
    def test_rule_resource_contains_source_content_and_personal_reason(self):
        with patch.object(agent_runtime, "_LLM_AVAILABLE", False):
            resource, hits = ResourceAgent(_Retriever()).run(
                "Vue 接口联调",
                0.34,
                "讲义",
                "前端开发工程师",
                learner_context={
                    "focus_dimension": "前端技术",
                    "focus_gap": "缺少可复现的接口联调证据",
                    "evidence_summary": "用户只描述了页面开发，没有提交异常处理与验证记录",
                },
            )
        self.assertEqual(len(hits), 1)
        self.assertIn("为什么为你推荐", resource["body"])
        self.assertIn("缺少可复现的接口联调证据", resource["body"])
        self.assertIn("响应状态", resource["body"])
        self.assertNotIn("待审核模板", resource["body"])

    def test_partial_review_is_visible_not_hallucinated(self):
        with patch.object(guardrail, "chat_json", return_value={"verdict": "partial", "reason": "主要结论有来源"}):
            result = guardrail.check_hallucination("Vue 接口联调需要记录响应状态与异常分支。", "讲义说明响应状态和异常分支。")
        self.assertEqual(result["verdict"], "partial")
        self.assertFalse(result["has_hallucination"])

    def test_path_sanitizer_replaces_failed_markdown_heading(self):
        steps = sanitize_learning_path_steps(
            [{
                "step": 1,
                "knowledge_point": "### 1. 构建失败",
                "resource_type": "- 练习",
                "estimated_time": 20,
            }],
            "前端开发工程师",
        )
        self.assertEqual(len(steps), 1)
        self.assertNotIn("构建失败", steps[0]["knowledge_point"])
        self.assertNotIn("#", steps[0]["knowledge_point"])
        self.assertEqual(steps[0]["resource_type"], "练习")


if __name__ == "__main__":
    unittest.main()
