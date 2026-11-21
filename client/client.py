import hashlib
import logging
import os
import time
from typing import Dict, Any, Optional

import grpc

from common import silifs_pb2 as pb
from common import silifs_pb2_grpc as pb_grpc
from client.metrics import log_metric

MAX_MSG = 16 * 1024 * 1024
CHANNEL_OPTS = [
    ("grpc.max_send_message_length", MAX_MSG),
    ("grpc.max_receive_message_length", MAX_MSG),
]

STRATEGY_MAP = {
    "random": pb.RANDOM,
    "round_robin": pb.ROUND_ROBIN,
    "capacity_aware": pb.CAPACITY_AWARE,
}

STRATEGY_NAME_MAP = {
    pb.RANDOM: "random",
    pb.ROUND_ROBIN: "round_robin",
    pb.CAPACITY_AWARE: "capacity_aware",
}

logger = logging.getLogger("silifs.client")


class SiliFSClient:
    def __init__(self, master_address: str = "localhost:50051", metrics_csv: Optional[str] = None):
        self.master_address = master_address
        self.metrics_csv = metrics_csv

    def _get_master_stub(self) -> pb_grpc.MasterServiceStub:
        channel = grpc.insecure_channel(self.master_address, options=CHANNEL_OPTS)
        return pb_grpc.MasterServiceStub(channel)

    def _get_datanode_stub(self, node_address: str) -> pb_grpc.DataNodeServiceStub:
        channel = grpc.insecure_channel(node_address, options=CHANNEL_OPTS)
        return pb_grpc.DataNodeServiceStub(channel)

    def upload(
        self,
        local_path: str,
        filename: Optional[str] = None,
        rf: int = 2,
        chunk_mb: int = 4,
        strategy: str = "round_robin",
    ) -> Dict[str, Any]:
        """
        Alur upload file ke SiliFS:
        1. Baca ukuran file dan validasi.
        2. Minta alokasi chunk ke Master (AllocateChunks).
        3. Pecah file per chunk, hitung SHA-256, kirim (StoreChunk) ke semua node replika.
        4. Jika seluruh replika berhasil, CommitFile ke Master.
        5. Catat metrik ke CSV.
        """
        start_time = time.time()
        chunk_latencies = []
        filename = filename or os.path.basename(local_path)

        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"File lokal tidak ditemukan: {local_path}")

        file_size = os.path.getsize(local_path)
        file_mb = file_size / (1024 * 1024)
        chunk_size_bytes = chunk_mb * 1024 * 1024

        strategy_enum = STRATEGY_MAP.get(strategy.lower(), pb.ROUND_ROBIN)
        strategy_str = strategy.lower()

        logger.info(
            "Memulai upload %s (%.2f MB), RF=%d, Chunk=%d MB, Strategi=%s",
            filename, file_mb, rf, chunk_mb, strategy_str
        )

        master_stub = self._get_master_stub()

        # 1. Alokasi chunk ke master
        alloc_resp = master_stub.AllocateChunks(
            pb.AllocateChunksRequest(
                filename=filename,
                file_size=file_size,
                chunk_size=chunk_size_bytes,
                replication_factor=rf,
                strategy=strategy_enum,
            ),
            timeout=10,
        )

        if not alloc_resp.ok:
            error_msg = f"Alokasi master gagal: {alloc_resp.error}"
            logger.error(error_msg)
            duration_s = time.time() - start_time
            if self.metrics_csv:
                log_metric(
                    self.metrics_csv, "upload", filename, strategy_str, rf,
                    chunk_mb, file_mb, duration_s, 0, 0.0, False
                )
            return {"ok": False, "error": error_msg}

        chunks_plan = sorted(alloc_resp.chunks, key=lambda c: c.index)
        total_chunks = len(chunks_plan)

        # 2. Baca file dan kirim chunk ke semua replika
        with open(local_path, "rb") as f:
            for chunk_meta in chunks_plan:
                chunk_data = f.read(chunk_size_bytes)
                checksum = hashlib.sha256(chunk_data).hexdigest()

                for node_addr in chunk_meta.node_addresses:
                    store_t0 = time.time()
                    try:
                        node_stub = self._get_datanode_stub(node_addr)
                        resp = node_stub.StoreChunk(
                            pb.StoreChunkRequest(
                                chunk_id=chunk_meta.chunk_id,
                                data=chunk_data,
                                checksum=checksum,
                            ),
                            timeout=30,
                        )
                        latency_ms = (time.time() - store_t0) * 1000
                        chunk_latencies.append(latency_ms)

                        if not resp.ok:
                            err = f"Node {node_addr} gagal menyimpan chunk {chunk_meta.chunk_id}: {resp.error}"
                            logger.error(err)
                            duration_s = time.time() - start_time
                            avg_lat = sum(chunk_latencies) / len(chunk_latencies) if chunk_latencies else 0.0
                            if self.metrics_csv:
                                log_metric(
                                    self.metrics_csv, "upload", filename, strategy_str, rf,
                                    chunk_mb, file_mb, duration_s, total_chunks, avg_lat, False
                                )
                            return {"ok": False, "error": err}
                    except grpc.RpcError as e:
                        err = f"Gagal menghubungi node {node_addr} untuk chunk {chunk_meta.chunk_id}: {e.code()}"
                        logger.error(err)
                        duration_s = time.time() - start_time
                        avg_lat = sum(chunk_latencies) / len(chunk_latencies) if chunk_latencies else 0.0
                        if self.metrics_csv:
                            log_metric(
                                self.metrics_csv, "upload", filename, strategy_str, rf,
                                chunk_mb, file_mb, duration_s, total_chunks, avg_lat, False
                            )
                        return {"ok": False, "error": err}

        # 3. Commit file ke Master
        commit_resp = master_stub.CommitFile(
            pb.CommitFileRequest(filename=filename),
            timeout=10,
        )

        duration_s = time.time() - start_time
        avg_chunk_latency_ms = sum(chunk_latencies) / len(chunk_latencies) if chunk_latencies else 0.0
        throughput_mbps = (file_mb / duration_s) if duration_s > 0 else 0.0

        if not commit_resp.ok:
            err = "Commit file ke Master gagal"
            logger.error(err)
            if self.metrics_csv:
                log_metric(
                    self.metrics_csv, "upload", filename, strategy_str, rf,
                    chunk_mb, file_mb, duration_s, total_chunks, avg_chunk_latency_ms, False
                )
            return {"ok": False, "error": err}

        logger.info(
            "Upload selesai: %s, durasi=%.3fs, throughput=%.2f MB/s",
            filename, duration_s, throughput_mbps
        )

        if self.metrics_csv:
            log_metric(
                self.metrics_csv, "upload", filename, strategy_str, rf,
                chunk_mb, file_mb, duration_s, total_chunks, avg_chunk_latency_ms, True
            )

        return {
            "ok": True,
            "filename": filename,
            "file_size": file_size,
            "file_mb": file_mb,
            "chunks": total_chunks,
            "duration_s": duration_s,
            "throughput_mbps": throughput_mbps,
            "avg_chunk_latency_ms": avg_chunk_latency_ms,
        }

    def download(self, filename: str, output_path: str) -> Dict[str, Any]:
        """
        Alur download file dari SiliFS:
        1. Minta lokasi chunk ke Master (GetChunkLocations).
        2. Untuk tiap chunk, baca (ReadChunk) dari replika pertama;
           jika gagal, fallback ke replika berikutnya (fault tolerance).
        3. Rekonstruksi file sesuai file_size asli.
        4. Catat metrik ke CSV.
        """
        start_time = time.time()
        chunk_latencies = []

        logger.info("Memulai download file: %s -> %s", filename, output_path)

        master_stub = self._get_master_stub()
        loc_resp = master_stub.GetChunkLocations(
            pb.GetChunkLocationsRequest(filename=filename),
            timeout=10,
        )

        if not loc_resp.ok:
            err = f"Gagal mendapatkan lokasi chunk: {loc_resp.error}"
            logger.error(err)
            duration_s = time.time() - start_time
            if self.metrics_csv:
                log_metric(
                    self.metrics_csv, "download", filename, "unknown", 0,
                    0.0, 0.0, duration_s, 0, 0.0, False
                )
            return {"ok": False, "error": err}

        file_size = loc_resp.file_size
        file_mb = file_size / (1024 * 1024)
        chunks_plan = sorted(loc_resp.chunks, key=lambda c: c.index)
        total_chunks = len(chunks_plan)

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        bytes_written = 0
        with open(output_path, "wb") as out_f:
            for chunk_meta in chunks_plan:
                chunk_data = None
                success = False

                if not chunk_meta.node_addresses:
                    err = f"Tidak ada node replika aktif untuk chunk {chunk_meta.chunk_id}"
                    logger.error(err)
                    duration_s = time.time() - start_time
                    avg_lat = sum(chunk_latencies) / len(chunk_latencies) if chunk_latencies else 0.0
                    if self.metrics_csv:
                        log_metric(
                            self.metrics_csv, "download", filename, "unknown", 0,
                            0.0, file_mb, duration_s, total_chunks, avg_lat, False
                        )
                    return {"ok": False, "error": err}

                # Mekanisme Failover: coba setiap alamat replika
                for node_addr in chunk_meta.node_addresses:
                    read_t0 = time.time()
                    try:
                        node_stub = self._get_datanode_stub(node_addr)
                        resp = node_stub.ReadChunk(
                            pb.ReadChunkRequest(chunk_id=chunk_meta.chunk_id),
                            timeout=30,
                        )
                        latency_ms = (time.time() - read_t0) * 1000
                        chunk_latencies.append(latency_ms)

                        if resp.ok:
                            chunk_data = resp.data
                            success = True
                            break
                        else:
                            logger.warning(
                                "Gagal membaca chunk %s dari %s: %s, mencoba replika berikutnya...",
                                chunk_meta.chunk_id, node_addr, resp.error
                            )
                    except grpc.RpcError as e:
                        logger.warning(
                            "Koneksi ke node %s gagal untuk chunk %s (%s), mencoba replika berikutnya...",
                            node_addr, chunk_meta.chunk_id, e.code()
                        )

                if not success or chunk_data is None:
                    err = f"Seluruh replika untuk chunk {chunk_meta.chunk_id} gagal diakses"
                    logger.error(err)
                    duration_s = time.time() - start_time
                    avg_lat = sum(chunk_latencies) / len(chunk_latencies) if chunk_latencies else 0.0
                    if self.metrics_csv:
                        log_metric(
                            self.metrics_csv, "download", filename, "unknown", 0,
                            0.0, file_mb, duration_s, total_chunks, avg_lat, False
                        )
                    return {"ok": False, "error": err}

                # Tulis potongan chunk ke output (potong jika melebihi ukuran asli file)
                remaining = file_size - bytes_written
                to_write = chunk_data[:remaining]
                out_f.write(to_write)
                bytes_written += len(to_write)

        duration_s = time.time() - start_time
        avg_chunk_latency_ms = sum(chunk_latencies) / len(chunk_latencies) if chunk_latencies else 0.0
        throughput_mbps = (file_mb / duration_s) if duration_s > 0 else 0.0

        logger.info(
            "Download selesai: %s, ukuran=%.2f MB, durasi=%.3fs, throughput=%.2f MB/s",
            filename, file_mb, duration_s, throughput_mbps
        )

        if self.metrics_csv:
            log_metric(
                self.metrics_csv, "download", filename, "unknown", 0,
                0.0, file_mb, duration_s, total_chunks, avg_chunk_latency_ms, True
            )

        return {
            "ok": True,
            "filename": filename,
            "output_path": output_path,
            "file_size": file_size,
            "file_mb": file_mb,
            "chunks": total_chunks,
            "duration_s": duration_s,
            "throughput_mbps": throughput_mbps,
            "avg_chunk_latency_ms": avg_chunk_latency_ms,
        }
