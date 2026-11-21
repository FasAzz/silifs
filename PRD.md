# PRD: SiliFS

## 1. Ringkasan

**Judul:** Perbandingan Strategi Penempatan Replika (Random, Round-Robin, dan Capacity-Aware) terhadap Keseimbangan Beban dan Waktu Pemulihan pada Sistem Berkas Terdistribusi

**Masalah:** Pada distributed file system, pemilihan node untuk menyimpan replika memengaruhi seberapa merata beban dan seberapa cepat sistem pulih saat node gagal.

**Tujuan:** Membangun mini DFS dan membandingkan tiga strategi penempatan replika secara eksperimental.

## 2. Ruang lingkup

**Termasuk:** partisi file menjadi chunk, replikasi, tiga strategi penempatan, heartbeat dan deteksi node mati, re-replication, upload/download, pengujian performa dan fault tolerance, deployment Docker.

**Bonus:** Kubernetes (kind), monitoring dashboard.

**Tidak termasuk:** autentikasi, enkripsi, direktori bertingkat, penghapusan file, master berreplika (single master diterima).

## 3. Arsitektur

| Komponen | Fungsi |
|---|---|
| Master | Metadata (file, chunk, lokasi), penempatan replika, heartbeat, re-replication |
| Data node | Menyimpan chunk, melapor sisa disk, menyalin chunk ke node lain |
| Client | Memecah file, upload, download, mencatat metrik |
| Communication layer | gRPC (`proto/silifs.proto`) |
| Storage | File per chunk di `data/<node_id>/` (container volume di Docker) |

Alur upload: client meminta alokasi ke master, mengirim tiap chunk ke semua replika, lalu `CommitFile`.
Alur download: client meminta lokasi, membaca dari replika hidup (fallback ke replika lain), menggabungkan chunk.
Alur pemulihan: master mendeteksi node mati lewat heartbeat, mencari chunk yang kurang replika, lalu menyuruh node sumber menyalin ke node tujuan.

## 4. Strategi penempatan

| Strategi | Cara kerja |
|---|---|
| Random | Memilih RF node secara acak (seed tetap untuk eksperimen) |
| Round-Robin | Memilih node berurutan, titik awal bergeser tiap chunk |
| Capacity-Aware | Memilih RF node dengan sisa disk terbanyak |

## 5. Persyaratan fungsional

- FR1: Minimal 1 master dan 3 data node.
- FR2: File dipecah menjadi chunk dengan ukuran dapat diatur (1, 4, 8 MB).
- FR3: Replication factor dapat diatur (1, 2, 3).
- FR4: Strategi dapat dipilih per upload.
- FR5: Download tetap berhasil saat 1 node mati (RF >= 2).
- FR6: Master memulihkan replika yang hilang secara otomatis.
- FR7: Integritas chunk diverifikasi dengan SHA-256.
- FR8: Pengujian upload/download 100 file @ 50 MB.

## 6. Eksperimen dan metrik

Variabel: strategi (3) x RF (1, 2, 3) x chunk size (1, 4, 8 MB), jumlah node (2, 4, 8; maksimum sesuai kemampuan laptop, jelaskan batasannya di laporan).

| Metrik | Definisi |
|---|---|
| Speedup | S = T_sekuensial / T_paralel |
| Efficiency | E = S / P |
| Throughput | MB/s dan file/detik |
| Latency | Rata-rata waktu per chunk |
| Keseimbangan beban | Standar deviasi jumlah chunk per node |
| Waktu deteksi | Node dimatikan sampai master mendeteksi |
| Waktu pemulihan | Deteksi sampai semua chunk kembali ke RF |
| Fault tolerance | Matikan 1 node saat eksekusi, data tetap dapat diakses |

## 7. Kriteria selesai

- [ ] Upload 50 MB lalu download menghasilkan hash SHA-256 identik.
- [ ] Download berhasil saat 1 node dimatikan.
- [ ] Log master menampilkan `PEMULIHAN SELESAI` dengan jumlah chunk > 0.
- [ ] Seluruh kombinasi eksperimen menghasilkan CSV dan grafik.
- [ ] Sistem berjalan dengan `docker compose up`.
- [ ] Laporan IEEE 6 bab, README final, dan video demo maksimal 10 menit.

## 8. Rubrik dosen (acuan prioritas)

| Komponen | Bobot |
|---|---|
| Tema dan desain | 15% |
| Implementasi sistem | 25% |
| Kinerja dan pengujian | 25% |
| Analisis ilmiah | 15% |
| Laporan dan presentasi | 20% |
| Bonus (monitoring, Docker/Kubernetes) | +5% |

## 9. Risiko

| Risiko | Penanganan |
|---|---|
| Docker hanya ada di laptop Fasha | Pengembangan tanpa Docker, pengujian final di laptop Fasha |
| Batas pesan gRPC 4 MB | Semua channel dan server memakai batas 16 MB |
| Resource laptop terbatas untuk 8+ node | Uji besar di Compose, jelaskan batasannya di laporan |
| Perbedaan antar strategi kecil dengan 3 node | Jalankan juga dengan 5 dan 8 node |
| Waktu 1 minggu | Kerja paralel per komponen, cek deadline di Classroom |