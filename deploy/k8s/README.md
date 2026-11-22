# Deployment SiliFS di Kubernetes (`kind`)

> **Status**: Manifest sudah disiapkan, **belum diuji secara langsung** karena `kind` belum terpasang di mesin ini (`kubectl` sudah terpasang melalui Docker Desktop). Hasil uji dan potongan log akan ditambahkan setelah pengujian dijalankan.

## Struktur Manifest

- `master.yaml`: `Deployment` (1 replika) dan `Service` ClusterIP `master` pada port `50051`.
- `datanode.yaml`: Headless `Service` `datanode` (`clusterIP: None`) dan `StatefulSet` `datanode` (3 replika) dengan:
  - Identitas node diambil dari nama pod (`POD_NAME` via `fieldRef: metadata.name`),
  - Alamat advertise `$(POD_NAME).datanode:50052`,
  - Koneksi ke `master:50051`,
  - Penyimpanan persisten `volumeClaimTemplates` sebesar `2Gi` per pod pada `/app/data`,
  - `imagePullPolicy: Never` (memakai image lokal `silifs:latest`).
- `client-job.yaml`: Contoh `Job` uji asap (*smoke test*) upload 50 MB, download, dan verifikasi kesamaan SHA-256.

## Prasyarat

1. Pastikan cluster Docker Compose tidak sedang berjalan (`docker compose -f deploy/dockerCompose.8.yml down -v`).
2. Pastikan image `silifs:latest` sudah dibangun (`docker compose -f deploy/dockerCompose.yml build`).
3. Pasang `kind` jika belum ada (mis. `winget install Kubernetes.kind`).

## Langkah Menjalankan dan Menguji

```powershell
# 1. Buat cluster kind dan muat image lokal
kind create cluster --name silifs
kind load docker-image silifs:latest --name silifs

# 2. Terapkan manifest master dan data node
kubectl apply -f deploy/k8s/master.yaml
kubectl apply -f deploy/k8s/datanode.yaml

# 3. Verifikasi 4 pod Running (1 master + 3 datanode) dan 3 node terdaftar
kubectl get pods -o wide
kubectl logs deployment/master

# 4. Uji upload 50 MB + download dengan verifikasi SHA-256
kubectl apply -f deploy/k8s/client-job.yaml
kubectl wait --for=condition=complete job/silifs-smoke-test --timeout=180s
kubectl logs job/silifs-smoke-test

# 5. Uji fault tolerance: hapus pod datanode-1 dan cek deteksi + pemulihan di log master
kubectl delete pod datanode-1
# Tunggu ~35-45 detik (HEARTBEAT_TIMEOUT=30 s), lalu cek log master:
kubectl logs deployment/master --tail=30

# 6. Uji scaling StatefulSet ke 5 data node
kubectl scale statefulset datanode --replicas=5
kubectl get pods -w
kubectl logs deployment/master --tail=20

# 7. Bersihkan cluster setelah selesai
kind delete cluster --name silifs
```

## Batasan

- Cluster `kind` berjalan di dalam container Docker pada satu laptop, sehingga PVC bawaan (`standard` / `local-path-provisioner`) tetap berbagi disk fisik yang sama dengan host.
- Deployment Kubernetes ini ditujukan sebagai bukti fungsionalitas (*deployment*, *fault tolerance* pod, dan *scaling* StatefulSet), **bukan** untuk pengukuran performa throughput/pemulihan.
- Catatan khusus pengujian `kubectl delete pod datanode-1`: karena `StatefulSet` otomatis membuat ulang `datanode-1` dengan PVC yang sama (chunk lama masih ada di PVC), master hanya akan memicu pemulihan jika waktu restart pod melebihi `HEARTBEAT_TIMEOUT` (`30 s`) atau jika pengujian kegagalan dilakukan dengan `kubectl scale statefulset datanode --replicas=2` / mematikan proses sementara.
