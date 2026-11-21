import argparse
import csv
import json
import os
import socket
from typing import Dict, List, Any

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# Konfigurasi default
DATA_DIR = "data"
METRICS_CSV = os.path.join("experiments", "results", "client_metrics.csv")
DEFAULT_NODES = [
    {"node_id": "node1", "address": "localhost:50052"},
    {"node_id": "node2", "address": "localhost:50053"},
    {"node_id": "node3", "address": "localhost:50054"},
]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SiliFS Monitoring Dashboard</title>
    <style>
        :root {
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
            --primary: #38bdf8;
            --success: #22c55e;
            --danger: #ef4444;
            --border: #334155;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background-color: var(--bg); color: var(--text-main); padding: 24px; }
        .container { max-width: 1200px; margin: 0 auto; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
        h1 { font-size: 24px; font-weight: 700; color: var(--primary); display: flex; align-items: center; gap: 8px; }
        .badge { background: #0369a1; color: #e0f2fe; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
        .pulse { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--success); margin-right: 6px; animation: blink 1.5s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        
        .grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: var(--card-bg); padding: 20px; border-radius: 12px; border: 1px solid var(--border); }
        .stat-label { font-size: 13px; color: var(--text-sub); text-transform: uppercase; font-weight: 600; margin-bottom: 8px; }
        .stat-value { font-size: 28px; font-weight: 700; color: var(--text-main); }
        
        .section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
        .nodes-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 28px; }
        .node-card { background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border); padding: 20px; }
        .node-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .node-name { font-weight: 600; font-size: 16px; }
        .status-pill { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 4px; }
        .status-online { background: rgba(34, 197, 94, 0.15); color: var(--success); border: 1px solid rgba(34, 197, 94, 0.3); }
        .status-offline { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }
        
        .table-container { background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border); overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }
        th { background: rgba(255, 255, 255, 0.03); color: var(--text-sub); font-weight: 600; padding: 12px 16px; border-bottom: 1px solid var(--border); }
        td { padding: 12px 16px; border-bottom: 1px solid var(--border); color: var(--text-main); }
        tr:last-child td { border-bottom: none; }
        .tag-op { font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; }
        .tag-upload { background: #0284c7; color: #fff; }
        .tag-download { background: #7c3aed; color: #fff; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>SiliFS Cluster Monitor <span class="badge">Live</span></h1>
            <div>
                <span class="pulse"></span><span style="font-size: 13px; color: var(--text-sub);" id="refresh-time">Memperbarui...</span>
            </div>
        </header>

        <div class="grid-stats">
            <div class="stat-card">
                <div class="stat-label">Total Data Nodes</div>
                <div class="stat-value" id="total-nodes">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Node Aktif / Mati</div>
                <div class="stat-value" id="node-health">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Chunks Tersimpan</div>
                <div class="stat-value" id="total-chunks">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Penyimpanan Terpakai</div>
                <div class="stat-value" id="total-storage">-</div>
            </div>
        </div>

        <div class="section-title">Status Data Nodes</div>
        <div class="nodes-grid" id="nodes-container">
            <!-- Node cards injected here -->
        </div>

        <div class="section-title">Riwayat Operasi Client (client_metrics.csv)</div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Waktu</th>
                        <th>Operasi</th>
                        <th>Nama File</th>
                        <th>Strategi</th>
                        <th>RF</th>
                        <th>Ukuran</th>
                        <th>Durasi</th>
                        <th>Throughput</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="metrics-tbody">
                    <tr><td colspan="9" style="text-align: center; color: var(--text-sub);">Memuat data...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                // Update Overview
                document.getElementById('total-nodes').innerText = data.cluster.total_nodes;
                document.getElementById('node-health').innerHTML = `<span style="color: var(--success);">${data.cluster.alive_nodes}</span> / <span style="color: var(--danger);">${data.cluster.dead_nodes}</span>`;
                document.getElementById('total-chunks').innerText = data.cluster.total_chunks + ' chunk';
                document.getElementById('total-storage').innerText = data.cluster.total_used_mb.toFixed(2) + ' MB';
                
                // Update Nodes
                const container = document.getElementById('nodes-container');
                container.innerHTML = '';
                data.nodes.forEach(n => {
                    const statusClass = n.alive ? 'status-online' : 'status-offline';
                    const statusText = n.alive ? '● ONLINE' : '✖ OFFLINE';
                    const card = `
                        <div class="node-card">
                            <div class="node-header">
                                <span class="node-name">${n.node_id}</span>
                                <span class="status-pill ${statusClass}">${statusText}</span>
                            </div>
                            <div style="font-size: 13px; color: var(--text-sub); margin-bottom: 8px;">Alamat: ${n.address}</div>
                            <div style="font-size: 14px; margin-bottom: 4px;">Chunks: <strong>${n.chunk_count}</strong> chunk</div>
                            <div style="font-size: 14px;">Terpakai: <strong>${n.used_mb.toFixed(2)} MB</strong> / ${n.capacity_mb} MB</div>
                        </div>
                    `;
                    container.innerHTML += card;
                });

                // Update Metrics Table
                const tbody = document.getElementById('metrics-tbody');
                if (data.recent_metrics.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-sub);">Belum ada log operasi.</td></tr>';
                } else {
                    tbody.innerHTML = '';
                    data.recent_metrics.slice(-10).reverse().forEach(m => {
                        const tagClass = m.operation === 'upload' ? 'tag-upload' : 'tag-download';
                        const okText = m.ok === 'True' || m.ok === true ? '<span style="color: var(--success);">✓ SUKSES</span>' : '<span style="color: var(--danger);">✗ GAGAL</span>';
                        tbody.innerHTML += `
                            <tr>
                                <td>${m.timestamp}</td>
                                <td><span class="tag-op ${tagClass}">${m.operation}</span></td>
                                <td>${m.filename}</td>
                                <td>${m.strategy}</td>
                                <td>${m.rf}</td>
                                <td>${m.file_mb} MB</td>
                                <td>${m.duration_s} s</td>
                                <td>${m.throughput_mbps} MB/s</td>
                                <td>${okText}</td>
                            </tr>
                        `;
                    });
                }
                
                document.getElementById('refresh-time').innerText = 'Pembaruan terakhir: ' + new Date().toLocaleTimeString();
            } catch (err) {
                console.error("Gagal mengambil data monitoring:", err);
            }
        }

        fetchStatus();
        setInterval(fetchStatus, 3000);
    </script>
