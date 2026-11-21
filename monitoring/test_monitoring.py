import os
import shutil
import tempfile
import unittest

from monitoring.app import app, check_node_alive, get_node_stats


class TestMonitoringApp(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_dashboard_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"SiliFS Cluster Monitor", resp.data)

    def test_api_status(self):
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("cluster", data)
        self.assertIn("nodes", data)
        self.assertIn("recent_metrics", data)

    def test_node_stats(self):
        node_dir = os.path.join(self.test_dir, "node1")
        os.makedirs(node_dir, exist_ok=True)
        # Tulis 2 chunk dummy
        with open(os.path.join(node_dir, "chk_1"), "wb") as f:
            f.write(b"12345")
        with open(os.path.join(node_dir, "chk_2"), "wb") as f:
            f.write(b"67890")

        stats = get_node_stats("node1", self.test_dir)
        self.assertEqual(stats["chunk_count"], 2)
        self.assertEqual(stats["used_bytes"], 10)


if __name__ == "__main__":
    unittest.main()
