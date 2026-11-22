"""Analisis hasil eksperimen SiliFS dan pembuatan grafik.

Membaca data dari experiments/data/:
- upload_download_<skenario>.csv
- load_balance.csv
- recovery.csv

Menghasilkan:
- experiments/data/summary.csv
- docs/figures/01_throughput_upload.png
- docs/figures/02_standar_deviasi_beban.png
- docs/figures/03_waktu_pemulihan.png
- docs/figures/04_scalability_throughput.png
"""

from pathlib import Path
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "experiments" / "data"
FIG_DIR = ROOT / "docs" / "figures"

STRATEGIES = [
    ("random", "rnd", "Random"),
    ("round_robin", "rr", "Round-Robin"),
    ("capacity_aware", "cap", "Capacity-Aware"),
]
NODE_COUNTS = [3, 5, 8]
RF = 2
CHUNK_MB = 4

COLORS = {
    "random": "#E07A5F",
    "round_robin": "#3D5A80",
    "capacity_aware": "#2A9D8F",
}
MARKERS = {
    "random": "o",
    "round_robin": "s",
    "capacity_aware": "^",
}


def load_summary() -> tuple[pd.DataFrame, list[str]]:
    """Membaca seluruh CSV dan menyusun tabel ringkasan tanpa mengarang data."""
    notes: list[str] = []

    lb_path = DATA_DIR / "load_balance.csv"
    rec_path = DATA_DIR / "recovery.csv"

    lb_df = pd.read_csv(lb_path) if lb_path.exists() else pd.DataFrame()
    rec_df = pd.read_csv(rec_path) if rec_path.exists() else pd.DataFrame()

    if lb_df.empty:
        notes.append("PERINGATAN: load_balance.csv kosong atau tidak ditemukan.")
    if rec_df.empty:
        notes.append("PERINGATAN: recovery.csv kosong atau tidak ditemukan.")

    rows = []
    for n in NODE_COUNTS:
        for strat_key, short, _label in STRATEGIES:
            sk = f"{short}_rf{RF}_c{CHUNK_MB}_n{n}"
            row = {
                "skenario": sk,
                "strategi": strat_key,
                "rf": RF,
                "chunk_mb": CHUNK_MB,
                "nodes": n,
                "upload_count": np.nan,
                "avg_throughput_mbps": np.nan,
                "avg_chunk_latency_ms": np.nan,
                "chunk_mean": np.nan,
                "chunk_std": np.nan,
                "chunk_cv": np.nan,
                "chunk_max_min_diff": np.nan,
                "waktu_deteksi_s": np.nan,
                "waktu_pemulihan_s": np.nan,
                "chunks_dipulihkan": np.nan,
                "chunks_total": np.nan,
            }

            # 1. Upload metrics
            up_path = DATA_DIR / f"upload_download_{sk}.csv"
            if not up_path.exists():
                notes.append(f"PERINGATAN [{sk}]: {up_path.name} tidak ditemukan.")
            else:
                up_df = pd.read_csv(up_path)
                up_ok = up_df[
                    (up_df["operation"].astype(str).str.lower() == "upload")
                    & (up_df["ok"].astype(str).str.lower() == "true")
                ]
                if len(up_ok) < 100:
                    notes.append(
                        f"PERINGATAN [{sk}]: hanya {len(up_ok)} baris upload ok=True (diharapkan 100)."
                    )
                if len(up_ok) > 0:
                    row["upload_count"] = int(len(up_ok))
                    row["avg_throughput_mbps"] = round(float(up_ok["throughput_mbps"].mean()), 4)
                    row["avg_chunk_latency_ms"] = round(float(up_ok["avg_chunk_latency_ms"].mean()), 4)

            # 2. Load balance metrics
            if not lb_df.empty:
                sub_lb = lb_df[lb_df["skenario"] == sk]
                if len(sub_lb) != n:
                    notes.append(
                        f"PERINGATAN [{sk}]: load_balance.csv punya {len(sub_lb)} baris (diharapkan {n})."
                    )
                if len(sub_lb) > 0:
                    counts = sub_lb["chunk_count"].astype(float)
                    mean_val = float(counts.mean())
                    std_val = float(counts.std(ddof=0))
                    row["chunk_mean"] = round(mean_val, 4)
                    row["chunk_std"] = round(std_val, 4)
                    row["chunk_cv"] = round(std_val / mean_val, 6) if mean_val > 0 else np.nan
                    row["chunk_max_min_diff"] = int(counts.max() - counts.min())

            # 3. Recovery metrics
            if not rec_df.empty:
                sub_rec = rec_df[rec_df["skenario"] == sk]
                if sub_rec.empty:
                    notes.append(f"PERINGATAN [{sk}]: tidak ada baris di recovery.csv.")
                else:
                    if len(sub_rec) > 1:
                        notes.append(
                            f"PERINGATAN [{sk}]: ada {len(sub_rec)} baris di recovery.csv, mengambil baris terakhir."
                        )
                    r = sub_rec.iloc[-1]
                    c_total = int(r["chunks_total"])
                    c_rec = int(r["chunks_dipulihkan"])
                    if c_total <= 0:
                        notes.append(
                            f"PERINGATAN [{sk}]: data pemulihan tidak valid ({c_rec}/{c_total} chunk), dikosongkan."
                        )
                    else:
                        row["waktu_deteksi_s"] = round(float(r["waktu_deteksi_s"]), 3)
                        row["waktu_pemulihan_s"] = round(float(r["waktu_pemulihan_s"]), 3)
                        row["chunks_dipulihkan"] = c_rec
                        row["chunks_total"] = c_total

            rows.append(row)

    return pd.DataFrame(rows), notes


