import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import main
from database import SessionLocal
from models.assessment import Assessment
from models.job import Job
from models.path import LearningPath
from models.resource import Resource
from models.session import Session, SessionMessage
from models.user import User
from routers import assessment as assessment_router
from routers import auth


class WorkflowIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.user_id = str(uuid.uuid4())
        db = SessionLocal()
        db.add(User(id=cls.user_id, username=f"workflow_{cls.user_id[:8]}", password_hash="test"))
        db.commit()
        db.close()
        main.app.dependency_overrides[auth.get_current_user] = lambda: SimpleNamespace(id=cls.user_id)

    @classmethod
    def tearDownClass(cls):
        main.app.dependency_overrides.clear()
        db = SessionLocal()
        session_ids = [row[0] for row in db.query(Session.id).filter(Session.user_id == cls.user_id).all()]
        if session_ids:
            db.query(SessionMessage).filter(SessionMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
            db.query(Session).filter(Session.id.in_(session_ids)).delete(synchronize_session=False)
        db.query(Assessment).filter(Assessment.user_id == cls.user_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == cls.user_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    def _job_id(self) -> str:
        db = SessionLocal()
        job = db.query(Job).filter(Job.job_title == "前端开发工程师").first()
        job_id = job.id
        db.close()
        return job_id

    def test_invalid_job_and_zero_score_diagnosis(self):
        invalid = self.client.post("/api/assessment/create", json={"job_id": str(uuid.uuid4())})
        self.assertEqual(invalid.status_code, 404, invalid.text)

        db = SessionLocal()
        assessment = Assessment(
            user_id=self.user_id,
            job_id=self._job_id(),
            overall_mastery=0,
            ability_vector=[],
            ability_matrix=[],
            knowledge_gaps=[],
            confidence=0.3,
        )
        db.add(assessment)
        db.commit()
        assessment_id = assessment.id
        db.close()
        response = self.client.get(f"/api/assessment/{assessment_id}/diagnosis")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["overall_mastery"], 0.0)

    def test_duplicate_submit_is_idempotent(self):
        db = SessionLocal()
        assessment = Assessment(user_id=self.user_id, job_id=self._job_id(), user_input="persisted context")
        db.add(assessment)
        db.flush()
        session = Session(
            user_id=self.user_id,
            job_id=assessment.job_id,
            status="completed",
            turn_count=2,
            minimum_turns=2,
            ready_for_diagnosis=1,
            assessment_id=assessment.id,
        )
        db.add(session)
        db.flush()
        db.add_all([
            SessionMessage(session_id=session.id, user_id=self.user_id, role="user", content="第一轮能力说明足够完整。", turn_index=1),
            SessionMessage(session_id=session.id, user_id=self.user_id, role="user", content="第二轮补充了项目证据。", turn_index=2),
        ])
        db.commit()
        assessment_id, session_id = assessment.id, session.id
        db.close()

        with patch.object(assessment_router, "_run_assessment") as runner:
            response = self.client.post(
                f"/api/assessment/{assessment_id}/submit",
                json={"user_input": "ignored", "session_id": session_id},
            )
        self.assertEqual(response.status_code, 200, response.text)
        runner.assert_not_called()

    def test_downstream_failure_rolls_back_diagnosis(self):
        db = SessionLocal()
        assessment = Assessment(user_id=self.user_id, job_id=self._job_id(), user_input="server context")
        db.add(assessment)
        db.flush()
        session = Session(
            user_id=self.user_id,
            job_id=assessment.job_id,
            status="completed",
            turn_count=2,
            minimum_turns=2,
            ready_for_diagnosis=1,
            assessment_id=assessment.id,
        )
        db.add(session)
        db.commit()
        assessment_id = assessment.id
        session_id = session.id
        db.close()
        diagnosis = {
            "overall_mastery": 0.5,
            "ability_vector": [{"index": 1, "name": "工程能力", "value": 0.5, "weight": "high", "category": "工程"}],
            "ability_matrix": [],
            "knowledge_gaps": ["工程能力"],
            "gap_validation": [],
            "confidence": 0.7,
            "requirement_scores": [],
            "calibration": {"status": "unvalidated", "evaluated_count": 0, "accuracy": None},
            "calibration_records": [],
        }
        with patch.object(assessment_router.agent_adapter, "diagnose", return_value=diagnosis), \
             patch.object(assessment_router.agent_adapter, "get_last_trace", return_value={"agents": []}), \
             patch.object(assessment_router.agent_adapter, "plan_learning_path", side_effect=RuntimeError("path failed")):
            assessment_router._run_assessment(
                assessment_id,
                self.user_id,
                "前端开发工程师",
                "server context",
                [],
                False,
            )

        db = SessionLocal()
        persisted = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        self.assertIsNone(persisted.overall_mastery)
        retriable_session = db.query(Session).filter(Session.id == session_id).first()
        self.assertIsNone(retriable_session.assessment_id)
        self.assertEqual(retriable_session.status, "ready_for_diagnosis")
        db.close()

    def test_unbound_resources_do_not_publish_false_success(self):
        db = SessionLocal()
        assessment = Assessment(user_id=self.user_id, job_id=self._job_id(), user_input="server context")
        db.add(assessment)
        db.flush()
        session = Session(
            user_id=self.user_id,
            job_id=assessment.job_id,
            status="completed",
            turn_count=2,
            minimum_turns=2,
            ready_for_diagnosis=1,
            assessment_id=assessment.id,
        )
        db.add(session)
        db.commit()
        assessment_id = assessment.id
        session_id = session.id
        db.close()

        diagnosis = {
            "overall_mastery": 0.5,
            "ability_vector": [{"index": 1, "name": "工程能力", "value": 0.5, "weight": "high", "category": "工程"}],
            "ability_matrix": [],
            "knowledge_gaps": ["工程能力"],
            "gap_validation": [],
            "confidence": 0.7,
            "requirement_scores": [],
            "calibration": {"status": "unvalidated", "evaluated_count": 0, "accuracy": None},
            "calibration_records": [],
        }
        path_steps = [{
            "step": 1,
            "knowledge_point": "Vue",
            "resource_type": "讲义",
            "estimated_time": 30,
            "status": "current",
            "weight": "high",
        }]
        generated = {
            "content_type": "讲义",
            "title": "Vue 能力补强讲义",
            "body": "围绕组件状态、事件处理和接口联调设计的可验证学习内容。",
            "difficulty": 2,
            "source_chunk_id": "",
            "source_text": "",
            "source_title": "Vue 工程实践",
            "source_score": 0.9,
            "generation_method": "rules",
        }

        def approve_unbound(_package_id, resources):
            return [
                {"resource_id": item["resource_id"], "status": "passed", "reason": "测试误放行"}
                for item in resources
            ]

        with patch.object(assessment_router.agent_adapter, "diagnose", return_value=diagnosis), \
             patch.object(assessment_router.agent_adapter, "get_last_trace", return_value={"agents": []}), \
             patch.object(assessment_router.agent_adapter, "plan_learning_path", return_value=path_steps), \
             patch.object(assessment_router.agent_adapter, "generate_resource", return_value=generated), \
             patch.object(assessment_router.agent_adapter, "review_resources", side_effect=approve_unbound):
            assessment_router._run_assessment(
                assessment_id,
                self.user_id,
                "前端开发工程师",
                "server context",
                [],
                False,
            )

        db = SessionLocal()
        persisted = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        self.assertIsNone(persisted.overall_mastery)
        self.assertEqual(db.query(Resource).filter(Resource.assessment_id == assessment_id).count(), 0)
        self.assertEqual(db.query(LearningPath).filter(LearningPath.assessment_id == assessment_id).count(), 0)
        retriable_session = db.query(Session).filter(Session.id == session_id).first()
        self.assertIsNone(retriable_session.assessment_id)
        self.assertEqual(retriable_session.status, "ready_for_diagnosis")
        db.close()


if __name__ == "__main__":
    unittest.main()
