import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.calibration import (
    GroundTruthCalibrationAgent,
    build_automatic_evidence_labels,
    requirement_id,
)


class Profile:
    text = "我会 Redis，做过缓存项目"
    matched_skills = {"Redis": 0.72}
    negative_skills = set()


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.agent = GroundTruthCalibrationAgent()
        self.skills = [("Redis", "数据库"), ("FastAPI", "后端技术")]
        self.dimensions = [(1, "数据库", "专业方向"), (2, "后端技术", "专业方向")]
        self.diagnosis = {
            "overall_mastery": 0.5,
            "ability_vector": [
                {"index": 1, "name": "数据库", "value": 0.5, "weight": "high", "category": "专业方向"},
                {"index": 2, "name": "后端技术", "value": 0.5, "weight": "high", "category": "专业方向"},
            ],
            "knowledge_gaps": [],
            "requirement_scores": [],
        }

    def test_requirement_id_is_stable(self):
        self.assertEqual(requirement_id("后端开发工程师", "Redis"), "backend.redis")

    def test_without_gold_labels_is_unvalidated(self):
        result = self.agent.run(
            "后端开发工程师", self.diagnosis, self.skills, self.dimensions, Profile(), [], False
        )
        self.assertEqual(result["summary"]["status"], "unvalidated")
        self.assertIsNone(result["summary"]["accuracy"])

    def test_automatic_review_only_labels_explicit_evidence(self):
        labels = build_automatic_evidence_labels(
            "后端开发工程师", self.skills, Profile()
        )
        self.assertEqual([item["requirement_name"] for item in labels], ["Redis"])

    def test_trusted_gold_label_is_compared_and_can_correct(self):
        result = self.agent.run(
            "后端开发工程师",
            self.diagnosis,
            self.skills,
            self.dimensions,
            Profile(),
            [{"requirement_id": "backend.redis", "gold_score": 0.65, "source_type": "unit_test", "trusted": True}],
            True,
        )
        self.assertEqual(result["summary"]["status"], "passed")
        self.assertEqual(result["summary"]["evaluated_count"], 1)
        self.assertTrue(result["summary"]["correction_applied"])
        redis = next(item for item in result["diagnosis"]["requirement_scores"] if item["requirement_id"] == "backend.redis")
        self.assertEqual(redis["score"], 0.65)


if __name__ == "__main__":
    unittest.main()