def setup_style():
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "legend.fontsize": 9.5,
            "figure.titlesize": 13,
            "axes.grid": True,
            "grid.alpha": 0.3,
            "grid.linestyle": "--",
        }
    )


def plot_grouped_bar(
    df: pd.DataFrame,
    value_col: str,
    title: str,
    ylabel: str,
    out_path: Path,
    fmt: str = "{:.2f}",
):
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    x = np.arange(len(NODE_COUNTS))
    width = 0.25

    for idx, (strat_key, _short, label) in enumerate(STRATEGIES):
        vals = []
        for n in NODE_COUNTS:
            sub = df[(df["nodes"] == n) & (df["strategi"] == strat_key)]
            v = sub[value_col].iloc[0] if not sub.empty else np.nan
            vals.append(v)

        offset = (idx - 1) * width
        plot_vals = [0.0 if pd.isna(v) else float(v) for v in vals]
        bars = ax.bar(
            x + offset,
            plot_vals,
            width,
            label=label,
            color=COLORS[strat_key],
            edgecolor="white",
            linewidth=0.7,
        )

        for bar, orig_v in zip(bars, vals):
            if pd.isna(orig_v):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    0.02,
                    "N/A",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="#666666",
                )
            else:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    fmt.format(orig_v),
                    ha="center",
                    va="bottom",
                    fontsize=8.5,
                    fontweight="normal",
                )

    ax.set_title(title, pad=12)
    ax.set_xlabel("Jumlah Data Node")
    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{n} Node" for n in NODE_COUNTS])
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    valid_vals = df[value_col].dropna()
    if not valid_vals.empty:
        ax.set_ylim(0, float(valid_vals.max()) * 1.24)

    ax.legend(title="Strategi Penempatan", frameon=True, loc="upper right", ncol=3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_scalability(df: pd.DataFrame, out_path: Path):
    fig, ax = plt.subplots(figsize=(8.5, 5.0))

    for strat_key, _short, label in STRATEGIES:
        sub = df[df["strategi"] == strat_key].sort_values("nodes")
        valid = sub.dropna(subset=["avg_throughput_mbps"])
        if valid.empty:
            continue
        ax.plot(
            valid["nodes"],
            valid["avg_throughput_mbps"],
            marker=MARKERS[strat_key],
            linewidth=2.2,
            markersize=7.5,
            label=label,
            color=COLORS[strat_key],
        )
        label_offset = {"round_robin": 9, "random": 9, "capacity_aware": -14}
        for _, r in valid.iterrows():
            dy = label_offset.get(strat_key, 8)
            if strat_key == "random" and int(r["nodes"]) == 8:
                dy = 9
            elif strat_key == "random" and int(r["nodes"]) == 3:
                dy = 9
            ax.annotate(
                f"{r['avg_throughput_mbps']:.1f}",
                (r["nodes"], r["avg_throughput_mbps"]),
                textcoords="offset points",
                xytext=(0, dy),
                ha="center",
                fontsize=8.5,
                color=COLORS[strat_key],
                fontweight="normal",
            )

    ax.set_title(
        "Skalabilitas: Throughput Upload terhadap Jumlah Data Node (RF=2, Chunk 4 MB)",
        pad=12,
    )
    ax.set_xlabel("Jumlah Data Node")
    ax.set_ylabel("Rata-rata Throughput Upload (MB/s)")
    ax.set_xticks(NODE_COUNTS)
    ax.set_xticklabels([f"{n} Node" for n in NODE_COUNTS])
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    valid_vals = df["avg_throughput_mbps"].dropna()
    if not valid_vals.empty:
        ymin = max(0, float(valid_vals.min()) * 0.85)
        ymax = float(valid_vals.max()) * 1.12
        ax.set_ylim(ymin, ymax)

    ax.legend(title="Strategi Penempatan", frameon=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> int:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    setup_style()

    summary_df, notes = load_summary()
    out_csv = DATA_DIR / "summary.csv"
    summary_df.to_csv(out_csv, index=False)

    plot_grouped_bar(
        summary_df,
        "avg_throughput_mbps",
        "Perbandingan Throughput Upload per Strategi dan Jumlah Node (RF=2, Chunk 4 MB)",
        "Rata-rata Throughput Upload (MB/s)",
        FIG_DIR / "01_throughput_upload.png",
        fmt="{:.1f}",
    )
    plot_grouped_bar(
        summary_df,
        "chunk_std",
        "Perbandingan Standar Deviasi Beban Chunk antar Node (RF=2, Chunk 4 MB)",
        "Standar Deviasi Jumlah Chunk (chunk)",
        FIG_DIR / "02_standar_deviasi_beban.png",
        fmt="{:.2f}",
    )
    plot_grouped_bar(
        summary_df,
        "waktu_pemulihan_s",
        "Perbandingan Waktu Pemulihan saat 1 Node Mati (RF=2, Chunk 4 MB)",
        "Waktu Pemulihan (detik)",
        FIG_DIR / "03_waktu_pemulihan.png",
        fmt="{:.1f}",
    )
    plot_scalability(summary_df, FIG_DIR / "04_scalability_throughput.png")

    print(f"Ringkasan disimpan ke: {out_csv}")
    print(f"Grafik disimpan ke:    {FIG_DIR}")
    print()
    print(summary_df.to_string(index=False))

    if notes:
        print("\nCatatan validasi:")
        for note in notes:
            print(f"  - {note}")
    else:
        print("\nValidasi: seluruh 9 skenario lengkap dan valid.")
    return 0


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=UserWarning)
    sys.exit(main())
