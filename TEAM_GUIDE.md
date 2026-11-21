# Panduan Tim

## Tim

| Anggota | Peran | Branch (`nama/tugas`) |
|---|---|---|
| Fasha | Master, strategi penempatan, heartbeat, re-replication, Docker, Kubernetes | `fasha/...` |
| Azhar | Client, penyempurnaan data node, metrik CSV, (bonus) monitoring | `azhar/...` |
| Fajar | Skrip eksperimen, grafik, laporan, README final, video demo | `fajar/...` |

## Status

- [x] `proto/silifs.proto`: kontrak gRPC (terkunci)
- [x] `master/placement.py`: 3 strategi penempatan
- [x] `master/server.py`: registrasi, heartbeat, alokasi, commit, deteksi node mati, re-replication
- [x] `datanode/server.py`: versi sederhana (teruji: registrasi, heartbeat)
- [ ] `client/`: upload dan download (Azhar)
- [ ] `experiments/`: skrip eksperimen (Fajar)
- [ ] `deploy/`: Dockerfile dan Compose (Fasha)
- [ ] Uji re-replication sungguhan (butuh client)

## Setup

```powershell
git checkout main
git pull origin main
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Semua perintah dijalankan dari root repo dengan venv aktif.

## Menjalankan sistem (tanpa Docker)

Satu terminal per proses:

```powershell
python -m master.server
python -m datanode.server --node-id node1 --port 50052
python -m datanode.server --node-id node2 --port 50053
python -m datanode.server --node-id node3 --port 50054
```

Opsi data node: `--capacity-mb` (kapasitas virtual, default 2048), `--master` (default `localhost:50051`), `--data-dir` (default `data/<node_id>`).

Log yang normal: master mencetak `node terdaftar: ...`. Kalau satu data node dihentikan (`Ctrl+C`), sekitar 10 sampai 12 detik kemudian master mencetak `NODE MATI terdeteksi`.

## Aturan kerja

- Satu branch per tugas, format `nama/tugas` (contoh `azhar/client-upload`).
- Jangan push langsung ke `main`. Merge lewat Pull Request.
- Sebelum mulai kerja: `git pull origin main`.
- Commit kecil dan sering, pesan commit jelas.
- `proto/silifs.proto` terkunci. Kalau perlu diubah, kabari grup dulu, lalu generate ulang:
  `python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/silifs.proto`
  dan perbaiki import di `common/silifs_pb2_grpc.py` menjadi `from common import silifs_pb2 as silifs__pb2`.
- Impor kode gRPC: `from common import silifs_pb2 as pb, silifs_pb2_grpc as pb_grpc`.
- Semua channel dan server wajib memakai batas pesan 16 MB (bawaan gRPC hanya 4 MB, terlalu kecil untuk chunk 4 MB):
  ```python
  CHANNEL_OPTS = [("grpc.max_send_message_length", 16*1024*1024),
                  ("grpc.max_receive_message_length", 16*1024*1024)]
  ```
- Folder `data/` dan `.venv/` tidak boleh ter-commit (sudah di `.gitignore`).

---

## Tugas Azhar: Client dan data node

Folder: `client/` (buat `client/__init__.py`) dan `datanode/server.py`.

### 1. Client CLI (`client/cli.py`)

Antarmuka yang harus tersedia:

```powershell
python -m client.cli upload <path_file> --rf 2 --chunk-mb 4 --strategy round_robin
python -m client.cli download <nama_file> --out <path_tujuan>
```

Opsi umum: `--master localhost:50051` (default) dan `--metrics-csv experiments/results/client_metrics.csv`.
Pilihan `--strategy`: `random`, `round_robin`, `capacity_aware` (petakan ke `pb.RANDOM`, `pb.ROUND_ROBIN`, `pb.CAPACITY_AWARE`).

### 2. Alur upload

1. Baca ukuran file. Panggil `MasterService.AllocateChunks(filename, file_size, chunk_size (byte), replication_factor, strategy)`.
2. Respons berisi daftar `ChunkPlacement` (`chunk_id`, `index`, `node_addresses`). Jika `ok=False`, tampilkan `error` dan berhenti.
3. Pecah file menjadi potongan sebesar `chunk_size` (potongan terakhir boleh lebih kecil).
4. Untuk tiap chunk, kirim `DataNodeService.StoreChunk(chunk_id, data, checksum)` ke **semua** alamat di `node_addresses`. Chunk dianggap sukses jika semua replika `ok=True`.
5. Jika semua chunk sukses, panggil `MasterService.CommitFile(filename)`. Jika ada yang gagal, jangan commit.

### 3. Alur download

1. Panggil `MasterService.GetChunkLocations(filename)`. Master hanya mengembalikan replika di node yang hidup.
2. Untuk tiap chunk, panggil `ReadChunk` ke alamat pertama. Jika gagal, coba alamat berikutnya (inilah yang membuktikan fault tolerance).
3. Urutkan chunk berdasarkan `index`, gabungkan, tulis ke file tujuan. Potong sesuai `file_size`.
4. Jika semua replika sebuah chunk gagal, laporkan error yang jelas.

### 4. Checksum (data node dan client)

- Client mengisi `checksum` (SHA-256 hex) saat `StoreChunk`.
- Data node memverifikasi sebelum menyimpan. Jika tidak cocok, kembalikan `ok=False` dengan `error`.
- Client memverifikasi ulang saat download.

### 5. Metrik ke CSV

Tiap operasi upload atau download menambah satu baris ke CSV (buat folder dan header jika belum ada). Kolom (final ditentukan Fajar, ubah dengan persetujuan):

```
timestamp,operation,filename,strategy,rf,chunk_mb,file_mb,duration_s,throughput_mbps,chunks,avg_chunk_latency_ms,ok
```

`avg_chunk_latency_ms` adalah rata-rata waktu satu `StoreChunk` atau `ReadChunk`.

### 6. Penyempurnaan data node

- Verifikasi checksum (poin 4).
- Penanganan error yang rapi (disk penuh, chunk tidak ditemukan).
- Tetap kompatibel dengan opsi CLI yang ada (`--node-id`, `--port`, `--master`, `--advertise`, `--data-dir`, `--capacity-mb`).

### 7. Bonus

Monitoring sederhana (status node, jumlah chunk per node) via Flask atau Prometheus. Kerjakan setelah poin 1 sampai 6 selesai. Kalau butuh endpoint statistik di master, minta ke Fasha.

### Definisi selesai

- Upload file 50 MB lalu download kembali menghasilkan file dengan hash SHA-256 yang sama dengan aslinya.
- Download tetap berhasil saat 1 data node dimatikan (RF >= 2).
- Baris metrik muncul di CSV.

### Menguji re-replication

Setelah client jadi: jalankan master dan minimal 3 data node, upload file dengan RF 2, lalu matikan satu data node dengan `Ctrl+C`. Di log master harus muncul `PEMULIHAN SELESAI` dengan jumlah chunk lebih dari 0. Sampai sekarang kode re-replication baru teruji dengan hasil `0 chunk`, jadi ini ujian pertamanya. Kabari Fasha kalau hasilnya tidak sesuai.

---

## Tugas Fajar: Eksperimen dan laporan

Folder: `experiments/` dan `docs/`.

### 1. Skrip eksperimen (`experiments/`)

Jalankan kombinasi: strategi (3) x RF (1, 2, 3) x chunk size (1, 4, 8 MB), dengan beban 100 file @ 50 MB. Saat uji skrip, pakai skala kecil dulu (misalnya 10 file @ 5 MB). Skrip memanggil client CLI Azhar dan menyimpan hasil ke `experiments/results/`. Untuk Random, set seed tetap (`random.seed(42)`) agar eksperimen bisa diulang.

Pengujian skala besar di Docker dijalankan di laptop Fasha (Docker hanya ada di sana). Skrip yang sama harus bisa jalan di kedua lingkungan, dan hasilnya dibagikan lewat Git sebagai CSV dan log.

### 2. Metrik

| Metrik | Cara hitung |
|---|---|
| Speedup | `S = T_sekuensial / T_paralel` |
| Efficiency | `E = S / P` (P = jumlah node) |
| Throughput | MB/s dan file/detik dari CSV client |
| Latency | Rata-rata waktu per chunk |
| Keseimbangan beban | Standar deviasi jumlah chunk per node |
| Waktu deteksi | Node dimatikan sampai master mendeteksi |
| Waktu pemulihan | Dari log master: `waktu pemulihan = ... detik` |
| Scalability | Ulangi dengan 2, 4, 8 node |

Catatan: master belum punya endpoint statistik. Untuk sementara, hitung chunk per node dengan menghitung file di `data/<node_id>/`. Kalau butuh endpoint, minta ke Fasha. Waktu pemulihan di log master dihitung dari saat node terdeteksi mati, jadi catat juga waktu saat node dimatikan untuk mendapat waktu deteksi.

### 3. Grafik dan analisis

Gunakan matplotlib:

- Throughput vs strategi
- Standar deviasi beban vs strategi
- Waktu pemulihan vs RF dan chunk size
- Scalability (throughput vs jumlah node)

Tulis interpretasi hasil dan bandingkan dengan teori. Dengan hanya 3 node, perbedaan antar strategi bisa kecil, jadi jalankan juga dengan 5 dan 8 node.

### 4. Laporan dan video

Laporan format IEEE, 6 bab: Pendahuluan, Kajian Teori, Metodologi dan Arsitektur, Implementasi, Pengujian dan Analisis Performansi, Kesimpulan dan Saran. Bab 1 sampai 3 bisa mulai sekarang tanpa menunggu kode. Video demo maksimal 10 menit. Simpan semuanya di `docs/`.

Di akhir proyek, Fajar juga menulis README final (cara run, dependensi, topologi).

### Definisi selesai

- Seluruh kombinasi eksperimen menghasilkan CSV dan grafik.
- Laporan 6 bab lengkap, video demo selesai.

---

## Tugas Fasha: Master dan deployment

- Selesai: master, tiga strategi penempatan, heartbeat, deteksi node mati, re-replication, data node dasar.
- Berikutnya: `Dockerfile` dan `docker-compose.yml` di `deploy/` (1 master + 3 sampai 8 data node), pengujian skala besar di Docker, bonus Kubernetes (kind), review dan merge Pull Request.
- Kalau ada permintaan perubahan di master atau `.proto` dari Azhar atau Fajar, Fasha yang memutuskan dan mengabari grup.

## Alur kerja harian

1. `git pull origin main`
2. Buat atau pindah ke branch tugas (`nama/tugas`)
3. Kerja, commit kecil, push
4. Buka Pull Request, minta satu teman me-review, lalu merge
5. Perbarui bagian **Status** di file ini kalau ada yang selesai