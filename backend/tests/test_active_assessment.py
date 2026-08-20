import sys
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import main
from database import SessionLocal
from models.assessment import Assessment
from models.job import Job
from models.user import User
from routers import auth


class ActiveAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.user_id = str(uuid.uuid4())
        cls.other_user_id = str(uuid.uuid4())
        db = SessionLocal()
        cls.user = User(id=cls.user_id, username=f"active_{cls.user_id[:8]}", password_hash="test")
        other = User(id=cls.other_user_id, username=f"other_{cls.other_user_id[:8]}", password_hash="test")
        db.add_all([cls.user, other])
        db.flush()
        job = db.query(Job).first()
        now = datetime.utcnow()
        older = Assessment(
            user_id=cls.user_id,
            job_id=job.id,
            overall_mastery=0.61,
            created_at=now - timedelta(minutes=5),
        )
        latest = Assessment(
            user_id=cls.user_id,
            job_id=job.id,
            overall_mastery=0.82,
            created_at=now,
        )
        foreign = Assessment(
            user_id=cls.other_user_id,
            job_id=job.id,
            overall_mastery=0.90,
            created_at=now + timedelta(minutes=1),
        )
        pending = Assessment(
            user_id=cls.user_id,
            job_id=job.id,
            overall_mastery=None,
            created_at=now + timedelta(minutes=2),
        )
        db.add_all([older, latest, foreign, pending])
        db.commit()
        cls.older_id = older.id
        cls.latest_id = latest.id
        cls.foreign_id = foreign.id
        cls.pending_id = pending.id
        db.close()
        identity = SimpleNamespace(id=cls.user_id)
        main.app.dependency_overrides[auth.get_current_user] = lambda: identity

    @classmethod
    def tearDownClass(cls):
        main.app.dependency_overrides.clear()
        db = SessionLocal()
        db.query(Assessment).filter(Assessment.user_id.in_([cls.user_id, cls.other_user_id])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([cls.user_id, cls.other_user_id])).delete(synchronize_session=False)
        db.commit()
        db.close()

    def test_active_selection_is_persistent_and_owned(self):
        initial = self.client.get("/api/auth/me")
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(initial.json()["latest_assessment_id"], self.latest_id)
        self.assertEqual(initial.json()["active_assessment_id"], self.latest_id)

        selected = self.client.put("/api/auth/active-assessment", json={"assessment_id": self.older_id})
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(selected.json()["active_assessment_id"], self.older_id)
        self.assertEqual(selected.json()["latest_assessment_id"], self.latest_id)

        refreshed = self.client.get("/api/auth/me")
        self.assertEqual(refreshed.json()["active_assessment_id"], self.older_id)

        foreign = self.client.put("/api/auth/active-assessment", json={"assessment_id": self.foreign_id})
        self.assertEqual(foreign.status_code, 404, foreign.text)
        pending = self.client.put("/api/auth/active-assessment", json={"assessment_id": self.pending_id})
        self.assertEqual(pending.status_code, 404, pending.text)

    def test_deleting_active_result_falls_back_to_latest_completed(self):
        selected = self.client.put("/api/auth/active-assessment", json={"assessment_id": self.older_id})
        self.assertEqual(selected.status_code, 200, selected.text)
        deleted = self.client.delete(f"/api/assessment/{self.older_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        refreshed = self.client.get("/api/auth/me")
        self.assertEqual(refreshed.json()["active_assessment_id"], self.latest_id)


if __name__ == "__main__":
    unittest.main()