</body>
</html>
"""


def check_node_alive(address: str) -> bool:
    """Mengecek apakah port data node listening via TCP socket."""
    try:
        host, port_str = address.split(":")
        port = int(port_str)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def get_node_stats(node_id: str, data_dir: str, capacity_mb: int = 2048) -> Dict[str, Any]:
    """Menghitung jumlah chunk dan kapasitas disk di direktori node."""
    node_path = os.path.join(data_dir, node_id)
    chunk_count = 0
    used_bytes = 0
    if os.path.exists(node_path):
        for fname in os.listdir(node_path):
            fpath = os.path.join(node_path, fname)
            if os.path.isfile(fpath):
                chunk_count += 1
                used_bytes += os.path.getsize(fpath)
    return {
        "chunk_count": chunk_count,
        "used_bytes": used_bytes,
        "used_mb": used_bytes / (1024 * 1024),
        "capacity_mb": capacity_mb,
    }


def read_recent_metrics(metrics_csv_path: str) -> List[Dict[str, str]]:
    """Membaca baris riwayat dari file CSV metrik."""
    metrics = []
    if os.path.exists(metrics_csv_path):
        try:
            with open(metrics_csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    metrics.append(dict(row))
        except Exception:
            pass
    return metrics


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/status")
def api_status():
    global DATA_DIR, METRICS_CSV, DEFAULT_NODES

    nodes_info = []
    alive_count = 0
    total_chunks = 0
    total_used_bytes = 0

    for node in DEFAULT_NODES:
        nid = node["node_id"]
        addr = node["address"]
        alive = check_node_alive(addr)
        if alive:
            alive_count += 1

        stats = get_node_stats(nid, DATA_DIR)
        total_chunks += stats["chunk_count"]
        total_used_bytes += stats["used_bytes"]

        nodes_info.append({
            "node_id": nid,
            "address": addr,
            "alive": alive,
            "chunk_count": stats["chunk_count"],
            "used_mb": stats["used_mb"],
            "capacity_mb": stats["capacity_mb"],
        })

    dead_count = len(DEFAULT_NODES) - alive_count
    metrics = read_recent_metrics(METRICS_CSV)

    response_data = {
        "cluster": {
            "total_nodes": len(DEFAULT_NODES),
            "alive_nodes": alive_count,
            "dead_nodes": dead_count,
            "total_chunks": total_chunks,
            "total_used_bytes": total_used_bytes,
            "total_used_mb": total_used_bytes / (1024 * 1024),
        },
        "nodes": nodes_info,
        "recent_metrics": metrics,
    }
    return jsonify(response_data)


def main():
    global DATA_DIR, METRICS_CSV
    parser = argparse.ArgumentParser(description="SiliFS Monitoring Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Port web dashboard (default: 8080)")
    parser.add_argument("--host", default="0.0.0.0", help="Host listening (default: 0.0.0.0)")
    parser.add_argument("--data-dir", default="data", help="Direktori chunk data (default: data)")
    parser.add_argument("--metrics-csv", default=os.path.join("experiments", "results", "client_metrics.csv"),
                        help="Path ke file client_metrics.csv")
    args = parser.parse_args()

    DATA_DIR = args.data_dir
    METRICS_CSV = args.metrics_csv

    print(f"==================================================")
    print(f"  SiliFS Monitoring Dashboard Aktif!               ")
    print(f"  Buka di Browser: http://localhost:{args.port}    ")
    print(f"  Data Dir       : {DATA_DIR}                      ")
    print(f"  Metrics CSV    : {METRICS_CSV}                   ")
    print(f"==================================================")

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
