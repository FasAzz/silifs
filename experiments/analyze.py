"""Analisis hasil eksperimen SiliFS dan pembuatan grafik.

Membaca data dari experiments/data/:
- upload_download_<skenario>.csv
- load_balance.csv
- recovery.csv
- upload_status.csv (opsional, untuk skenario heterogen)
- hetero_capacity.csv (opsional, untuk skenario heterogen)

Menghasilkan:
- experiments/data/summary.csv          (9 skenario utama)
- experiments/data/summary_ulang.csv    (agregasi rata-rata & simpangan baku pengulangan)
- docs/figures/01_throughput_upload.png
- docs/figures/02_standar_deviasi_beban.png
- docs/figures/03_waktu_pemulihan.png   (dengan error bar bila n_runs >= 2)
- docs/figures/04_scalability_throughput.png
- docs/figures/05_hetero_upload_berhasil_gagal.png
- docs/figures/06_hetero_sebaran_chunk.png
- docs/figures/07_latensi_waktu_akses.png
- docs/figures/08_speedup_efficiency.png
- experiments/data/speedup_efficiency.csv
"""

from pathlib import Path
import re
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


def compute_single_scenario(
    sk: str,
    strat_key: str,
    n: int,
    lb_df: pd.DataFrame,
    rec_df: pd.DataFrame,
    notes: list[str],
) -> dict:
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

    return row


