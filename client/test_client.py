import hashlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from common import silifs_pb2 as pb
from client.client import SiliFSClient
from client.metrics import log_metric, CSV_HEADERS


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.test_dir, "metrics.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_log_metric_creates_header_and_row(self):
        log_metric(
            csv_path=self.csv_path,
            operation="upload",
            filename="sample.bin",
            strategy="round_robin",
            rf=2,
            chunk_mb=4.0,
            file_mb=10.0,
            duration_s=2.0,
            chunks_count=3,
            avg_chunk_latency_ms=15.5,
            ok=True,
        )

        self.assertTrue(os.path.exists(self.csv_path))
        with open(self.csv_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0], ",".join(CSV_HEADERS))
            self.assertIn("upload,sample.bin,round_robin,2,4.00,10.00,2.0000,5.0000,3,15.50,True", lines[1])


class TestSiliFSClient(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.test_dir, "metrics.csv")
        self.client = SiliFSClient(master_address="localhost:50051", metrics_csv=self.csv_path)

        # Create dummy file (10 KB)
        self.file_path = os.path.join(self.test_dir, "test.dat")
        self.file_content = b"A" * 10240
        with open(self.file_path, "wb") as f:
            f.write(self.file_content)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch.object(SiliFSClient, "_get_master_stub")
    @patch.object(SiliFSClient, "_get_datanode_stub")
    def test_upload_success(self, mock_get_datanode, mock_get_master):
        mock_master = MagicMock()
        mock_master.AllocateChunks.return_value = pb.AllocateChunksResponse(
            ok=True,
            chunks=[
                pb.ChunkPlacement(chunk_id="chk_1", index=0, node_addresses=["node1:50052", "node2:50053"]),
            ]
        )
        mock_master.CommitFile.return_value = pb.CommitFileResponse(ok=True)
        mock_get_master.return_value = mock_master

        mock_datanode = MagicMock()
        mock_datanode.StoreChunk.return_value = pb.StoreChunkResponse(ok=True)
        mock_get_datanode.return_value = mock_datanode

        res = self.client.upload(self.file_path, rf=2, chunk_mb=1, strategy="round_robin")
        self.assertTrue(res["ok"])
        self.assertEqual(res["chunks"], 1)

        # Verifikasi Master dipanggil
        mock_master.AllocateChunks.assert_called_once()
        mock_master.CommitFile.assert_called_once()

        # Verifikasi StoreChunk dipanggil 2 kali (karena 2 replika)
        self.assertEqual(mock_datanode.StoreChunk.call_count, 2)

        # Verifikasi metrics ditulis
        self.assertTrue(os.path.exists(self.csv_path))

    @patch.object(SiliFSClient, "_get_master_stub")
    @patch.object(SiliFSClient, "_get_datanode_stub")
    def test_download_failover(self, mock_get_datanode, mock_get_master):
        # Skenario: Node pertama mati/gagal, node kedua berhasil
        mock_master = MagicMock()
        mock_master.GetChunkLocations.return_value = pb.GetChunkLocationsResponse(
            ok=True,
            file_size=len(self.file_content),
            chunks=[
                pb.ChunkPlacement(chunk_id="chk_1", index=0, node_addresses=["dead_node:50052", "alive_node:50053"]),
            ]
        )
        mock_get_master.return_value = mock_master

        # Node pertama gagal, node kedua sukses
        node_dead = MagicMock()
        node_dead.ReadChunk.return_value = pb.ReadChunkResponse(ok=False, error="Connection refused")
        node_alive = MagicMock()
        node_alive.ReadChunk.return_value = pb.ReadChunkResponse(ok=True, data=self.file_content)

        def datanode_side_effect(addr):
            if "dead_node" in addr:
                return node_dead
            return node_alive

        mock_get_datanode.side_effect = datanode_side_effect

        out_path = os.path.join(self.test_dir, "downloaded.dat")
        res = self.client.download("test.dat", out_path)
        self.assertTrue(res["ok"])

        # Verifikasi file berhasil didownload dan hash sama
        with open(out_path, "rb") as f:
            downloaded_data = f.read()
        self.assertEqual(downloaded_data, self.file_content)


if __name__ == "__main__":
    unittest.main()
