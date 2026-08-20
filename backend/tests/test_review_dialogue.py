import sys
import uuid
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import main
from database import SessionLocal
from models.job import Job
from models.session import Session, SessionMessage
from models.user import User
from routers import auth
from adapters.agent_runtime import InputParsingAgent


def _complete_llm_reply(*_args, **_kwargs):
    return {
        "decision": "ready_for_diagnosis",
        "question": "",
        "missing": [],
        "summary": {
            "known_skills": ["Vue", "JavaScript"],
            "practice_evidence": ["独立完成电商前端项目"],
            "weak_or_unknown": ["工程化部署不熟"],
            "learning_goals": ["前端开发工程师"],
        },
        "reason": "信息足以进入诊断",
    }


class ReviewDialogueApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.user_id = str(uuid.uuid4())
        db = SessionLocal()
        user = User(id=cls.user_id, username=f"dialogue_{cls.user_id[:8]}", password_hash="test")
        db.add(user)
        db.commit()
        db.close()
        # Endpoint code only requires the authenticated identity.  A compact
        # value object mirrors a JWT-authenticated request without returning a
        # detached SQLAlchemy model from the test fixture.
        main.app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(id=cls.user_id)

    @classmethod
    def tearDownClass(cls):
        main.app.dependency_overrides.clear()
        db = SessionLocal()
        session_ids = [row[0] for row in db.query(Session.id).filter(Session.user_id == cls.user_id).all()]
        if session_ids:
            db.query(SessionMessage).filter(SessionMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
            db.query(Session).filter(Session.id.in_(session_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id == cls.user_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    def _new_session(self) -> str:
        db = SessionLocal()
        job = db.query(Job).filter(Job.job_title == "前端开发工程师").first()
        job_id = job.id if job else ""
        db.close()
        self.assertIsNotNone(job)
        created = self.client.post("/api/session/create", json={"job_id": job_id})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["minimum_turns"], 2)
        return created.json()["id"]

    @patch("adapters.review_dialogue.chat_json", side_effect=_complete_llm_reply)
    def test_two_learner_turns_are_required_and_persisted(self, _chat):
        session_id = self._new_session()
        first = self.client.post(
            f"/api/session/{session_id}/review-turn",
            json={"content": "我会 Vue 和 JavaScript，做过商品列表页面。"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["turn_count"], 1)
        self.assertEqual(first.json()["decision"], "ask_followup")
        self.assertFalse(first.json()["ready_for_diagnosis"])
        self.assertTrue(first.json()["question"])

        second = self.client.post(
            f"/api/session/{session_id}/review-turn",
            json={"content": "项目中我负责购物车和订单页联调，工程化部署还不熟。"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["turn_count"], 2)
        self.assertEqual(second.json()["decision"], "ready_for_diagnosis")
        self.assertTrue(second.json()["ready_for_diagnosis"])
        self.assertTrue(second.json()["context_trace_id"])

        messages = self.client.get(f"/api/session/{session_id}/messages")
        self.assertEqual(messages.status_code, 200)
        self.assertEqual([item["role"] for item in messages.json()], ["user", "assistant", "user", "assistant"])

    @patch("adapters.review_dialogue.chat_json", side_effect=_complete_llm_reply)
    def test_explicit_skip_is_recorded_as_second_turn(self, _chat):
        session_id = self._new_session()
        self.client.post(
            f"/api/session/{session_id}/review-turn",
            json={"content": "我会 Python，写过一个简单接口。"},
        )
        skipped = self.client.post(
            f"/api/session/{session_id}/review-turn",
            json={"content": "暂不补充，按当前资料进入能力诊断。", "force_finish": True},
        )
        self.assertEqual(skipped.status_code, 200, skipped.text)
        self.assertEqual(skipped.json()["turn_count"], 2)
        self.assertTrue(skipped.json()["ready_for_diagnosis"])

    @patch("adapters.review_dialogue.chat_json", side_effect=_complete_llm_reply)
    def test_first_turn_cannot_bypass_minimum_with_force_finish(self, _chat):
        session_id = self._new_session()
        skipped = self.client.post(
            f"/api/session/{session_id}/review-turn",
            json={"content": "暂不补充，按当前资料进入能力诊断。", "force_finish": True},
        )
        self.assertEqual(skipped.status_code, 200, skipped.text)
        self.assertEqual(skipped.json()["turn_count"], 1)
        self.assertFalse(skipped.json()["ready_for_diagnosis"])
        self.assertEqual(skipped.json()["decision"], "ask_followup")

    def test_second_turn_weakness_does_not_negate_first_turn_skill(self):
        profile = InputParsingAgent()._run_rules(
            "后端开发工程师",
            "【第1轮学习者描述】我会使用 Redis 开发缓存接口。\n"
            "【第2轮学习者描述】我对缓存穿透排查还不熟，希望补强。",
        )
        self.assertNotIn("Redis", profile.negative_skills)
        self.assertGreater(profile.matched_skills.get("Redis", 0), 0.5)


if __name__ == "__main__":
    unittest.main()
