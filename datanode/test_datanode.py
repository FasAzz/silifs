import hashlib
import os
import shutil
import tempfile
import unittest

from common import silifs_pb2 as pb
from datanode.server import DataNodeService


class TestDataNodeService(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # Kapasitas 100 KB untuk memudahkan tes batas kapasitas
        self.service = DataNodeService(self.test_dir, capacity_bytes=100 * 1024)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_store_and_read_chunk_success(self):
        data = b"Hello SiliFS distributed chunk test data!"
        checksum = hashlib.sha256(data).hexdigest()
        req = pb.StoreChunkRequest(chunk_id="chk_001", data=data, checksum=checksum)
        resp = self.service.StoreChunk(req, None)
        self.assertTrue(resp.ok)
        self.assertEqual(resp.error, "")

        read_resp = self.service.ReadChunk(pb.ReadChunkRequest(chunk_id="chk_001"), None)
        self.assertTrue(read_resp.ok)
        self.assertEqual(read_resp.data, data)

    def test_store_chunk_checksum_mismatch(self):
        data = b"Some sensitive block of data"
        bad_checksum = "abcdef123456"
        req = pb.StoreChunkRequest(chunk_id="chk_002", data=data, checksum=bad_checksum)
        resp = self.service.StoreChunk(req, None)
        self.assertFalse(resp.ok)
        self.assertIn("Checksum mismatch", resp.error)

    def test_store_chunk_capacity_exceeded(self):
        # 105 KB exceeds 100 KB limit
        large_data = b"X" * (105 * 1024)
        checksum = hashlib.sha256(large_data).hexdigest()
        req = pb.StoreChunkRequest(chunk_id="chk_003", data=large_data, checksum=checksum)
        resp = self.service.StoreChunk(req, None)
        self.assertFalse(resp.ok)
        self.assertIn("Disk capacity exceeded", resp.error)

    def test_read_non_existent_chunk(self):
        read_resp = self.service.ReadChunk(pb.ReadChunkRequest(chunk_id="chk_non_exist"), None)
        self.assertFalse(read_resp.ok)
        self.assertIn("not found", read_resp.error)

    def test_delete_chunk(self):
        data = b"data to delete"
        self.service.StoreChunk(pb.StoreChunkRequest(chunk_id="chk_del", data=data), None)
        del_resp = self.service.DeleteChunk(pb.DeleteChunkRequest(chunk_id="chk_del"), None)
        self.assertTrue(del_resp.ok)
        read_resp = self.service.ReadChunk(pb.ReadChunkRequest(chunk_id="chk_del"), None)
        self.assertFalse(read_resp.ok)


if __name__ == "__main__":
    unittest.main()
