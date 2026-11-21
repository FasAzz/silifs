import argparse
import logging
import os
import sys

from client.client import SiliFSClient


def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [client] %(message)s",
        datefmt="%H:%M:%S",
    )


def handle_upload(args) -> int:
    client = SiliFSClient(
        master_address=args.master,
        metrics_csv=args.metrics_csv,
    )

    if not os.path.exists(args.file_path):
        print(f"[ERROR] File lokal tidak ditemukan: {args.file_path}", file=sys.stderr)
        return 1

    print(f"=== SiliFS Upload ===")
    print(f"File Path    : {args.file_path}")
    print(f"Master       : {args.master}")
    print(f"RF           : {args.rf}")
    print(f"Chunk Size   : {args.chunk_mb} MB")
    print(f"Strategi     : {args.strategy}")
    print(f"Metrics CSV  : {args.metrics_csv}")
    print("-" * 35)

    try:
        res = client.upload(
            local_path=args.file_path,
            filename=args.filename,
            rf=args.rf,
            chunk_mb=args.chunk_mb,
            strategy=args.strategy,
        )
    except Exception as e:
        print(f"[ERROR] Upload gagal dengan exception: {e}", file=sys.stderr)
        return 1

    if res.get("ok"):
        print("Upload BERHASIL!")
        print(f"File Name    : {res.get('filename')}")
        print(f"Ukuran File  : {res.get('file_mb', 0):.2f} MB ({res.get('file_size', 0)} bytes)")
        print(f"Jumlah Chunk : {res.get('chunks', 0)}")
        print(f"Durasi Total : {res.get('duration_s', 0):.4f} detik")
        print(f"Throughput   : {res.get('throughput_mbps', 0):.2f} MB/s")
        print(f"Avg Latency  : {res.get('avg_chunk_latency_ms', 0):.2f} ms/chunk")
        return 0
    else:
        print(f"[ERROR] Upload GAGAL: {res.get('error')}", file=sys.stderr)
        return 1


def handle_download(args) -> int:
    client = SiliFSClient(
        master_address=args.master,
        metrics_csv=args.metrics_csv,
    )

    print(f"=== SiliFS Download ===")
    print(f"File Name    : {args.filename}")
    print(f"Target Output: {args.out}")
    print(f"Master       : {args.master}")
    print(f"Metrics CSV  : {args.metrics_csv}")
    print("-" * 35)

    try:
        res = client.download(
            filename=args.filename,
            output_path=args.out,
        )
    except Exception as e:
        print(f"[ERROR] Download gagal dengan exception: {e}", file=sys.stderr)
        return 1

    if res.get("ok"):
        print("Download BERHASIL!")
        print(f"Tersimpan di : {res.get('output_path')}")
        print(f"Ukuran File  : {res.get('file_mb', 0):.2f} MB ({res.get('file_size', 0)} bytes)")
        print(f"Jumlah Chunk : {res.get('chunks', 0)}")
        print(f"Durasi Total : {res.get('duration_s', 0):.4f} detik")
        print(f"Throughput   : {res.get('throughput_mbps', 0):.2f} MB/s")
        print(f"Avg Latency  : {res.get('avg_chunk_latency_ms', 0):.2f} ms/chunk")
        return 0
    else:
        print(f"[ERROR] Download GAGAL: {res.get('error')}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m client.cli",
        description="SiliFS Distributed File System Client CLI",
    )
    parser.add_argument(
        "--master",
        default="localhost:50051",
        help="Alamat Master service (default: localhost:50051)",
    )
    parser.add_argument(
        "--metrics-csv",
        default="experiments/results/client_metrics.csv",
        help="Path file CSV untuk mencatat metrik (default: experiments/results/client_metrics.csv)",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: upload
    p_upload = subparsers.add_parser("upload", help="Upload file ke SiliFS")
    p_upload.add_argument("file_path", help="Path ke file lokal yang akan di-upload")
    p_upload.add_argument(
        "--rf",
        type=int,
        default=2,
        help="Replication factor (default: 2)",
    )
    p_upload.add_argument(
        "--chunk-mb",
        type=int,
        default=4,
        choices=[1, 4, 8],
        help="Ukuran chunk dalam MB (default: 4)",
    )
    p_upload.add_argument(
        "--strategy",
        default="round_robin",
        choices=["random", "round_robin", "capacity_aware"],
        help="Strategi penempatan replika (default: round_robin)",
    )
    p_upload.add_argument(
        "--filename",
        default=None,
        help="Nama file yang disimpan di SiliFS (default: nama basename file lokal)",
    )

    # Subcommand: download
    p_download = subparsers.add_parser("download", help="Download file dari SiliFS")
    p_download.add_argument("filename", help="Nama file di SiliFS yang ingin di-download")
    p_download.add_argument(
        "--out",
        required=True,
        help="Path tujuan file hasil download",
    )

    return parser


def main():
    setup_logger()
    parser = build_parser()
    args = parser.parse_args()

    if args.subcommand == "upload":
        sys.exit(handle_upload(args))
    elif args.subcommand == "download":
        sys.exit(handle_download(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
