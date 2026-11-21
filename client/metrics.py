import csv
import os
from datetime import datetime
from typing import Optional


CSV_HEADERS = [
    "timestamp",
    "operation",
    "filename",
    "strategy",
    "rf",
    "chunk_mb",
    "file_mb",
    "duration_s",
    "throughput_mbps",
    "chunks",
    "avg_chunk_latency_ms",
    "ok",
]


def log_metric(
    csv_path: str,
    operation: str,
    filename: str,
    strategy: str,
    rf: int,
    chunk_mb: float,
    file_mb: float,
    duration_s: float,
    chunks_count: int,
    avg_chunk_latency_ms: float,
    ok: bool,
    timestamp: Optional[str] = None,
) -> None:
    """Mencatat hasil operasi upload/download ke file CSV."""
    if not csv_path:
        return

    # Buat direktori jika belum ada
    dir_name = os.path.dirname(csv_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    throughput_mbps = (file_mb / duration_s) if duration_s > 0 else 0.0

    row = {
        "timestamp": timestamp,
        "operation": operation,
        "filename": filename,
        "strategy": strategy,
        "rf": rf,
        "chunk_mb": f"{chunk_mb:.2f}",
        "file_mb": f"{file_mb:.2f}",
        "duration_s": f"{duration_s:.4f}",
        "throughput_mbps": f"{throughput_mbps:.4f}",
        "chunks": chunks_count,
        "avg_chunk_latency_ms": f"{avg_chunk_latency_ms:.2f}",
        "ok": ok,
    }

    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
