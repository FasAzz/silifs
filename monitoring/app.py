import argparse
import csv
import hashlib
import io
import json
import os
import socket
import sys
import tempfile
from typing import Dict, List, Any

from flask import Flask, jsonify, render_template_string, request, send_file

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from client.client import SiliFSClient

app = Flask(__name__)

# Konfigurasi default
DATA_DIR = "data"
METRICS_CSV = os.path.join("experiments", "results", "client_metrics.csv")
MASTER_ADDR = "localhost:50051"
NODE_CAPACITY_MB = 2048
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
    <title>SiliFS — Cluster Monitoring Dashboard</title>
    <style>
        :root {
            --bg-deep: #060911;
            --bg-surface: rgba(15, 21, 36, 0.78);
            --bg-surface-solid: #0f1524;
            --bg-elevated: rgba(23, 32, 54, 0.72);
            --text-main: #f4f6fb;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
            --gold: #e5c07b;
            --gold-soft: rgba(229, 192, 123, 0.14);
            --gold-border: rgba(229, 192, 123, 0.32);
            --accent: #60a5fa;
            --accent-soft: rgba(96, 165, 250, 0.14);
            --violet: #a78bfa;
            --violet-soft: rgba(167, 139, 250, 0.15);
            --success: #34d399;
            --success-soft: rgba(52, 211, 153, 0.12);
            --success-border: rgba(52, 211, 153, 0.32);
            --danger: #f87171;
            --danger-soft: rgba(248, 113, 113, 0.12);
            --danger-border: rgba(248, 113, 113, 0.35);
            --border: rgba(255, 255, 255, 0.075);
            --border-hover: rgba(229, 192, 123, 0.28);
            --shadow-card: 0 18px 45px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.05);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            background-color: var(--bg-deep);
            background-image:
                radial-gradient(ellipse 80% 50% at 15% -10%, rgba(229, 192, 123, 0.11), transparent 55%),
                radial-gradient(ellipse 70% 45% at 85% 0%, rgba(56, 189, 248, 0.09), transparent 55%),
                radial-gradient(circle at 50% 100%, rgba(167, 139, 250, 0.05), transparent 50%);
            background-attachment: fixed;
            color: var(--text-main);
            min-height: 100vh;
            padding: 32px 28px 48px;
            -webkit-font-smoothing: antialiased;
        }

        .container {
            max-width: 1280px;
            margin: 0 auto;
        }

        /* Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            padding: 20px 26px;
            margin-bottom: 28px;
            background: var(--bg-surface);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border: 1px solid var(--border);
            border-radius: 18px;
            box-shadow: var(--shadow-card);
            position: relative;
            overflow: hidden;
        }

        header::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(229, 192, 123, 0.55), rgba(96, 165, 250, 0.4), transparent);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .brand-logo {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            background: linear-gradient(135deg, rgba(229, 192, 123, 0.2), rgba(229, 192, 123, 0.04));
            border: 1px solid var(--gold-border);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 24px rgba(229, 192, 123, 0.14);
            flex-shrink: 0;
        }

        .brand-text h1 {
            font-size: 21px;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .brand-text h1 .accent-word {
            background: linear-gradient(120deg, #f6e2b3 0%, #e5c07b 55%, #c99d4e 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand-subtitle {
            font-size: 12.5px;
            color: var(--text-muted);
            letter-spacing: 0.04em;
            margin-top: 3px;
        }

        .header-meta {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .live-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 7px 14px;
            border-radius: 999px;
            background: var(--success-soft);
            border: 1px solid var(--success-border);
            color: var(--success);
            font-size: 11.5px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .pulse-dot {
            position: relative;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
        }

        .pulse-dot::after {
            content: "";
            position: absolute;
            inset: -4px;
            border-radius: 50%;
            border: 1.5px solid var(--success);
            animation: ripple 1.8s ease-out infinite;
        }

        @keyframes ripple {
            0% { transform: scale(0.7); opacity: 0.9; }
            100% { transform: scale(2.1); opacity: 0; }
        }

        .refresh-chip {
            font-size: 12.5px;
            color: var(--text-muted);
            padding: 7px 13px;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border);
            font-variant-numeric: tabular-nums;
        }

        /* KPI Grid */
        .grid-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 18px;
            margin-bottom: 32px;
        }

        .stat-card {
            background: var(--bg-surface);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            padding: 22px 24px;
            border-radius: 16px;
            border: 1px solid var(--border);
            box-shadow: var(--shadow-card);
            position: relative;
            overflow: hidden;
            transition: transform 0.25s ease, border-color 0.25s ease;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            border-color: var(--border-hover);
        }

        .stat-card::after {
            content: "";
            position: absolute;
            top: 0;
            left: 24px;
            right: 24px;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(229, 192, 123, 0.38), transparent);
            opacity: 0.7;
        }

        .stat-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }

        .stat-label {
            font-size: 11.5px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.09em;
            font-weight: 600;
        }

        .stat-icon {
            width: 34px;
            height: 34px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border);
            color: var(--gold);
        }

        .stat-value {
            font-size: 30px;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text-main);
            font-variant-numeric: tabular-nums;
            line-height: 1.15;
        }

        .stat-unit {
            font-size: 15px;
            font-weight: 500;
            color: var(--text-muted);
            margin-left: 4px;
        }

        /* Section Titles */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 16px;
        }

        .section-title {
            font-size: 15.5px;
            font-weight: 600;
            letter-spacing: 0.01em;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .section-title::before {
            content: "";
            width: 4px;
            height: 18px;
            border-radius: 4px;
            background: linear-gradient(180deg, var(--gold), #a67c37);
            box-shadow: 0 0 12px rgba(229, 192, 123, 0.4);
        }

        .section-hint {
            font-size: 12px;
            color: var(--text-dim);
            font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
        }

        /* Node Cards */
        .nodes-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
            gap: 18px;
            margin-bottom: 34px;
        }

        .node-card {
            background: var(--bg-surface);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            border-radius: 16px;
            border: 1px solid var(--border);
            padding: 22px 24px;
            box-shadow: var(--shadow-card);
            transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
            position: relative;
            overflow: hidden;
        }

        .node-card:hover {
            transform: translateY(-2px);
            border-color: var(--border-hover);
        }

        .node-card.is-offline {
            border-color: rgba(248, 113, 113, 0.35);
            background: linear-gradient(180deg, rgba(248, 113, 113, 0.06), rgba(15, 21, 36, 0.85));
        }

        .node-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .node-title-wrap {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .node-avatar {
            width: 34px;
            height: 34px;
            border-radius: 10px;
            background: var(--gold-soft);
            border: 1px solid var(--gold-border);
            color: var(--gold);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 700;
        }

        .node-card.is-offline .node-avatar {
            background: var(--danger-soft);
            border-color: var(--danger-border);
            color: var(--danger);
        }

        .node-name {
            font-weight: 700;
            font-size: 16px;
            letter-spacing: -0.01em;
        }

        .node-addr {
            font-size: 12px;
            color: var(--text-dim);
            font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
            margin-top: 2px;
        }

        .status-pill {
            padding: 5px 11px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.06em;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-transform: uppercase;
        }

        .status-online {
            background: var(--success-soft);
            color: var(--success);
            border: 1px solid var(--success-border);
        }

        .status-offline {
            background: var(--danger-soft);
            color: var(--danger);
            border: 1px solid var(--danger-border);
        }

        .node-metrics-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 16px;
        }

        .node-metric-box {
            padding: 11px 13px;
            border-radius: 11px;
            background: rgba(255, 255, 255, 0.025);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .node-metric-label {
            font-size: 11px;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 4px;
        }

        .node-metric-val {
            font-size: 15px;
            font-weight: 700;
            color: var(--text-main);
            font-variant-numeric: tabular-nums;
        }

        .storage-bar-wrap {
            margin-top: 4px;
        }

        .storage-bar-meta {
            display: flex;
            justify-content: space-between;
            font-size: 11.5px;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-variant-numeric: tabular-nums;
        }

        .storage-track {
            width: 100%;
            height: 6px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.07);
            overflow: hidden;
        }

        .storage-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #c99d4e, #e5c07b, #60a5fa);
            transition: width 0.45s cubic-bezier(0.22, 1, 0.36, 1);
        }

        .node-card.is-offline .storage-fill {
            background: linear-gradient(90deg, #b91c1c, #f87171);
        }

        /* Table */
        .table-container {
            background: var(--bg-surface);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            border-radius: 16px;
            border: 1px solid var(--border);
            box-shadow: var(--shadow-card);
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 13.5px;
        }

        thead th {
            background: rgba(255, 255, 255, 0.025);
            color: var(--text-muted);
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            padding: 15px 18px;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }

        tbody td {
            padding: 14px 18px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.045);
            color: var(--text-main);
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }

        tbody tr {
            transition: background-color 0.18s ease;
        }

        tbody tr:hover {
            background: rgba(229, 192, 123, 0.04);
        }

        tbody tr:last-child td {
            border-bottom: none;
        }

        .mono {
            font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
            font-size: 12.5px;
            color: var(--text-muted);
        }

        .filename-cell {
            font-weight: 600;
            color: var(--text-main);
        }

        .tag-op {
            display: inline-block;
            font-size: 10.5px;
            font-weight: 700;
            letter-spacing: 0.07em;
            padding: 4px 10px;
            border-radius: 6px;
            text-transform: uppercase;
        }

        .tag-upload {
            background: var(--accent-soft);
            color: #93c5fd;
            border: 1px solid rgba(96, 165, 250, 0.3);
        }

        .tag-download {
            background: var(--violet-soft);
            color: #c4b5fd;
            border: 1px solid rgba(167, 139, 250, 0.32);
        }

        .strategy-pill {
            display: inline-block;
            padding: 3px 9px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #e2e8f0;
        }

        .throughput-val {
            font-weight: 700;
            color: var(--gold);
        }

        .ok-pill {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.05em;
        }

        .ok-true {
            background: var(--success-soft);
            color: var(--success);
            border: 1px solid var(--success-border);
        }

        .ok-false {
            background: var(--danger-soft);
            color: var(--danger);
            border: 1px solid var(--danger-border);
        }

        .empty-state {
            text-align: center;
            padding: 34px 16px !important;
            color: var(--text-dim) !important;
            font-size: 13.5px;
        }

        /* Interactive Control Panel */
        .control-panel {
            background: var(--bg-surface);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            border-radius: 16px;
            border: 1px solid var(--border);
            box-shadow: var(--shadow-card);
            padding: 22px 24px;
            margin-bottom: 34px;
        }

        .control-grid {
            display: grid;
            grid-template-columns: 2fr 1.2fr 1.1fr 0.7fr 0.8fr;
            gap: 14px;
            align-items: end;
        }

        @media (max-width: 960px) {
            .control-grid {
                grid-template-columns: 1fr 1fr;
            }
        }

        .field-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .field-label {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
        }

        .field-input, .field-select {
            height: 40px;
            padding: 0 12px;
            border-radius: 10px;
            background: rgba(6, 9, 17, 0.75);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: var(--text-main);
            font-size: 13px;
            outline: none;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }

        .field-input:focus, .field-select:focus {
            border-color: var(--gold-border);
            box-shadow: 0 0 0 3px rgba(229, 192, 123, 0.12);
        }

        .field-input[type="file"] {
            padding: 7px 10px;
            cursor: pointer;
        }

        .field-input[type="file"]::file-selector-button {
            background: var(--gold-soft);
            color: var(--gold);
            border: 1px solid var(--gold-border);
            border-radius: 6px;
            padding: 4px 10px;
            margin-right: 10px;
            font-size: 11.5px;
            font-weight: 600;
            cursor: pointer;
        }

        .control-actions {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 12px;
            margin-top: 16px;
        }

        .btn {
            height: 40px;
            padding: 0 18px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.02em;
            cursor: pointer;
            border: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: transform 0.15s ease, opacity 0.2s ease, box-shadow 0.2s ease;
        }

        .btn:hover:not(:disabled) {
            transform: translateY(-1px);
        }

        .btn:disabled {
            opacity: 0.55;
            cursor: wait;
        }

        .btn-gold {
            background: linear-gradient(135deg, #e5c07b 0%, #c99d4e 100%);
            color: #0b0f19;
            box-shadow: 0 6px 20px rgba(229, 192, 123, 0.24);
        }

        .btn-outline {
            background: rgba(255, 255, 255, 0.04);
            color: var(--text-main);
            border: 1px solid rgba(255, 255, 255, 0.12);
        }

        .btn-outline:hover:not(:disabled) {
            border-color: var(--gold-border);
            color: var(--gold);
        }

        .btn-xs {
            height: 28px;
            padding: 0 10px;
            border-radius: 7px;
            font-size: 11.5px;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(255, 255, 255, 0.04);
            color: var(--text-main);
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            transition: border-color 0.18s ease, color 0.18s ease;
        }

        .btn-xs:hover {
            border-color: var(--gold-border);
            color: var(--gold);
        }

        .feedback-box {
            margin-top: 14px;
            padding: 12px 15px;
            border-radius: 10px;
            font-size: 12.5px;
            display: none;
            line-height: 1.5;
        }

        .feedback-box.show { display: block; }
        .feedback-ok {
            background: var(--success-soft);
            border: 1px solid var(--success-border);
            color: #a7f3d0;
        }
        .feedback-err {
            background: var(--danger-soft);
            border: 1px solid var(--danger-border);
            color: #fecaca;
        }
        .feedback-info {
            background: var(--accent-soft);
            border: 1px solid rgba(96, 165, 250, 0.3);
            color: #bfdbfe;
        }
        .hash-code {
            font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
            font-size: 11.5px;
            background: rgba(0, 0, 0, 0.28);
            padding: 2px 6px;
            border-radius: 5px;
            word-break: break-all;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <div class="brand-logo" aria-hidden="true">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                        <path d="M12 2.5L20.5 7.25V16.75L12 21.5L3.5 16.75V7.25L12 2.5Z" stroke="#e5c07b" stroke-width="1.7" stroke-linejoin="round"/>
                        <path d="M12 21.5V12M12 12L20.5 7.25M12 12L3.5 7.25" stroke="#e5c07b" stroke-width="1.5" stroke-opacity="0.7" stroke-linejoin="round"/>
                        <circle cx="12" cy="12" r="2.2" fill="#e5c07b"/>
                    </svg>
                </div>
                <div class="brand-text">
                    <h1><span class="accent-word">SiliFS</span> Cluster Monitor</h1>
                    <div class="brand-subtitle">Distributed File System &middot; Real-Time Node &amp; Replication Telemetry</div>
                </div>
            </div>
            <div class="header-meta">
                <span class="live-badge"><span class="pulse-dot"></span>Live</span>
                <span class="refresh-chip" id="refresh-time">Memperbarui...</span>
            </div>
        </header>

        <div class="grid-stats">
            <div class="stat-card">
                <div class="stat-top">
                    <div class="stat-label">Total Data Nodes</div>
                    <div class="stat-icon" aria-hidden="true">
                        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><line x1="7" y1="7" x2="7.01" y2="7"/><line x1="7" y1="17" x2="7.01" y2="17"/>
                        </svg>
                    </div>
                </div>
                <div class="stat-value" id="total-nodes">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-top">
                    <div class="stat-label">Node Aktif / Mati</div>
                    <div class="stat-icon" aria-hidden="true">
                        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                        </svg>
                    </div>
                </div>
                <div class="stat-value" id="node-health">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-top">
                    <div class="stat-label">Total Chunks Tersimpan</div>
                    <div class="stat-icon" aria-hidden="true">
                        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                        </svg>
                    </div>
                </div>
                <div class="stat-value" id="total-chunks">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-top">
                    <div class="stat-label">Penyimpanan Terpakai</div>
                    <div class="stat-icon" aria-hidden="true">
                        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                            <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
                        </svg>
                    </div>
                </div>
                <div class="stat-value" id="total-storage">-</div>
            </div>
        </div>

        <div class="section-header">
            <div class="section-title">Status Data Nodes</div>
            <span class="section-hint">Auto-refresh 3s</span>
        </div>
        <div class="nodes-grid" id="nodes-container">
            <!-- Node cards injected here -->
        </div>

        <div class="section-header">
            <div class="section-title">Kontrol Upload &amp; Verifikasi Langsung</div>
            <span class="section-hint">Terhubung ke SiliFS Master gRPC</span>
        </div>
        <div class="control-panel">
            <div class="control-grid">
                <div class="field-group">
                    <label class="field-label" for="upload-file">Pilih File Lokal</label>
                    <input class="field-input" type="file" id="upload-file">
                </div>
                <div class="field-group">
                    <label class="field-label" for="upload-filename">Nama di SiliFS (opsional)</label>
                    <input class="field-input" type="text" id="upload-filename" placeholder="contoh: demo.bin">
                </div>
                <div class="field-group">
                    <label class="field-label" for="upload-strategy">Strategi Replika</label>
                    <select class="field-select" id="upload-strategy">
                        <option value="round_robin">Round-Robin</option>
                        <option value="capacity_aware">Capacity-Aware</option>
                        <option value="random">Random</option>
                    </select>
                </div>
                <div class="field-group">
                    <label class="field-label" for="upload-rf">RF</label>
                    <select class="field-select" id="upload-rf">
                        <option value="1">1</option>
                        <option value="2" selected>2</option>
                        <option value="3">3</option>
                    </select>
                </div>
                <div class="field-group">
                    <label class="field-label" for="upload-chunk">Chunk</label>
                    <select class="field-select" id="upload-chunk">
                        <option value="1">1 MB</option>
                        <option value="4" selected>4 MB</option>
                        <option value="8">8 MB</option>
                    </select>
                </div>
            </div>
            <div class="control-actions">
                <button class="btn btn-gold" id="btn-upload" onclick="doUpload(false)">&#8679; Upload File</button>
                <button class="btn btn-outline" id="btn-gen50" onclick="doUpload(true)">&#9889; Generate &amp; Upload 50 MB</button>
            </div>
            <div id="action-feedback" class="feedback-box"></div>
        </div>

        <div class="section-header">
            <div class="section-title">Riwayat Operasi Client</div>
            <span class="section-hint">client_metrics.csv (10 terbaru)</span>
        </div>
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
                        <th>Aksi</th>
                    </tr>
                </thead>
                <tbody id="metrics-tbody">
                    <tr><td colspan="10" class="empty-state">Memuat data...</td></tr>
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
                document.getElementById('node-health').innerHTML =
                    `<span style="color: var(--success);">${data.cluster.alive_nodes}</span> <span style="color: var(--text-dim); font-weight: 400;">/</span> <span style="color: var(--danger);">${data.cluster.dead_nodes}</span>`;
                document.getElementById('total-chunks').innerHTML =
                    `${data.cluster.total_chunks}<span class="stat-unit">chunk</span>`;
                document.getElementById('total-storage').innerHTML =
                    `${data.cluster.total_used_mb.toFixed(2)}<span class="stat-unit">MB</span>`;

                // Update Nodes
                const container = document.getElementById('nodes-container');
                container.innerHTML = '';
                data.nodes.forEach((n, idx) => {
                    const statusClass = n.alive ? 'status-online' : 'status-offline';
                    const cardState = n.alive ? '' : 'is-offline';
                    const statusText = n.alive ? '● ONLINE' : '✖ OFFLINE';
                    const pct = n.capacity_mb > 0 ? Math.min(100, (n.used_mb / n.capacity_mb) * 100) : 0;
                    const card = `
                        <div class="node-card ${cardState}">
                            <div class="node-header">
                                <div class="node-title-wrap">
                                    <div class="node-avatar">N${idx + 1}</div>
                                    <div>
                                        <div class="node-name">${n.node_id}</div>
                                        <div class="node-addr">${n.address}</div>
                                    </div>
                                </div>
                                <span class="status-pill ${statusClass}">${statusText}</span>
                            </div>
                            <div class="node-metrics-row">
                                <div class="node-metric-box">
                                    <div class="node-metric-label">Chunks</div>
                                    <div class="node-metric-val">${n.chunk_count} <span style="font-size: 12px; font-weight: 400; color: var(--text-muted);">chunk</span></div>
                                </div>
                                <div class="node-metric-box">
                                    <div class="node-metric-label">Terpakai</div>
                                    <div class="node-metric-val">${n.used_mb.toFixed(2)} <span style="font-size: 12px; font-weight: 400; color: var(--text-muted);">MB</span></div>
                                </div>
                            </div>
                            <div class="storage-bar-wrap">
                                <div class="storage-bar-meta">
                                    <span>Kapasitas Virtual</span>
                                    <span>${n.used_mb.toFixed(1)} / ${n.capacity_mb} MB (${pct.toFixed(1)}%)</span>
                                </div>
                                <div class="storage-track">
                                    <div class="storage-fill" style="width: ${pct.toFixed(1)}%;"></div>
                                </div>
                            </div>
                        </div>
                    `;
                    container.innerHTML += card;
                });

                // Update Metrics Table
                const tbody = document.getElementById('metrics-tbody');
                if (data.recent_metrics.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="10" class="empty-state">Belum ada log operasi.</td></tr>';
                } else {
                    tbody.innerHTML = '';
                    data.recent_metrics.slice(-10).reverse().forEach(m => {
                        const tagClass = m.operation === 'upload' ? 'tag-upload' : 'tag-download';
                        const isOk = m.ok === 'True' || m.ok === true;
                        const okText = isOk
                            ? '<span class="ok-pill ok-true">✓ SUKSES</span>'
                            : '<span class="ok-pill ok-false">✗ GAGAL</span>';
                        const safeName = encodeURIComponent(m.filename || '');
                        const escapedJs = (m.filename || '').replace(/'/g, "\\'");
                        const actionsHtml = isOk
                            ? `<div style="display:flex; gap:6px;">
                                   <a class="btn-xs" href="/api/download/${safeName}">&#8681; Unduh</a>
                                   <button class="btn-xs" onclick="doVerify('${escapedJs}')">&#10003; SHA-256</button>
                               </div>`
                            : '<span style="color:var(--text-dim); font-size:12px;">-</span>';
                        tbody.innerHTML += `
                            <tr>
                                <td class="mono">${m.timestamp}</td>
                                <td><span class="tag-op ${tagClass}">${m.operation}</span></td>
                                <td class="filename-cell">${m.filename}</td>
                                <td><span class="strategy-pill">${m.strategy}</span></td>
                                <td>${m.rf}</td>
                                <td>${m.file_mb} MB</td>
                                <td>${m.duration_s} s</td>
                                <td class="throughput-val">${m.throughput_mbps} MB/s</td>
                                <td>${okText}</td>
                                <td>${actionsHtml}</td>
                            </tr>
                        `;
                    });
                }

                document.getElementById('refresh-time').innerText = 'Pembaruan: ' + new Date().toLocaleTimeString();
            } catch (err) {
                console.error("Gagal mengambil data monitoring:", err);
            }
        }

        const uploadedHashes = {};

        function showFeedback(type, html) {
            const box = document.getElementById('action-feedback');
            box.className = 'feedback-box show feedback-' + type;
            box.innerHTML = html;
        }

        function setBusy(busy) {
            document.getElementById('btn-upload').disabled = busy;
            document.getElementById('btn-gen50').disabled = busy;
        }

        async function doUpload(generate50) {
            const fileInput = document.getElementById('upload-file');
            const customName = document.getElementById('upload-filename').value.trim();
            const strategy = document.getElementById('upload-strategy').value;
            const rf = document.getElementById('upload-rf').value;
            const chunkMb = document.getElementById('upload-chunk').value;

            const fd = new FormData();
            fd.append('strategy', strategy);
            fd.append('rf', rf);
            fd.append('chunk_mb', chunkMb);
            if (customName) fd.append('filename', customName);

            if (generate50) {
                fd.append('generate_mb', '50');
                showFeedback('info', 'Membuat file acak 50 MB dan mengunggah ke cluster SiliFS...');
            } else {
                if (!fileInput.files || fileInput.files.length === 0) {
                    showFeedback('err', 'Pilih file terlebih dahulu, atau klik <strong>Generate &amp; Upload 50 MB</strong>.');
                    return;
                }
                fd.append('file', fileInput.files[0]);
                showFeedback('info', `Mengunggah <strong>${fileInput.files[0].name}</strong> ke cluster SiliFS...`);
            }

            setBusy(true);
            try {
                const res = await fetch('/api/upload', { method: 'POST', body: fd });
                const data = await res.json();
                if (data.ok) {
                    uploadedHashes[data.filename] = data.sha256;
                    showFeedback(
                        'ok',
                        `<strong>Upload BERHASIL:</strong> ${data.filename} (${data.file_mb.toFixed(2)} MB, ${data.chunks} chunk, ${data.duration_s.toFixed(2)} s, <strong>${data.throughput_mbps.toFixed(2)} MB/s</strong>)<br>SHA-256: <span class="hash-code">${data.sha256}</span>`
                    );
                    fetchStatus();
                } else {
                    showFeedback('err', `<strong>Upload GAGAL:</strong> ${data.error || 'Terjadi kesalahan.'}`);
                }
            } catch (e) {
                showFeedback('err', `<strong>Error:</strong> ${e.message}`);
            } finally {
                setBusy(false);
            }
        }

        async function doVerify(filename) {
            showFeedback('info', `Mengunduh &amp; memverifikasi integritas SHA-256 untuk <strong>${filename}</strong>...`);
            try {
                const res = await fetch('/api/verify/' + encodeURIComponent(filename), { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    const orig = uploadedHashes[filename];
                    const matchNote = orig
                        ? (orig === data.sha256 ? ' &nbsp; <strong style="color:var(--success);">&#10003; IDENTIK DENGAN UPLOAD</strong>' : ' &nbsp; <strong style="color:var(--danger);">&#10007; HASH BERBEDA</strong>')
                        : '';
                    showFeedback(
                        'ok',
                        `<strong>Download &amp; Verifikasi BERHASIL:</strong> ${data.filename} (${data.file_mb.toFixed(2)} MB, ${data.duration_s.toFixed(2)} s, <strong>${data.throughput_mbps.toFixed(2)} MB/s</strong>)${matchNote}<br>SHA-256: <span class="hash-code">${data.sha256}</span>`
                    );
                    fetchStatus();
                } else {
                    showFeedback('err', `<strong>Verifikasi GAGAL:</strong> ${data.error || 'File tidak dapat diunduh.'}`);
                }
            } catch (e) {
                showFeedback('err', `<strong>Error:</strong> ${e.message}`);
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
    global DATA_DIR, METRICS_CSV, DEFAULT_NODES, NODE_CAPACITY_MB

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

        stats = get_node_stats(nid, DATA_DIR, capacity_mb=NODE_CAPACITY_MB)
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


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


@app.route("/api/upload", methods=["POST"])
def api_upload():
    global MASTER_ADDR, METRICS_CSV
    strategy = request.form.get("strategy", "round_robin")
    rf = int(request.form.get("rf", 2))
    chunk_mb = int(request.form.get("chunk_mb", 4))
    custom_name = (request.form.get("filename") or "").strip()
    generate_mb = request.form.get("generate_mb")

    tmp_path = None
    try:
        if generate_mb:
            size_mb = max(1, min(200, int(generate_mb)))
            short_st = {"random": "rnd", "round_robin": "rr", "capacity_aware": "cap"}.get(strategy, strategy)
            target_name = custom_name or f"demo_{short_st}_{size_mb}mb.bin"
            fd, tmp_path = tempfile.mkstemp(prefix="silifs_up_", suffix=".bin")
            with os.fdopen(fd, "wb") as f:
                for _ in range(size_mb):
                    f.write(os.urandom(1024 * 1024))
        else:
            up_file = request.files.get("file")
            if not up_file or not up_file.filename:
                return jsonify({"ok": False, "error": "Tidak ada file yang dipilih."}), 400
            target_name = custom_name or os.path.basename(up_file.filename)
            fd, tmp_path = tempfile.mkstemp(prefix="silifs_up_")
            os.close(fd)
            up_file.save(tmp_path)

        file_hash = _sha256_file(tmp_path)
        client = SiliFSClient(master_address=MASTER_ADDR, metrics_csv=METRICS_CSV)
        res = client.upload(
            local_path=tmp_path,
            filename=target_name,
            rf=rf,
            chunk_mb=chunk_mb,
            strategy=strategy,
        )
        res["sha256"] = file_hash
        return jsonify(res), (200 if res.get("ok") else 400)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.route("/api/download/<path:filename>", methods=["GET"])
def api_download(filename: str):
    global MASTER_ADDR, METRICS_CSV
    fd, tmp_path = tempfile.mkstemp(prefix="silifs_dl_")
    os.close(fd)
    try:
        client = SiliFSClient(master_address=MASTER_ADDR, metrics_csv=METRICS_CSV)
        res = client.download(filename=filename, output_path=tmp_path)
        if not res.get("ok"):
            return jsonify(res), 404
        with open(tmp_path, "rb") as f:
            buf = io.BytesIO(f.read())
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=os.path.basename(filename))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.route("/api/verify/<path:filename>", methods=["POST"])
def api_verify(filename: str):
    global MASTER_ADDR, METRICS_CSV
    fd, tmp_path = tempfile.mkstemp(prefix="silifs_ver_")
    os.close(fd)
    try:
        client = SiliFSClient(master_address=MASTER_ADDR, metrics_csv=METRICS_CSV)
        res = client.download(filename=filename, output_path=tmp_path)
        if res.get("ok"):
            res["sha256"] = _sha256_file(tmp_path)
        return jsonify(res), (200 if res.get("ok") else 400)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def main():
    global DATA_DIR, METRICS_CSV, DEFAULT_NODES, NODE_CAPACITY_MB, MASTER_ADDR
    parser = argparse.ArgumentParser(description="SiliFS Monitoring Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Port web dashboard (default: 8080)")
    parser.add_argument("--host", default="0.0.0.0", help="Host listening (default: 0.0.0.0)")
    parser.add_argument("--master", default="localhost:50051", help="Alamat Master gRPC (default: localhost:50051)")
    parser.add_argument("--data-dir", default="data", help="Direktori chunk data (default: data)")
    parser.add_argument("--metrics-csv", default=os.path.join("experiments", "results", "client_metrics.csv"),
                        help="Path ke file client_metrics.csv")
    parser.add_argument("--nodes", default=None,
                        help="Daftar node, format: node1=host:port,node2=host:port,...")
    parser.add_argument("--capacity-mb", type=int, default=2048,
                        help="Kapasitas virtual per node dalam MB (default: 2048)")
    args = parser.parse_args()

    DATA_DIR = args.data_dir
    METRICS_CSV = args.metrics_csv
    MASTER_ADDR = args.master
    NODE_CAPACITY_MB = args.capacity_mb
    if args.nodes:
        parsed_nodes = []
        for item in args.nodes.split(","):
            item = item.strip()
            if "=" in item:
                nid, addr = item.split("=", 1)
                parsed_nodes.append({"node_id": nid.strip(), "address": addr.strip()})
        if parsed_nodes:
            DEFAULT_NODES = parsed_nodes

    print(f"==================================================")
    print(f"  SiliFS Monitoring Dashboard Aktif!               ")
    print(f"  Buka di Browser: http://localhost:{args.port}    ")
    print(f"  Data Dir       : {DATA_DIR}                      ")
    print(f"  Metrics CSV    : {METRICS_CSV}                   ")
    print(f"==================================================")

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
