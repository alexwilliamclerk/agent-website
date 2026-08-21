import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import main


class SecurityBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_private_result_endpoints_require_login(self):
        cases = [
            ("/api/resource/list", {}),
            ("/api/resource/search", {"q": "Spring Boot"}),
            ("/api/path/not-a-user", {}),
            ("/api/assessment/list", {}),
        ]
        for path, params in cases:
            with self.subTest(path=path):
                response = self.client.get(path, params=params)
                self.assertEqual(response.status_code, 401, response.text)

    def test_registration_rejects_weak_or_malformed_credentials(self):
        cases = [
            {"username": "a", "password": "123456"},
            {"username": "  ", "password": "123456"},
            {"username": "two words", "password": "123456"},
            {"username": "valid_name", "password": "123"},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/auth/register", json=payload)
                self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