def load_summary() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Membaca seluruh CSV dan menyusun summary.csv (9 utama) serta summary_ulang.csv."""
    notes: list[str] = []

    lb_path = DATA_DIR / "load_balance.csv"
    rec_path = DATA_DIR / "recovery.csv"

    lb_df = pd.read_csv(lb_path) if lb_path.exists() else pd.DataFrame()
    rec_df = pd.read_csv(rec_path) if rec_path.exists() else pd.DataFrame()

    if lb_df.empty:
        notes.append("PERINGATAN: load_balance.csv kosong atau tidak ditemukan.")
    if rec_df.empty:
        notes.append("PERINGATAN: recovery.csv kosong atau tidak ditemukan.")

    # 1. 9 skenario utama
    base_rows = []
    for n in NODE_COUNTS:
        for strat_key, short, _label in STRATEGIES:
            sk = f"{short}_rf{RF}_c{CHUNK_MB}_n{n}"
            base_rows.append(compute_single_scenario(sk, strat_key, n, lb_df, rec_df, notes))
    summary_df = pd.DataFrame(base_rows)

    # 2. Deteksi pengulangan (_run2, _run3, dst.) untuk setiap konfigurasi utama
    all_rec_scenarios = set(rec_df["skenario"].astype(str).tolist()) if not rec_df.empty else set()
    all_up_scenarios = {
        p.stem.replace("upload_download_", "")
        for p in DATA_DIR.glob("upload_download_*.csv")
    }
    all_scenarios = all_rec_scenarios | all_up_scenarios

    repeat_rows = []
    for n in NODE_COUNTS:
        for strat_key, short, _label in STRATEGIES:
            base_sk = f"{short}_rf{RF}_c{CHUNK_MB}_n{n}"
            pat = re.compile(rf"^{re.escape(base_sk)}(?:_run(\d+))?$")
            matched = []
            for sk in sorted(all_scenarios):
                m = pat.match(sk)
                if m:
                    run_idx = int(m.group(1)) if m.group(1) else 1
                    matched.append((run_idx, sk))
            matched.sort(key=lambda x: x[0])

            run_records = []
            for _ridx, sk in matched:
                if sk == base_sk:
                    rec = summary_df[summary_df["skenario"] == base_sk].iloc[0].to_dict()
                else:
                    rec = compute_single_scenario(sk, strat_key, n, lb_df, rec_df, notes)
                run_records.append(rec)

            rdf = pd.DataFrame(run_records)
            valid_rec = rdf.dropna(subset=["waktu_pemulihan_s"])
            valid_det = rdf.dropna(subset=["waktu_deteksi_s"])
            valid_thr = rdf.dropna(subset=["avg_throughput_mbps"])
            n_runs = len(valid_rec)

            def mean_std(series: pd.Series) -> tuple[float, float]:
                if len(series) == 0:
                    return np.nan, np.nan
                m_val = round(float(series.mean()), 3)
                s_val = round(float(series.std(ddof=1)), 3) if len(series) >= 2 else np.nan
                return m_val, s_val

            thr_m, thr_s = mean_std(valid_thr["avg_throughput_mbps"])
            det_m, det_s = mean_std(valid_det["waktu_deteksi_s"])
            rec_m, rec_s = mean_std(valid_rec["waktu_pemulihan_s"])
            chk_m = (
                round(float(valid_rec["chunks_dipulihkan"].mean()), 1)
                if len(valid_rec) > 0
                else np.nan
            )

            repeat_rows.append(
                {
                    "base_skenario": base_sk,
                    "strategi": strat_key,
                    "rf": RF,
                    "chunk_mb": CHUNK_MB,
                    "nodes": n,
                    "n_runs": n_runs,
                    "throughput_mean": thr_m,
                    "throughput_std": thr_s,
                    "waktu_deteksi_mean": det_m,
                    "waktu_deteksi_std": det_s,
                    "waktu_pemulihan_mean": rec_m,
                    "waktu_pemulihan_std": rec_s,
                    "chunks_dipulihkan_mean": chk_m,
                }
            )

    repeat_df = pd.DataFrame(repeat_rows)
    return summary_df, repeat_df, notes


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
    err_col: str | None = None,
    n_runs_col: str | None = None,
):
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    x = np.arange(len(NODE_COUNTS))
    width = 0.25
    max_top = 0.0

    for idx, (strat_key, _short, label) in enumerate(STRATEGIES):
        vals = []
        errs = []
        nruns = []
        for n in NODE_COUNTS:
            sub = df[(df["nodes"] == n) & (df["strategi"] == strat_key)]
            v = sub[value_col].iloc[0] if not sub.empty else np.nan
            e = sub[err_col].iloc[0] if (err_col and not sub.empty) else np.nan
            nr = int(sub[n_runs_col].iloc[0]) if (n_runs_col and not sub.empty) else 1
            vals.append(v)
            errs.append(e)
            nruns.append(nr)

        offset = (idx - 1) * width
        plot_vals = [0.0 if pd.isna(v) else float(v) for v in vals]
        plot_errs = [0.0 if pd.isna(e) else float(e) for e in errs]
        has_any_err = any((not pd.isna(e)) and float(e) > 0 for e in errs)

        bars = ax.bar(
            x + offset,
            plot_vals,
            width,
            yerr=plot_errs if has_any_err else None,
            capsize=4 if has_any_err else 0,
            error_kw={"elinewidth": 1.2, "ecolor": "#333333"} if has_any_err else None,
            label=label,
            color=COLORS[strat_key],
            edgecolor="white",
            linewidth=0.7,
        )

        for bar, orig_v, orig_e, nr in zip(bars, vals, errs, nruns):
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
                top_y = float(orig_v) + (0.0 if pd.isna(orig_e) else float(orig_e))
                max_top = max(max_top, top_y)
                if err_col and not pd.isna(orig_e) and nr >= 2:
                    lbl = f"{fmt.format(orig_v)}\n(±{orig_e:.1f})"
                else:
                    lbl = fmt.format(orig_v)
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    top_y + (max_top * 0.015 if max_top > 0 else 0.2),
                    lbl,
                    ha="center",
                    va="bottom",
                    fontsize=8.0,
                    fontweight="normal",
                )

    ax.set_title(title, pad=12)
    ax.set_xlabel("Jumlah Data Node")
    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    xlabels = []
    for n in NODE_COUNTS:
        if n_runs_col:
            nr_vals = df[df["nodes"] == n][n_runs_col].dropna().unique()
            nr_tag = f" (n={int(nr_vals[0])})" if len(nr_vals) == 1 and int(nr_vals[0]) > 1 else " (n=1)"
            xlabels.append(f"{n} Node{nr_tag}")
        else:
            xlabels.append(f"{n} Node")
    ax.set_xticklabels(xlabels)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if max_top > 0:
        ax.set_ylim(0, max_top * 1.28)

    ax.legend(title="Strategi Penempatan", frameon=True, loc="upper right", ncol=3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_scalability(df: pd.DataFrame, out_path: Path):
    fig, ax = plt.subplots(figsize=(8.5, 5.0))

    label_offset = {"round_robin": 9, "random": 9, "capacity_aware": -14}
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
        for _, r in valid.iterrows():
            dy = label_offset.get(strat_key, 8)
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


def plot_hetero_figures(notes: list[str]):
    """Buat 2 grafik untuk skenario heterogen (upload berhasil/gagal & sebaran chunk per node)."""
    up_stat_path = DATA_DIR / "upload_status.csv"
    het_cap_path = DATA_DIR / "hetero_capacity.csv"

    # Grafik 5: Upload berhasil vs gagal per strategi
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    if not up_stat_path.exists():
        notes.append("PERINGATAN [hetero]: upload_status.csv tidak ditemukan; grafik 05 kosong.")
        ax.text(0.5, 0.5, "Data upload_status.csv tidak tersedia", ha="center", va="center")
    else:
        udf = pd.read_csv(up_stat_path)
        hdf = udf[udf["skenario"].astype(str).str.endswith("_n5_het")]
        x = np.arange(len(STRATEGIES))
        width = 0.34
        ok_vals, fail_vals = [], []
        for strat_key, short, _label in STRATEGIES:
            sk = f"{short}_rf{RF}_c{CHUNK_MB}_n5_het"
            sub = hdf[hdf["skenario"] == sk]
            if sub.empty:
                notes.append(f"PERINGATAN [{sk}]: tidak ditemukan di upload_status.csv.")
                ok_vals.append(np.nan)
                fail_vals.append(np.nan)
            else:
                ok_vals.append(int(sub.iloc[-1]["upload_ok"]))
                fail_vals.append(int(sub.iloc[-1]["upload_gagal"]))

        b_ok = ax.bar(
            x - width / 2,
            [0 if pd.isna(v) else v for v in ok_vals],
            width,
            label="Upload Berhasil",
            color="#2A9D8F",
            edgecolor="white",
        )
        b_fail = ax.bar(
            x + width / 2,
            [0 if pd.isna(v) else v for v in fail_vals],
            width,
            label="Upload Gagal",
            color="#E76F51",
            edgecolor="white",
        )
        for bars, raw in [(b_ok, ok_vals), (b_fail, fail_vals)]:
            for bar, v in zip(bars, raw):
                lbl = "N/A" if pd.isna(v) else str(int(v))
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 1.5,
                    lbl,
                    ha="center",
                    va="bottom",
                    fontsize=9,
                )
        ax.set_xticks(x)
        ax.set_xticklabels([label for _, _, label in STRATEGIES])
        ax.set_ylim(0, 120)
        ax.legend(frameon=True, loc="upper right")

    ax.set_title(
        "Keberhasilan Upload Klaster Heterogen (node1=1 GB, node2–5=8 GB; 100 File)",
        pad=12,
        fontsize=11,
    )
    ax.set_xlabel("Strategi Penempatan")
    ax.set_ylabel("Jumlah File (file)")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "05_hetero_upload_berhasil_gagal.png", dpi=200)
    plt.close(fig)

    # Grafik 6: Sebaran chunk per node (node1..node5) pada klaster heterogen
    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    if not het_cap_path.exists():
        notes.append("PERINGATAN [hetero]: hetero_capacity.csv tidak ditemukan; grafik 06 kosong.")
        ax.text(0.5, 0.5, "Data hetero_capacity.csv tidak tersedia", ha="center", va="center")
    else:
        cdf = pd.read_csv(het_cap_path)
        node_ids = [f"node{i}" for i in range(1, 6)]
        x = np.arange(len(node_ids))
        width = 0.25
        max_c = 0.0

        for idx, (strat_key, short, label) in enumerate(STRATEGIES):
            sk = f"{short}_rf{RF}_c{CHUNK_MB}_n5_het"
            sub = cdf[cdf["skenario"] == sk]
            vals = []
            for nid in node_ids:
                row = sub[sub["node_id"] == nid]
                if row.empty:
                    vals.append(np.nan)
                else:
                    vals.append(int(row.iloc[-1]["chunk_count"]))
            if all(pd.isna(v) for v in vals):
                notes.append(f"PERINGATAN [{sk}]: tidak ditemukan di hetero_capacity.csv.")

            offset = (idx - 1) * width
            bars = ax.bar(
                x + offset,
                [0 if pd.isna(v) else v for v in vals],
                width,
                label=label,
                color=COLORS[strat_key],
                edgecolor="white",
            )
            for bar, v in zip(bars, vals):
                if pd.isna(v):
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        5,
                        "N/A",
                        ha="center",
                        va="bottom",
                        fontsize=8,
                        color="#666666",
                    )
                else:
                    max_c = max(max_c, float(v))
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 8,
                        str(int(v)),
                        ha="center",
                        va="bottom",
                        fontsize=8.2,
                    )

        ax.set_xticks(x)
        ax.set_xticklabels(
            [
                "node1\n(1024 MB)",
                "node2\n(8192 MB)",
                "node3\n(8192 MB)",
                "node4\n(8192 MB)",
                "node5\n(8192 MB)",
            ]
        )
        if max_c > 0:
            ax.set_ylim(0, max_c * 1.24)
        ax.legend(title="Strategi Penempatan", frameon=True, loc="upper left", ncol=3)

    ax.set_title(
        "Sebaran Jumlah Chunk per Node pada Klaster Heterogen (RF=2, Chunk 4 MB)",
        pad=12,
    )
    ax.set_xlabel("Data Node (Kapasitas Virtual)")
    ax.set_ylabel("Jumlah Chunk di Disk (chunk)")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "06_hetero_sebaran_chunk.png", dpi=200)
    plt.close(fig)


def compute_speedup_efficiency(summary_df: pd.DataFrame, repeat_df: pd.DataFrame) -> pd.DataFrame:
    """Hitung Speedup relatif (baseline P=3 node) dan Efficiency untuk upload & pemulihan.

    Catatan: P=3 digunakan sebagai baseline (bukan P=1) karena eksperimen memakai RF=2
    dan membutuhkan minimal 3 node agar re-replication memiliki node target saat 1 node mati.
    Scale factor relatif = P / 3, sehingga:
      - Speedup relatif  S_rel = T_base(P=3) / T(P)
      - Efficiency relatif E_rel = S_rel / (P / 3)
    Untuk waktu pemulihan n=3 digunakan rata-rata 3 run dari summary_ulang.csv.
    """
    rows = []
    for strat_key, _short, _label in STRATEGIES:
        sub_s = summary_df[summary_df["strategi"] == strat_key].set_index("nodes")
        sub_r = repeat_df[repeat_df["strategi"] == strat_key].set_index("nodes")
        if 3 not in sub_s.index or 3 not in sub_r.index:
            continue

        base_up_thr = float(sub_s.loc[3, "avg_throughput_mbps"])
        base_rec_s = float(sub_r.loc[3, "waktu_pemulihan_mean"])

        for n in NODE_COUNTS:
            if n not in sub_s.index or n not in sub_r.index:
                continue
            up_thr = float(sub_s.loc[n, "avg_throughput_mbps"])
            rec_s = float(sub_r.loc[n, "waktu_pemulihan_mean"])
            scale_p = n / 3.0

            # Upload: T berbanding terbalik dengan throughput (T_3 / T_n = thr_n / thr_3)
            s_up = up_thr / base_up_thr if base_up_thr > 0 else np.nan
            e_up = s_up / scale_p if not pd.isna(s_up) else np.nan

            # Pemulihan: S_rel = T_rec(3) / T_rec(n)
            s_rec = base_rec_s / rec_s if rec_s > 0 else np.nan
            e_rec = s_rec / scale_p if not pd.isna(s_rec) else np.nan

            rows.append(
                {
                    "strategi": strat_key,
                    "nodes": n,
                    "scale_factor_vs_n3": round(scale_p, 4),
                    "upload_throughput_mbps": round(up_thr, 4),
                    "upload_speedup_rel": round(s_up, 4),
                    "upload_efficiency_rel": round(e_up, 4),
                    "recovery_time_s": round(rec_s, 3),
                    "recovery_speedup_rel": round(s_rec, 4),
                    "recovery_efficiency_rel": round(e_rec, 4),
                }
            )
    return pd.DataFrame(rows)


def plot_speedup_efficiency(se_df: pd.DataFrame, out_path: Path):
    """Plot Speedup & Efficiency relatif (baseline 3 node) untuk waktu pemulihan dan upload."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.8))

    # Panel kiri: Speedup relatif waktu pemulihan
    ideal_x = NODE_COUNTS
    ideal_s = [n / 3.0 for n in NODE_COUNTS]
    ax1.plot(ideal_x, ideal_s, linestyle="--", color="#888888", linewidth=1.4, label="Ideal Linear (P/3)")

    for strat_key, _short, label in STRATEGIES:
        sub = se_df[se_df["strategi"] == strat_key].sort_values("nodes")
        if sub.empty:
            continue
        ax1.plot(
            sub["nodes"],
            sub["recovery_speedup_rel"],
            marker=MARKERS[strat_key],
            linewidth=2.1,
            markersize=7,
            label=label,
            color=COLORS[strat_key],
        )
        for _, r in sub.iterrows():
            ax1.annotate(
                f"{r['recovery_speedup_rel']:.2f}x",
                (r["nodes"], r["recovery_speedup_rel"]),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
                fontsize=8,
                color=COLORS[strat_key],
            )

    ax1.set_title("Speedup Relatif Pemulihan (Baseline 3 Node)", pad=10, fontsize=11)
    ax1.set_xlabel("Jumlah Data Node")
    ax1.set_ylabel("Speedup Relatif (S = T₃ / Tₙ)")
    ax1.set_xticks(NODE_COUNTS)
    ax1.set_xticklabels([f"{n} Node" for n in NODE_COUNTS])
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(frameon=True, fontsize=8.5, loc="upper left")

    # Panel kanan: Efficiency relatif (Upload vs Pemulihan — rata-rata 3 strategi per ukuran node)
    avg_by_n = se_df.groupby("nodes")[["upload_efficiency_rel", "recovery_efficiency_rel"]].mean().reindex(NODE_COUNTS)
    x = np.arange(len(NODE_COUNTS))
    w = 0.34
    b1 = ax2.bar(
        x - w / 2,
        avg_by_n["recovery_efficiency_rel"].values,
        w,
        label="Efisiensi Pemulihan",
        color="#2A9D8F",
        edgecolor="white",
    )
    b2 = ax2.bar(
        x + w / 2,
        avg_by_n["upload_efficiency_rel"].values,
        w,
        label="Efisiensi Upload (Single-Host)",
        color="#3D5A80",
        edgecolor="white",
    )
    ax2.axhline(1.0, linestyle="--", color="#888888", linewidth=1.2, label="Ideal (E = 1,00)")
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                h + 0.03,
                f"{h:.2f}",
                ha="center",
                va="bottom",
                fontsize=8.5,
            )

    ax2.set_title("Rata-rata Efisiensi Relatif (E = S / (P/3))", pad=10, fontsize=11)
    ax2.set_xlabel("Jumlah Data Node")
    ax2.set_ylabel("Efisiensi Relatif (E)")
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{n} Node" for n in NODE_COUNTS])
    max_e = float(max(avg_by_n["recovery_efficiency_rel"].max(), avg_by_n["upload_efficiency_rel"].max(), 1.0))
    ax2.set_ylim(0, max_e * 1.40)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.legend(frameon=True, fontsize=8.5, loc="upper right")

    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> int:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    setup_style()

    summary_df, repeat_df, notes = load_summary()
    se_df = compute_speedup_efficiency(summary_df, repeat_df)
    out_csv = DATA_DIR / "summary.csv"
    out_rep_csv = DATA_DIR / "summary_ulang.csv"
    out_se_csv = DATA_DIR / "speedup_efficiency.csv"
    summary_df.to_csv(out_csv, index=False)
    repeat_df.to_csv(out_rep_csv, index=False)
    se_df.to_csv(out_se_csv, index=False)

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
        repeat_df,
        "waktu_pemulihan_mean",
        "Perbandingan Waktu Pemulihan saat 1 Node Mati (Rata-rata ± SD, RF=2, Chunk 4 MB)",
        "Waktu Pemulihan (detik)",
        FIG_DIR / "03_waktu_pemulihan.png",
        fmt="{:.1f}",
        err_col="waktu_pemulihan_std",
        n_runs_col="n_runs",
    )
    plot_scalability(summary_df, FIG_DIR / "04_scalability_throughput.png")
    plot_hetero_figures(notes)
    plot_grouped_bar(
        summary_df,
        "avg_chunk_latency_ms",
        "Perbandingan Latensi / Waktu Akses per Chunk (RF=2, Chunk 4 MB)",
        "Rata-rata Latensi per Chunk (ms)",
        FIG_DIR / "07_latensi_waktu_akses.png",
        fmt="{:.2f}",
    )
    plot_speedup_efficiency(se_df, FIG_DIR / "08_speedup_efficiency.png")

    print(f"Ringkasan utama disimpan ke:     {out_csv}")
    print(f"Ringkasan pengulangan ke:        {out_rep_csv}")
    print(f"Speedup & efficiency ke:         {out_se_csv}")
    print(f"Grafik disimpan ke:              {FIG_DIR}")
    print("\n--- Ringkasan 9 Skenario Utama ---")
    print(summary_df.to_string(index=False))
    print("\n--- Ringkasan Pengulangan (summary_ulang.csv) ---")
    print(repeat_df.to_string(index=False))
    print("\n--- Speedup & Efficiency Relatif (baseline 3 node) ---")
    print(se_df.to_string(index=False))

    if notes:
        print("\nCatatan validasi:")
        for note in notes:
            print(f"  - {note}")
    else:
        print("\nValidasi: seluruh data yang dianalisis lengkap dan valid.")
    return 0


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=UserWarning)
    sys.exit(main())
