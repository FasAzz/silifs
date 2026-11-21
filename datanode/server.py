import argparse
import hashlib
import logging
import os
import threading
import time
from concurrent import futures

import grpc

from common import silifs_pb2 as pb
from common import silifs_pb2_grpc as pb_grpc

MAX_MSG = 16 * 1024 * 1024
CHANNEL_OPTS = [
    ("grpc.max_send_message_length", MAX_MSG),
    ("grpc.max_receive_message_length", MAX_MSG),
]
HEARTBEAT_INTERVAL = 3   # detik


class DataNodeService(pb_grpc.DataNodeServiceServicer):
    def __init__(self, data_dir, capacity_bytes=2048 * 1024 * 1024):
        self.data_dir = data_dir
        self.capacity_bytes = capacity_bytes
        os.makedirs(data_dir, exist_ok=True)

    def _path(self, chunk_id):
        return os.path.join(self.data_dir, chunk_id)

    def StoreChunk(self, request, context):
        # 1. Verifikasi checksum SHA-256 jika disertakan
        if request.checksum:
            calculated = hashlib.sha256(request.data).hexdigest()
            if calculated.lower() != request.checksum.lower():
                return pb.StoreChunkResponse(
                    ok=False,
                    error=f"Checksum mismatch: expected {request.checksum}, got {calculated}"
                )

        # 2. Pengecekan kapasitas disk
        target = self._path(request.chunk_id)
        existing_size = os.path.getsize(target) if os.path.exists(target) else 0
        free_bytes, _ = disk_stats(self.data_dir, self.capacity_bytes)
        needed_bytes = len(request.data) - existing_size

        if needed_bytes > free_bytes:
            return pb.StoreChunkResponse(
                ok=False,
                error=f"Disk capacity exceeded: needed {needed_bytes} bytes, free {free_bytes} bytes"
            )

        try:
            with open(target, "wb") as f:
                f.write(request.data)
            return pb.StoreChunkResponse(ok=True)
        except OSError as e:
            return pb.StoreChunkResponse(ok=False, error=str(e))

    def ReadChunk(self, request, context):
        target = self._path(request.chunk_id)
        if not os.path.exists(target):
            return pb.ReadChunkResponse(ok=False, error=f"Chunk {request.chunk_id} not found")
        try:
            with open(target, "rb") as f:
                return pb.ReadChunkResponse(ok=True, data=f.read())
        except OSError as e:
            return pb.ReadChunkResponse(ok=False, error=str(e))

    def DeleteChunk(self, request, context):
        target = self._path(request.chunk_id)
        if not os.path.exists(target):
            return pb.DeleteChunkResponse(ok=False)
        try:
            os.remove(target)
            return pb.DeleteChunkResponse(ok=True)
        except OSError:
            return pb.DeleteChunkResponse(ok=False)

    def ReplicateChunk(self, request, context):
        """Baca chunk lokal, hitung checksum, lalu kirim ke node tujuan."""
        target = self._path(request.chunk_id)
        if not os.path.exists(target):
            return pb.ReplicateChunkResponse(
                ok=False,
                error=f"Chunk {request.chunk_id} not found on source node"
            )
        try:
            with open(target, "rb") as f:
                data = f.read()
            checksum = hashlib.sha256(data).hexdigest()
            with grpc.insecure_channel(request.target_address, options=CHANNEL_OPTS) as ch:
                stub = pb_grpc.DataNodeServiceStub(ch)
                r = stub.StoreChunk(
                    pb.StoreChunkRequest(chunk_id=request.chunk_id, data=data, checksum=checksum),
                    timeout=30)
            return pb.ReplicateChunkResponse(ok=r.ok, error=r.error)
        except (OSError, grpc.RpcError) as e:
            return pb.ReplicateChunkResponse(ok=False, error=str(e))


def disk_stats(data_dir, capacity):
    used = 0
    count = 0
    if os.path.exists(data_dir):
        for name in os.listdir(data_dir):
            file_path = os.path.join(data_dir, name)
            if os.path.isfile(file_path):
                used += os.path.getsize(file_path)
                count += 1
    return max(capacity - used, 0), count


def register_and_heartbeat(args, address, log):
    master = pb_grpc.MasterServiceStub(
        grpc.insecure_channel(args.master, options=CHANNEL_OPTS))
    registered = False
    while True:
        try:
            if not registered:
                master.RegisterNode(pb.RegisterNodeRequest(
                    node_id=args.node_id, address=address,
                    capacity_bytes=args.capacity_mb * 1024 * 1024), timeout=5)
                registered = True
                log.info("terdaftar ke master %s", args.master)
            free, count = disk_stats(args.data_dir, args.capacity_mb * 1024 * 1024)
            r = master.Heartbeat(pb.HeartbeatRequest(
                node_id=args.node_id, free_bytes=free, chunk_count=count), timeout=5)
            if not r.ok:
                registered = False
        except grpc.RpcError:
            registered = False
            log.warning("master tidak terjangkau, mencoba lagi...")
        time.sleep(HEARTBEAT_INTERVAL)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--node-id", required=True)
    p.add_argument("--port", type=int, default=50052)
    p.add_argument("--master", default="localhost:50051")
    p.add_argument("--advertise", default=None,
                   help="alamat yang dilihat node lain, default localhost:<port>")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--capacity-mb", type=int, default=2048)
    args = p.parse_args()

    args.data_dir = args.data_dir or os.path.join("data", args.node_id)
    address = args.advertise or f"localhost:{args.port}"
    capacity_bytes = args.capacity_mb * 1024 * 1024

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s.%(msecs)03d [{args.node_id}] %(message)s",
        datefmt="%H:%M:%S")
    log = logging.getLogger(args.node_id)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=CHANNEL_OPTS)
    pb_grpc.add_DataNodeServiceServicer_to_server(
        DataNodeService(args.data_dir, capacity_bytes=capacity_bytes), server
    )
    server.add_insecure_port(f"0.0.0.0:{args.port}")
    server.start()
    log.info("data node berjalan di port %d, alamat %s", args.port, address)

    threading.Thread(target=register_and_heartbeat, args=(args, address, log),
                     daemon=True).start()
    server.wait_for_termination()


if __name__ == "__main__":
    main()