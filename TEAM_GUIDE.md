# Panduan Tim

## Tim

| Anggota | Peran | Branch |
|---|---|---|
| Fasha | Master, strategi penempatan, heartbeat, re-replication, Docker, Kubernetes | `fasha` |
| Azhar | Client, penyempurnaan data node, metrik CSV, monitoring | `azhar` |
| Fajar | Skrip eksperimen, grafik, laporan, README final, video demo | `fajar/...` |

## Status

- [x] `proto/silifs.proto`: kontrak gRPC (terkunci)
- [x] `master/placement.py`: 3 strategi penempatan
- [x] `master/server.py`: registrasi, heartbeat, alokasi, commit, deteksi node mati, re-replication
- [x] `datanode/server.py`: checksum SHA-256 dan batas kapasitas disk (Azhar)
- [x] `client/`: CLI upload dan download, metrik ke CSV (Azhar)
- [x] `monitoring/`: dashboard Flask (Azhar)
- [x] Uji re-replication end-to-end: 3 node 8/8 chunk (0,295 s), 5 node 3/3 chunk (0,090 s)
- [x] `deploy/`: Dockerfile, Compose 3/5/8 node, service `client` (Fasha)
- [x] Hasil eksperimen awal: `experiments/data/` (rr, RF 2, chunk 4 MB, 8 node)
- [x] `experiments/`: skrip eksperimen otomatis (`run_experiment.ps1` termasuk mode `-Hetero` dan `-Repeat`) dan analisis (`analyze.py`) beserta 6 grafik di `docs/figures/` (Fajar, Fasha)
- [x] Eksperimen skala penuh di Docker: 9 skenario utama (homogen, 100 file @ 50 MB, `HEARTBEAT_TIMEOUT = 30 s`), 3 skenario kapasitas heterogen (`node1=1 GB`, `node2..5=8 GB`), dan pengulangan 3x untuk `n=3` (`experiments/data/`, `docs/hasil_eksperimen.md`)
- [ ] Variasi RF (1, 2, 3) dan chunk size (1, 4, 8 MB) dengan beban kecil
- [ ] Laporan IEEE 6 bab, video demo maksimal 10 menit, README final (Fajar)
- [ ] Bonus: Kubernetes (`kind`) — manifest `deploy/k8s/` sudah disiapkan (belum diuji, menunggu instalasi `kind`) dan integrasi dashboard (Fasha dan Azhar)

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

Log yang normal: master mencetak `node terdaftar: ...`. Kalau satu data node dihentikan (`Ctrl+C`), sekitar 10 sampai 12 detik kemudian master mencetak `NODE MATI terdeteksi`, lalu `PEMULIHAN SELESAI`.

Contoh upload dan download:

```powershell
python -m client.cli upload tes50.bin --rf 2 --chunk-mb 4 --strategy round_robin
python -m client.cli download tes50.bin --out hasil.bin
```

Membuat file uji acak 50 MB:

```powershell
python -c "import os; open('tes50.bin','wb').write(os.urandom(50*1024*1024))"
```

## Menjalankan dengan Docker (hanya di laptop Fasha)

```powershell
docker compose -f deploy/dockerCompose.yml up -d
docker compose -f deploy/dockerCompose.yml run --rm client upload /work/<file> --rf 2 --chunk-mb 4 --strategy round_robin
docker compose -f deploy/dockerCompose.yml run --rm client download <nama_file> --out /work/hasil.bin
docker compose -f deploy/dockerCompose.yml logs master
docker compose -f deploy/dockerCompose.yml down -v
```

- Gunakan `dockerCompose.5.yml` atau `dockerCompose.8.yml` untuk 5 atau 8 node. Nama file memakai huruf besar `C`.
- Wajib `down -v` sebelum ganti konfigurasi (strategi, RF, chunk size, jumlah node), supaya chunk lama tidak tercampur dan angka sebaran beban tidak salah.
- Simulasi node mati: `docker stop silifs-datanode2`, hidupkan lagi dengan `docker start silifs-datanode2`.
- Hitung chunk per node: `docker exec silifs-datanode1 sh -c "ls /app/data/node1 | wc -l"`.
- Client berjalan di dalam network Docker (alamat `datanodeN:50052` hanya dikenal di sana). Metrik tersimpan di `experiments/results/client_metrics.csv` di laptop Fasha.
- Menjalankan eksperimen otomatis dengan skrip PowerShell:
  ```powershell
  # 9 skenario utama (homogen: 3, 5, 8 node x 3 strategi)
  .\experiments\run_experiment.ps1 -Force

  # Skenario kapasitas heterogen (5 node: node1=1024 MB, node2..5=8192 MB)
  .\experiments\run_experiment.ps1 -Hetero -Force

  # Pengulangan tambahan (_run2 dan _run3) tanpa menimpa data utama
  .\experiments\run_experiment.ps1 -Nodes 3 -Repeat 2 -StartRun 2 -Force

  # Analisis CSV dan pembuatan grafik
  .venv\Scripts\python.exe experiments\analyze.py
  ```

## Hasil eksperimen

- `experiments/results/`: tempat kerja lokal, di-ignore Git.
- `experiments/data/`: hasil final yang dibagikan lewat Git (CSV dan `logs/`), di-commit dengan sengaja setelah satu rangkaian eksperimen selesai.
- Beri nama file per skenario, contoh `upload_download_rr_rf2_c4_n8.csv`.

## Aturan kerja

