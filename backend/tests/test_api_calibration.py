import sys
import uuid
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import main
from adapters import agent_adapter, agent_runtime, guardrail
from database import SessionLocal
from models.job import Job
from models.user import User
from routers import auth


class FakeRetriever:
    def search(self, query: str, job: str, top_k: int = 5):
        return [{
            "source_chunk_id": "backend.redis.test",
            "title": "后端能力标准测试片段",
            "content": (
                "问题：Redis 缓存如何形成可验证的后端能力证据？\n"
                "回答：Redis 可用于缓存高频访问数据，降低数据库压力。"
                "实践中应记录缓存键设计、过期时间、命中率、异常分支和回源策略，"
                "并通过接口测试、运行日志与优化前后指标证明实现有效。"
            ),
            "score": 0.92,
        }]


class ApiCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.user_id = str(uuid.uuid4())
        db = SessionLocal()
        cls.user = User(id=cls.user_id, username=f"calibration_{cls.user_id[:8]}", password_hash="test")
        db.add(cls.user)
        db.commit()
        db.refresh(cls.user)
        db.expunge(cls.user)
        db.close()
        main.app.dependency_overrides[auth.get_current_user] = lambda: cls.user
        cls._original_llm_available = agent_runtime._LLM_AVAILABLE
        cls._original_retriever = agent_adapter._runtime.retriever
        cls._original_runtime_guard = agent_runtime.check_hallucination
        cls._original_guard = guardrail.check_hallucination
        agent_runtime._LLM_AVAILABLE = False
        agent_adapter._runtime.retriever = FakeRetriever()
        agent_runtime.check_hallucination = lambda *_args, **_kwargs: {"has_hallucination": False, "verdict": "grounded", "reason": "test"}
        guardrail.check_hallucination = lambda *_args, **_kwargs: {"has_hallucination": False, "verdict": "grounded", "reason": "test"}

    @classmethod
    def tearDownClass(cls):
        agent_runtime._LLM_AVAILABLE = cls._original_llm_available
        agent_adapter._runtime.retriever = cls._original_retriever
        agent_runtime.check_hallucination = cls._original_runtime_guard
        guardrail.check_hallucination = cls._original_guard
        main.app.dependency_overrides.clear()
        db = SessionLocal()
        db.query(User).filter(User.id == cls.user_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    def test_submit_and_calibration_metrics_are_persisted(self):
        db = SessionLocal()
        job = db.query(Job).filter(Job.job_title == "后端开发工程师").first()
        db.close()
        self.assertIsNotNone(job)

        # Formal diagnosis requires a completed two-turn material-review
        # session, not a single browser text field.
        session = self.client.post("/api/session/create", json={"job_id": job.id})
        self.assertEqual(session.status_code, 201, session.text)
        session_id = session.json()["id"]
        first_turn = self.client.post(
            f"/api/session/{session_id}/review-turn",
            json={"content": "我会使用 Redis 开发缓存接口，也做过缓存读写实践。"},
        )
        self.assertEqual(first_turn.status_code, 200, first_turn.text)
        second_turn = self.client.post(
            f"/api/session/{session_id}/review-turn",
            json={"content": "我对缓存穿透排查还不熟，希望补强这一部分。"},
        )
        self.assertEqual(second_turn.status_code, 200, second_turn.text)
        self.assertTrue(second_turn.json()["ready_for_diagnosis"])

        created = self.client.post("/api/assessment/create", json={"job_id": job.id})
        self.assertEqual(created.status_code, 201)
        assessment_id = created.json()["id"]
        response = self.client.post(
            f"/api/assessment/{assessment_id}/submit",
            json={
                "user_input": "我会使用 Redis 开发并完成缓存项目，能够实现缓存读写和问题排查。",
                "session_id": session_id,
                "gold_labels": [{
                    "requirement_id": "backend.redis",
                    "gold_score": 0.65,
                    "source_type": "unit_test",
                    "trusted": True,
                }],
                "apply_corrections": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        # Submit is intentionally asynchronous.  The immediate response only
        # confirms that the task was queued; persisted diagnosis fields are
        # asserted through the read endpoint after TestClient completes the
        # background task.
        persisted = self.client.get(f"/api/assessment/{assessment_id}")
        self.assertEqual(persisted.status_code, 200, persisted.text)
        body = persisted.json()
        self.assertIn("我会使用 Redis 开发缓存接口", body["user_input"])
        self.assertIn("我对缓存穿透排查还不熟", body["user_input"])
        self.assertNotIn("我会使用 Redis 开发并完成缓存项目", body["user_input"])
        self.assertEqual(body["calibration_status"], "passed")
        self.assertEqual(body["calibration_summary"]["accuracy"], 1.0)

        progress = self.client.get(f"/api/assessment/{assessment_id}/progress")
        self.assertEqual(progress.status_code, 200)
        progress_body = progress.json()
        self.assertEqual(progress_body["percent"], 100)
        self.assertEqual(progress_body["status"], "completed")
        self.assertEqual(progress_body["stage"], "complete")
        stages = {event["stage"] for event in progress_body["events"]}
        self.assertTrue({"material", "diagnosis", "path", "resource", "review", "complete"}.issubset(stages))

        # A diagnosis becomes globally active only after the complete stage,
        # so both the diagnosis page and resource library switch together.
        current_user = self.client.get("/api/auth/me")
        self.assertEqual(current_user.status_code, 200, current_user.text)
        self.assertEqual(current_user.json()["active_assessment_id"], assessment_id)

        calibration = self.client.get(f"/api/assessment/{assessment_id}/calibration")
        self.assertEqual(calibration.status_code, 200)
        self.assertEqual(calibration.json()["summary"]["evaluated_count"], 1)
        self.assertEqual(calibration.json()["records"][0]["requirement_id"], "backend.redis")

        # The learner-facing calibration command must be one click: it derives
        # reproducible evidence-review labels and never opens a manual form.
        automatic = self.client.post(f"/api/assessment/{assessment_id}/auto-calibrate")
        self.assertEqual(automatic.status_code, 200, automatic.text)
        automatic_body = automatic.json()
        self.assertEqual(automatic_body["calibration"]["mode"], "automatic_evidence_review")
        self.assertEqual(automatic_body["calibration"]["metric_label"], "自动证据校准得分")
        self.assertGreater(automatic_body["calibration"]["evaluated_count"], 0)
        self.assertIsNotNone(automatic_body["calibration"]["accuracy"])
        self.assertIn("diagnosis_confidence", automatic_body["calibration"]["calculation"])
        self.assertIn("binary_item_accuracy", automatic_body["calibration"])
        expected = round(
            0.45 * automatic_body["calibration"]["continuous_agreement"]
            + 0.40 * automatic_body["calibration"]["diagnosis_confidence_component"]
            + 0.15 * automatic_body["calibration"]["explicit_evidence_coverage"],
            4,
        )
        self.assertAlmostEqual(automatic_body["calibration"]["accuracy"], expected, places=4)
        self.assertGreaterEqual(
            automatic_body["calibration"]["accuracy"],
            0.90,
            "完整、可验证的双轮信息应达到自动证据校准通过线",
        )
        self.assertFalse(automatic_body["diagnosis_updated"])
        score_before_repair = body["overall_mastery"]

        # A historical diagnosis with an empty/blocked package can be repaired
        # in place. TestClient waits for the background task, so the returned
        # resource list must already contain source-bound learning content.
        repair = self.client.post(f"/api/assessment/{assessment_id}/repair-learning-package")
        self.assertEqual(repair.status_code, 200, repair.text)
        resources = self.client.get("/api/resource/list", params={"assessment_id": assessment_id})
        self.assertEqual(resources.status_code, 200, resources.text)
        resource_items = resources.json()
        self.assertGreater(len(resource_items), 0)
        self.assertTrue(all(item["source_chunk_id"] for item in resource_items))
        self.assertTrue(all(len(item["body"].strip()) > 120 for item in resource_items))

        paths = self.client.get(f"/api/path/{self.user_id}", params={"assessment_id": assessment_id})
        self.assertEqual(paths.status_code, 200, paths.text)
        self.assertGreater(len(paths.json()), 0)
        labels = [step["knowledge_point"] for step in paths.json()[0]["steps"]]
        self.assertFalse(any("构建失败" in label or "###" in label for label in labels))
        repaired_diagnosis = self.client.get(f"/api/assessment/{assessment_id}")
        self.assertEqual(repaired_diagnosis.status_code, 200, repaired_diagnosis.text)
        self.assertEqual(repaired_diagnosis.json()["overall_mastery"], score_before_repair)
        self.assertEqual(
            repaired_diagnosis.json()["calibration_summary"]["mode"],
            "automatic_evidence_review",
        )


if __name__ == "__main__":
    unittest.main()
