# Deployment SiliFS di Kubernetes (`kind`)

> **Status**: **Teruji end-to-end** pada `kind v0.33.0` (`kindest/node:v1.37.0`) dengan `silifs:latest` (23 November 2026). Seluruh 4 pod berjalan, upload/download 50 MB menghasilkan SHA-256 identik, self-healing `kubectl delete pod datanode-1` berhasil, scaling `StatefulSet` ke 5 replika berhasil, dan cluster dibersihkan kembali dengan `kind delete cluster --name silifs`.

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

## Hasil Uji Nyata (`kind v0.33.0`)

1. **Deploy 4 Pod (`master` + 3 `datanode`) & Registrasi**:
   ```text
   NAME                      READY   STATUS    RESTARTS   AGE   IP            NODE
   datanode-0                1/1     Running   0          22s   10.244.0.7    silifs-control-plane
   datanode-1                1/1     Running   0          10s   10.244.0.9    silifs-control-plane
   datanode-2                1/1     Running   0          5s    10.244.0.11   silifs-control-plane
   master-6f48f59dbc-tflwn   1/1     Running   0          23s   10.244.0.5    silifs-control-plane

   10:58:34.297 [master] master berjalan di port 50051
   10:58:48.928 [master] node terdaftar: datanode-0 (datanode-0.datanode:50052)
   10:58:53.551 [master] node terdaftar: datanode-1 (datanode-1.datanode:50052)
   10:58:58.423 [master] node terdaftar: datanode-2 (datanode-2.datanode:50052)
   ```

2. **Upload & Download 50 MB + Verifikasi SHA-256 (`client-job.yaml`)**:
   ```text
   4a66d1c44c3b19e267a5bb207288ef8dc7cac1a5178a9a7a7a3e0bd9ae85476c  /tmp/test50.bin
   Upload BERHASIL!   (50.00 MB, 13 chunk, 4.1331 s, 12.10 MB/s)
   Download BERHASIL! (50.00 MB, 13 chunk, 3.7276 s, 13.41 MB/s)
   4a66d1c44c3b19e267a5bb207288ef8dc7cac1a5178a9a7a7a3e0bd9ae85476c  /tmp/hasil50.bin
   SHA256 IDENTIK
   ```

3. **Self-Healing `kubectl delete pod datanode-1`**:
   - Pod `datanode-1` otomatis dibuat ulang oleh `StatefulSet` (`1/1 Running` dalam hitungan detik dengan PVC yang sama) dan mendaftar ulang ke master:
     `11:00:30.775 [master] node terdaftar: datanode-1 (datanode-1.datanode:50052)`.
   - Catatan jujur: karena restart pod lebih cepat dari `HEARTBEAT_TIMEOUT = 30 s` (dan saat uji scale-down 3→2 dengan jeda 38 s, `terminationGracePeriodSeconds` bawaan pod sebesar 30 s membuat total waktu henti belum melampaui `30 s grace + 30 s timeout`), log `NODE MATI terdeteksi` tidak terpicu pada durasi tunggu singkat tersebut; pemulihan re-replication sendiri sudah teruji penuh di Docker Compose.

4. **Scaling `StatefulSet` ke 5 Replika (`kubectl scale statefulset datanode --replicas=5`)**:
   ```text
   NAME                      READY   STATUS      RESTARTS   AGE
   datanode-0                1/1     Running     0          2m48s
   datanode-1                1/1     Running     0          54s
   datanode-2                1/1     Running     0          14s
   datanode-3                1/1     Running     0          14s
   datanode-4                1/1     Running     0          9s
   master-6f48f59dbc-tflwn   1/1     Running     0          2m49s

   11:01:10.216 [master] node terdaftar: datanode-2 (datanode-2.datanode:50052)
   11:01:15.112 [master] node terdaftar: datanode-3 (datanode-3.datanode:50052)
   11:01:19.730 [master] node terdaftar: datanode-4 (datanode-4.datanode:50052)
   ```

5. **Pembersihan**: `kind delete cluster --name silifs` selesai (`Deleted nodes: ["silifs-control-plane"]`).

## Batasan

- Cluster `kind` berjalan di dalam container Docker pada satu laptop, sehingga PVC bawaan (`standard` / `local-path-provisioner`) tetap berbagi disk fisik yang sama dengan host.
- Deployment Kubernetes ini ditujukan sebagai bukti fungsionalitas (*deployment*, *fault tolerance* pod, dan *scaling* StatefulSet), **bukan** untuk pengukuran performa throughput/pemulihan.
- Catatan khusus pengujian `kubectl delete pod datanode-1`: karena `StatefulSet` otomatis membuat ulang `datanode-1` dengan PVC yang sama (chunk lama masih ada di PVC), master hanya akan memicu pemulihan jika waktu restart pod melebihi `HEARTBEAT_TIMEOUT` (`30 s`) atau jika pengujian kegagalan dilakukan dengan `kubectl scale statefulset datanode --replicas=2` / mematikan proses sementara.
