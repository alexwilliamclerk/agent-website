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


if __name__ == "__main__":
    unittest.main()