- Fasha memakai satu branch kerja `fasha`. Azhar dan Fajar bebas memakai satu branch per orang atau `nama/tugas`, asal konsisten.
- Jangan push langsung ke `main`. Merge lewat Pull Request, satu PR untuk satu hal.
- Untuk branch yang dipakai terus (misalnya `fasha`): jangan klik Delete branch setelah merge, lalu tarik `main` lagi dengan `git pull origin main`.
- Sebelum mulai kerja: `git pull origin main`.
- Commit kecil dan sering, pesan commit jelas.
- Jangan meng-commit file uji (`*.bin`) atau hasil lokal (`experiments/results/*.csv`). Stage file satu per satu, bukan "stage all".
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

## Tugas Azhar: Client dan data node (selesai)

Folder: `client/`, `datanode/server.py`, `monitoring/`.

### Hasil

- Client CLI: `upload` dan `download` dengan opsi `--rf`, `--chunk-mb` (1, 4, 8), `--strategy`, `--filename`, `--master`, `--metrics-csv`.
- Checksum SHA-256 di client dan data node, batas kapasitas disk.
- Metrik ke CSV dengan kolom:
  ```
  timestamp,operation,filename,strategy,rf,chunk_mb,file_mb,duration_s,throughput_mbps,chunks,avg_chunk_latency_ms,ok
  ```
- Dashboard monitoring Flask di `monitoring/`.

### Tugas lanjutan

- Bantu Fajar kalau skrip eksperimen butuh perubahan di client (misalnya opsi tambahan atau format CSV).
- Dashboard: kalau butuh endpoint statistik di master (daftar node, status hidup atau mati, jumlah chunk), minta ke Fasha.

---

## Tugas Fajar: Eksperimen dan laporan

Folder: `experiments/` dan `docs/`.

### 1. Skrip eksperimen (`experiments/`)

Kombinasi: strategi (3) x RF (1, 2, 3) x chunk size (1, 4, 8 MB) x ukuran cluster (3, 5, 8 node). Prioritas:

1. Subset utama dengan beban penuh (100 file @ 50 MB): RF 2, chunk 4 MB, 3 strategi x 3 ukuran cluster = 9 skenario.
2. Variasi RF dan chunk size dengan beban kecil (misalnya 10 file @ 10 MB).

Skrip memanggil client CLI dan menyimpan hasil ke `experiments/results/`. Untuk Random, set seed tetap (`random.seed(42)`) agar eksperimen bisa diulang.

Pengujian di Docker dijalankan di laptop Fasha. Alurnya: Fajar menulis dan menguji skrip tanpa Docker, lalu Fasha menjalankannya di Docker dan membagikan hasil final lewat `experiments/data/`. Setiap skenario harus mulai dari kondisi bersih (di Docker: `down -v` lalu `up`).

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
| Scalability | Ulangi dengan 3, 5, 8 node |

Catatan:
- Master belum punya endpoint statistik. Tanpa Docker, hitung chunk per node dengan menghitung file di `data/<node_id>/`. Di Docker, chunk ada di `/app/data/<node_id>` di dalam container.
- Waktu pemulihan di log master dihitung dari saat node terdeteksi mati. Catat juga waktu saat node dimatikan untuk mendapat waktu deteksi (sekitar 10 sampai 12 detik, sesuai timeout heartbeat).
- Satu file kecil memberi sebaran yang tidak rata (efek putaran round-robin). Ukur keseimbangan dengan beban penuh, bukan satu file.
- Ulangi tiap konfigurasi beberapa kali dan ambil rata-rata.

### 3. Grafik dan analisis

Gunakan matplotlib:

- Throughput vs strategi
- Standar deviasi beban vs strategi
- Waktu pemulihan vs RF dan chunk size
- Scalability (throughput vs jumlah node)

Tulis interpretasi hasil dan bandingkan dengan teori. Dengan 3 node, perbedaan antar strategi bisa kecil, jadi bandingkan dengan 5 dan 8 node.

Batasan yang perlu disebut di laporan: semua node berjalan di satu laptop, jadi latensi jaringan sangat kecil dan angka tidak bisa disamakan dengan klaster fisik. Sebutkan juga spesifikasi laptop (CPU, RAM, versi Docker).

### 4. Laporan dan video

Laporan format IEEE, 6 bab: Pendahuluan, Kajian Teori, Metodologi dan Arsitektur, Implementasi, Pengujian dan Analisis Performansi, Kesimpulan dan Saran. Bab 1 sampai 3 bisa mulai sekarang tanpa menunggu kode. Video demo maksimal 10 menit. Simpan semuanya di `docs/`.

Di akhir proyek, Fajar juga menulis README final (cara run, dependensi, topologi).

### Definisi selesai

- Seluruh skenario prioritas menghasilkan CSV dan grafik.
- Laporan 6 bab lengkap, video demo selesai.

---

## Tugas Fasha: Master dan deployment

- Selesai: master, tiga strategi penempatan, heartbeat, deteksi node mati, re-replication (teruji end-to-end), Docker (Compose 3/5/8 node dan service `client`).
- Berikutnya:
  1. Skrip eksperimen otomatis (PowerShell) dan menjalankannya di Docker, lalu membagikan hasil lewat `experiments/data/`.
  2. Kubernetes (kind) sebagai bonus, kalau waktu masih ada.
  3. Review dan merge Pull Request.
- Kalau ada permintaan perubahan di master atau `.proto` dari Azhar atau Fajar, Fasha yang memutuskan dan mengabari grup.

## Alur kerja harian

1. `git pull origin main`
2. Pindah ke branch kerja masing-masing
3. Kerja, commit kecil, push
4. Buka Pull Request, minta satu teman me-review, lalu merge
5. Tarik `main` lagi ke branch kerja (`git pull origin main`)
6. Perbarui bagian **Status** di file ini kalau ada yang selesai