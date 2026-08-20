import unittest

from adapters.context_manager import ContextManager


class ContextManagerTests(unittest.TestCase):
    def test_stage_allowlist_and_source_lineage_are_bounded(self):
        manager = ContextManager(trace_id="trace_test")
        snapshot = manager.record(
            "retrieve_knowledge",
            {
                "target_job": "后端开发工程师",
                "matched_skills": {"Redis": 0.4},
                "user_raw_history": "should not enter the next stage",
                "retrieval_hits": [
                    {
                        "source_chunk_id": "chunk-1",
                        "title": "Redis基础",
                        "score": 0.91,
                        "content": "x" * 3000,
                    }
                ],
            },
            {"hit_count": 1},
        )

        self.assertNotIn("user_raw_history", snapshot.inputs)
        self.assertEqual(snapshot.source_chunk_ids, ("chunk-1",))
        self.assertLessEqual(len(snapshot.inputs["approved_sources"][0]["content"]), 1200)
        self.assertEqual(snapshot.trace_id, "trace_test")
        self.assertEqual(snapshot.sequence, 1)

    def test_ledger_keeps_order_and_stage_metadata(self):
        manager = ContextManager(trace_id="trace_order")
        manager.record("parse_input", {"target_job": "产品经理", "user_input": "我做过需求分析"})
        manager.record("diagnose_capability", {"target_job": "产品经理", "matched_skills": {}})
        ledger = manager.as_dicts()

        self.assertEqual([item["sequence"] for item in ledger], [1, 2])
        self.assertEqual([item["stage"] for item in ledger], ["parse_input", "diagnose_capability"])
        self.assertTrue(all(item["schema_version"] == "agent-context.v1" for item in ledger))


if __name__ == "__main__":
    unittest.main()
