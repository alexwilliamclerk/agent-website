import sys
import uuid
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import main
from database import SessionLocal
from models.assessment import Assessment
from models.job import Job
from models.learning_record import LearningRecord
from models.resource import Resource
from models.resource_bookmark import ResourceBookmark
from models.session import Session
from models.user import User
from routers import auth


class ResourceActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.user_id = str(uuid.uuid4())
        db = SessionLocal()
        cls.user = User(
            id=cls.user_id,
            username=f"resource_{cls.user_id[:8]}",
            password_hash="test",
        )
        db.add(cls.user)
        db.commit()
        db.refresh(cls.user)
        db.expunge(cls.user)
        db.close()
        main.app.dependency_overrides[auth.get_current_user] = lambda: cls.user

    @classmethod
    def tearDownClass(cls):
        main.app.dependency_overrides.clear()
        db = SessionLocal()
        resource_ids = [row[0] for row in db.query(Resource.id).join(
            Assessment, Resource.assessment_id == Assessment.id
        ).filter(Assessment.user_id == cls.user_id).all()]
        if resource_ids:
            db.query(ResourceBookmark).filter(ResourceBookmark.resource_id.in_(resource_ids)).delete(synchronize_session=False)
            db.query(LearningRecord).filter(LearningRecord.resource_id.in_(resource_ids)).delete(synchronize_session=False)
            db.query(Resource).filter(Resource.id.in_(resource_ids)).delete(synchronize_session=False)
        db.query(Session).filter(Session.user_id == cls.user_id).delete(synchronize_session=False)
        db.query(Assessment).filter(Assessment.user_id == cls.user_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == cls.user_id).delete(synchronize_session=False)
        db.commit()
        db.close()

    def _create_resource(self):
        db = SessionLocal()
        job = db.query(Job).filter(Job.job_title == "后端开发工程师").first()
        self.assertIsNotNone(job)
        assessment = Assessment(user_id=self.user_id, job_id=job.id, overall_mastery=0.6)
        db.add(assessment)
        db.flush()
        resource = Resource(
            assessment_id=assessment.id,
            knowledge_point="Redis 缓存",
            content_type="讲义",
            title="Redis 缓存学习讲义",
            body="本讲义介绍缓存读写策略、失效机制与可验证的练习步骤。",
            difficulty=2,
            source_chunk_id="backend.redis.actions",
            source_text="Redis 可用于缓存高频访问数据，并需要配置合理的失效策略。",
            review_status="passed",
            review_reason="测试来源一致",
            generation_method="test",
            is_legacy=0,
        )
        db.add(resource)
        db.commit()
        ids = (assessment.id, resource.id)
        db.close()
        return ids

    def test_bookmark_learning_progress_and_delete_cleanup(self):
        assessment_id, resource_id = self._create_resource()

        bookmarked = self.client.post(f"/api/resource/{resource_id}/bookmark")
        self.assertEqual(bookmarked.status_code, 200, bookmarked.text)
        repeated = self.client.post(f"/api/resource/{resource_id}/bookmark")
        self.assertEqual(repeated.status_code, 200, repeated.text)
        bookmarks = self.client.get("/api/resource/bookmarks")
        self.assertEqual(bookmarks.status_code, 200, bookmarks.text)
        self.assertEqual([item["resource_id"] for item in bookmarks.json()], [resource_id])

        started = self.client.post(f"/api/record/resource/{resource_id}/start")
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["status"], "in_progress")
        record_id = started.json()["id"]
        repeated_start = self.client.post(f"/api/record/resource/{resource_id}/start")
        self.assertEqual(repeated_start.json()["id"], record_id)

        listed = self.client.get("/api/record/list", params={"assessment_id": assessment_id})
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()), 1)
        completed = self.client.put(f"/api/record/{record_id}/complete", json={"time_spent": 120})
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["status"], "completed")

        deleted = self.client.delete(f"/api/assessment/{assessment_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        db = SessionLocal()
        self.assertIsNone(db.query(Resource).filter(Resource.id == resource_id).first())
        self.assertIsNone(db.query(ResourceBookmark).filter(ResourceBookmark.resource_id == resource_id).first())
        self.assertIsNone(db.query(LearningRecord).filter(LearningRecord.resource_id == resource_id).first())
        db.close()


if __name__ == "__main__":
    unittest.main()
