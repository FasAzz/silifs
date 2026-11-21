import time
import grpc
from common import silifs_pb2 as pb, silifs_pb2_grpc as pb_grpc

GB = 1024 ** 3
MB = 1024 ** 2

channel = grpc.insecure_channel("localhost:50051")
stub = pb_grpc.MasterServiceStub(channel)

# 1. daftarkan 4 node palsu
for i in range(1, 5):
    stub.RegisterNode(pb.RegisterNodeRequest(
        node_id=f"node{i}", address=f"datanode{i}:50052", capacity_bytes=10 * GB))

# 2. minta alokasi file 50 MB, chunk 4 MB, RF 2, round robin
resp = stub.AllocateChunks(pb.AllocateChunksRequest(
    filename="tes.bin", file_size=50 * MB, chunk_size=4 * MB,
    replication_factor=2, strategy=pb.ROUND_ROBIN))
print("alokasi ok:", resp.ok, "| jumlah chunk:", len(resp.chunks))
for c in resp.chunks[:4]:
    print(" ", c.chunk_id, list(c.node_addresses))

# 3. commit dan minta lokasi
stub.CommitFile(pb.CommitFileRequest(filename="tes.bin"))
loc = stub.GetChunkLocations(pb.GetChunkLocationsRequest(filename="tes.bin"))
print("lokasi ok:", loc.ok, "| ukuran:", loc.file_size)

# 4. tunggu 15 detik tanpa heartbeat: semua node harus terdeteksi mati
print("menunggu deteksi node mati...")
time.sleep(15)
loc = stub.GetChunkLocations(pb.GetChunkLocationsRequest(filename="tes.bin"))
print("replika tersisa di chunk 0:", list(loc.chunks[0].node_addresses))