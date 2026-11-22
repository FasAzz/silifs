import logging
import math
import threading
import time
import uuid
from concurrent import futures

import grpc

from common import silifs_pb2 as pb
from common import silifs_pb2_grpc as pb_grpc
from master.placement import NodeInfo, get_strategy

PORT = 50051
HEARTBEAT_TIMEOUT = 30          # detik tanpa heartbeat = node dianggap mati
MAX_MSG = 16 * 1024 * 1024      # naikkan batas 4 MB bawaan gRPC

CHANNEL_OPTS = [
    ("grpc.max_send_message_length", MAX_MSG),
    ("grpc.max_receive_message_length", MAX_MSG),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [master] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("master")


class MasterState:
    """Semua data yang dipegang master. Diakses dari banyak thread, jadi pakai lock."""

    def __init__(self):
        self.lock = threading.Lock()
        self.nodes = {}        # node_id -> NodeInfo
        self.files = {}        # filename -> {"file_size", "committed", "chunks": [...]}
        self.strategies = {}   # nama strategi -> objek (supaya pointer round-robin tersimpan)

    def get_strategy(self, name):
        if name not in self.strategies:
            self.strategies[name] = get_strategy(name)
        return self.strategies[name]

    def alive_nodes(self):
        return [n for n in self.nodes.values() if n.alive]


class MasterService(pb_grpc.MasterServiceServicer):
    def __init__(self, state):
        self.state = state

    def RegisterNode(self, request, context):
        with self.state.lock:
            self.state.nodes[request.node_id] = NodeInfo(
                node_id=request.node_id,
                address=request.address,
                capacity_bytes=request.capacity_bytes,
                free_bytes=request.capacity_bytes,
                last_heartbeat=time.time(),
                alive=True,
            )
        log.info("node terdaftar: %s (%s)", request.node_id, request.address)
        return pb.RegisterNodeResponse(ok=True)

    def Heartbeat(self, request, context):
        with self.state.lock:
            node = self.state.nodes.get(request.node_id)
            if node is None:
                # master restart / node belum terdaftar: suruh daftar ulang
                return pb.HeartbeatResponse(ok=False)
            if not node.alive:
                log.info("node hidup kembali: %s", node.node_id)
            node.alive = True
            node.last_heartbeat = time.time()
            node.free_bytes = request.free_bytes
            node.chunk_count = request.chunk_count
        return pb.HeartbeatResponse(ok=True)

    def AllocateChunks(self, request, context):
        strategy_name = pb.PlacementStrategy.Name(request.strategy).lower()
        rf = request.replication_factor
        num_chunks = max(1, math.ceil(request.file_size / request.chunk_size))

        with self.state.lock:
            alive = self.state.alive_nodes()
            if len(alive) < rf:
                return pb.AllocateChunksResponse(
                    ok=False,
                    error=f"node hidup {len(alive)}, kurang dari RF {rf}",
                )

            strategy = self.state.get_strategy(strategy_name)
            file_id = uuid.uuid4().hex[:8]
            chunks = []
            for i in range(num_chunks):
                picked = strategy.choose(alive, rf, request.chunk_size)
                chunks.append({
                    "chunk_id": f"{file_id}_{i}",
                    "index": i,
                    "nodes": [n.address for n in picked],
                })

            self.state.files[request.filename] = {
                "file_size": request.file_size,
                "chunk_size": request.chunk_size,
                "rf": rf,
                "strategy": strategy_name,
                "committed": False,
                "chunks": chunks,
            }

        log.info("alokasi %s: %d chunk, RF=%d, strategi=%s",
                 request.filename, num_chunks, rf, strategy_name)
        return pb.AllocateChunksResponse(
            ok=True,
            chunks=[
                pb.ChunkPlacement(chunk_id=c["chunk_id"], index=c["index"],
                                  node_addresses=c["nodes"])
                for c in chunks
            ],
        )

    def CommitFile(self, request, context):
        with self.state.lock:
            f = self.state.files.get(request.filename)
            if f is None:
                return pb.CommitFileResponse(ok=False)
            f["committed"] = True
        log.info("file commit: %s", request.filename)
        return pb.CommitFileResponse(ok=True)

    def GetChunkLocations(self, request, context):
        with self.state.lock:
            f = self.state.files.get(request.filename)
            if f is None or not f["committed"]:
                return pb.GetChunkLocationsResponse(ok=False, error="file tidak ditemukan")
            alive_addr = {n.address for n in self.state.alive_nodes()}
            chunks = []
            for c in f["chunks"]:
                # hanya kirim replika di node yang masih hidup
                live = [a for a in c["nodes"] if a in alive_addr]
                chunks.append(pb.ChunkPlacement(
                    chunk_id=c["chunk_id"], index=c["index"], node_addresses=live))
            return pb.GetChunkLocationsResponse(ok=True, file_size=f["file_size"], chunks=chunks)


def rereplicate(state, dead_node_id, t_detect):
    """Pulihkan chunk yang kehilangan replika akibat node mati."""
    tasks = []   # (chunk, sumber, tujuan, file)
    with state.lock:
        alive = state.alive_nodes()
        alive_addr = {n.address for n in alive}
        for fname, f in state.files.items():
            if not f["committed"]:
                continue
            strategy = state.get_strategy(f["strategy"])
            for c in f["chunks"]:
                live = [a for a in c["nodes"] if a in alive_addr]
                missing = f["rf"] - len(live)
                if missing <= 0 or not live:
                    continue   # tidak perlu dipulihkan, atau semua replika hilang
                candidates = [n for n in alive if n.address not in c["nodes"]]
                if len(candidates) < missing:
                    continue
                targets = strategy.choose(candidates, missing, f["chunk_size"])
                for t in targets:
                    tasks.append((c, live[0], t.address))

    log.info("re-replication: %d chunk perlu dipulihkan (node mati: %s)",
             len(tasks), dead_node_id)
    ok_count = 0
    for c, source, target in tasks:
        try:
            with grpc.insecure_channel(source, options=CHANNEL_OPTS) as ch:
                stub = pb_grpc.DataNodeServiceStub(ch)
                r = stub.ReplicateChunk(
                    pb.ReplicateChunkRequest(chunk_id=c["chunk_id"], target_address=target),
                    timeout=30)
            if r.ok:
                with state.lock:
                    # ganti alamat node mati dengan node baru di metadata
                    c["nodes"] = [a for a in c["nodes"] if a in
                                  {n.address for n in state.alive_nodes()}] + [target]
                ok_count += 1
        except grpc.RpcError as e:
            log.warning("gagal replikasi %s: %s", c["chunk_id"], e.code())

    durasi = time.time() - t_detect
    log.info("PEMULIHAN SELESAI: %d/%d chunk, waktu pemulihan = %.3f detik",
             ok_count, len(tasks), durasi)
    
def monitor_loop(state):
    while True:
        time.sleep(2)
        now = time.time()
        newly_dead = []
        with state.lock:
            for node in state.nodes.values():
                if node.alive and now - node.last_heartbeat > HEARTBEAT_TIMEOUT:
                    node.alive = False
                    newly_dead.append(node.node_id)
                    log.warning("NODE MATI terdeteksi: %s", node.node_id)
        for nid in newly_dead:
            threading.Thread(target=rereplicate, args=(state, nid, time.time()),
                             daemon=True).start()


def serve():
    state = MasterState()
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=CHANNEL_OPTS
    )
    pb_grpc.add_MasterServiceServicer_to_server(MasterService(state), server)
    server.add_insecure_port(f"0.0.0.0:{PORT}")   # 0.0.0.0, bukan localhost
    server.start()
    threading.Thread(target=monitor_loop, args=(state,), daemon=True).start()
    log.info("master berjalan di port %d", PORT)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()