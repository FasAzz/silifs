param(
  [int[]]$Nodes = @(3,5,8),
  [string[]]$Strategies = @('random','round_robin','capacity_aware'),
  [int]$Rf = 2,
  [int]$ChunkMb = 4,
  [int]$Files = 100,
  [int]$FileMb = 50,
  [int]$KillIndex = 2,
  [int]$Repeat = 1,
  [switch]$Force
)

$ErrorActionPreference = 'Continue'
$inv  = [Globalization.CultureInfo]::InvariantCulture
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$dataDir = Join-Path $root 'experiments\data'
$logDir  = Join-Path $dataDir 'logs'
$resDir  = Join-Path $root 'experiments\results'
New-Item -ItemType Directory -Force $dataDir, $logDir, $resDir | Out-Null

$short = @{ random = 'rnd'; round_robin = 'rr'; capacity_aware = 'cap' }
$composeFor = @{
  3 = 'deploy/dockerCompose.yml'
  5 = 'deploy/dockerCompose.5.yml'
  8 = 'deploy/dockerCompose.8.yml'
}
$cleanupCompose = 'deploy/dockerCompose.8.yml'   # superset, membersihkan semua volume

function Run($cmd) { cmd /c "$cmd 2>&1" }

function Ensure-Header($path, $header) {
  if (-not (Test-Path $path)) { Set-Content -Path $path -Value $header -Encoding ascii }
}

function Remove-ScenarioRows($path, $scenarioName) {
  if (Test-Path $path) {
    $prefix = "$scenarioName,"
    $kept = Get-Content -Path $path | Where-Object { -not $_.StartsWith($prefix) }
    Set-Content -Path $path -Value $kept -Encoding ascii
  }
}

$lbCsv  = Join-Path $dataDir 'load_balance.csv'
$recCsv = Join-Path $dataDir 'recovery.csv'
Ensure-Header $lbCsv  'skenario,strategi,rf,chunk_mb,nodes,node_id,chunk_count'
Ensure-Header $recCsv 'skenario,strategi,rf,chunk_mb,nodes,chunks_dipulihkan,waktu_deteksi_s,waktu_pemulihan_s,chunks_total'

# File dasar acak (satu file dipakai untuk semua upload dengan nama berbeda)
$base = "base_${FileMb}mb.bin"
$basePath = Join-Path $root $base
if (-not (Test-Path $basePath)) {
  Write-Host "Membuat $base ..."
  $fs  = [IO.File]::OpenWrite($basePath)
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  $buf = New-Object byte[] (1MB)
  for ($i = 0; $i -lt $FileMb; $i++) { $rng.GetBytes($buf); $fs.Write($buf, 0, $buf.Length) }
  $fs.Close()
}

$startAll = Get-Date
foreach ($n in $Nodes) {
  $cf = $composeFor[$n]
  if (-not $cf) { Write-Host "Ukuran cluster $n tidak punya file Compose, dilewati."; continue }

  foreach ($st in $Strategies) {
    for ($rep = 1; $rep -le $Repeat; $rep++) {
    $suffix = if ($Repeat -gt 1) { "_run$rep" } else { "" }
    $sk    = "{0}_rf{1}_c{2}_n{3}{4}" -f $short[$st], $Rf, $ChunkMb, $n, $suffix
    $upCsv = Join-Path $dataDir "upload_download_$sk.csv"
    if ((Test-Path $upCsv) -and -not $Force) { Write-Host "[$sk] sudah ada, dilewati (pakai -Force untuk ulang)"; continue }

    Write-Host ""
    Write-Host "=== Skenario $sk ($Files file @ $FileMb MB) ===" -ForegroundColor Cyan

    # 1. Mulai dari kondisi bersih
    Run "docker compose -f $cleanupCompose down -v --remove-orphans" | Out-Null
    Remove-Item (Join-Path $resDir 'client_metrics.csv') -ErrorAction SilentlyContinue
    Run "docker compose -f $cf up -d" | Out-Null

    # 2. Tunggu semua node terdaftar
    $ok = $false
    for ($t = 0; $t -lt 40; $t++) {
      $reg = @(Run "docker logs silifs-master" | Select-String 'node terdaftar').Count
      if ($reg -ge $n) { $ok = $true; break }
      Start-Sleep -Seconds 2
    }
    if (-not $ok) { Write-Host "[$sk] node tidak lengkap terdaftar, skenario dilewati" -ForegroundColor Red; continue }

    # 3. Upload
    $fail = 0
    $t0 = Get-Date
    for ($i = 1; $i -le $Files; $i++) {
      $name = "f{0:D3}.bin" -f $i
      $out = (Run "docker compose -f $cf run --rm --no-deps client upload /work/$base --rf $Rf --chunk-mb $ChunkMb --strategy $st --filename $name") -join "`n"
      if ($out -notmatch 'BERHASIL') { $fail++; Write-Host "  upload $name GAGAL" -ForegroundColor Yellow }
      if ($i % 10 -eq 0) { Write-Host "  upload $i/$Files" }
    }
    $totalS = ((Get-Date) - $t0).TotalSeconds
    Write-Host ("  upload selesai: {0} gagal, total {1:N1} detik" -f $fail, $totalS)

    $metrics = Join-Path $resDir 'client_metrics.csv'
    if (Test-Path $metrics) { Copy-Item $metrics $upCsv -Force }

    # 4. Sebaran chunk per node (hapus baris lama skenario ini jika ada)
    Remove-ScenarioRows $lbCsv $sk
    for ($i = 1; $i -le $n; $i++) {
      $c = ((Run "docker exec silifs-datanode$i sh -c `"ls /app/data/node$i | wc -l`"") -join '').Trim()
      Add-Content -Path $lbCsv -Value ("{0},{1},{2},{3},{4},node{5},{6}" -f $sk, $st, $Rf, $ChunkMb, $n, $i, $c) -Encoding ascii
    }

    # 5. Matikan satu node, ukur deteksi dan pemulihan
    $killed = "node$KillIndex"
    Run "docker kill silifs-datanode$KillIndex" | Out-Null
    $tKill = [DateTimeOffset]::UtcNow
    $det = $null; $rec = $null; $expectedTotal = $null
    $otherDeadEarly = @(); $otherDeadDuring = @()
    for ($t = 0; $t -lt 120; $t++) {
      Start-Sleep -Seconds 2
      $lines = @(Run "docker logs --timestamps silifs-master")
      $detIdx = -1
      for ($idx = 0; $idx -lt $lines.Count; $idx++) {
        if ($lines[$idx] -match "NODE MATI terdeteksi: $killed\b") {
          $detIdx = $idx
          $det = $lines[$idx]
          break
        }
      }
      if ($detIdx -ge 0) {
        # Cari jumlah chunk target re-replication khusus untuk $killed
        if ($null -eq $expectedTotal) {
          for ($idx = $detIdx; $idx -lt $lines.Count; $idx++) {
            if ($lines[$idx] -match "re-replication: (\d+) chunk perlu dipulihkan \(node mati: $killed\)") {
              $expectedTotal = [int]$Matches[1]
              break
            }
          }
        }
        # Cari baris PEMULIHAN SELESAI SETELAH deteksi $killed yang jumlah totalnya cocok dengan $expectedTotal
        if ($null -ne $expectedTotal) {
          for ($idx = $detIdx + 1; $idx -lt $lines.Count; $idx++) {
            if ($lines[$idx] -match 'PEMULIHAN SELESAI: (\d+)/(\d+) chunk, waktu pemulihan = ([\d\.]+) detik') {
              if ([int]$Matches[2] -eq $expectedTotal) {
                $rec = $lines[$idx]
                break
              }
            }
          }
        }
      }
      if ($det -and $rec) {
        # Catat jika ada node lain yang terdeteksi mati lebih awal atau selama pemulihan
        for ($idx = 0; $idx -lt $lines.Count; $idx++) {
          if ($lines[$idx] -match 'NODE MATI terdeteksi: (node\d+)' -and $Matches[1] -ne $killed) {
            if ($idx -lt $detIdx) { $otherDeadEarly += $Matches[1] } else { $otherDeadDuring += $Matches[1] }
          }
        }
        break
      }
    }
    if ($otherDeadEarly.Count -gt 0) {
      Write-Host ("  PERINGATAN: node lain terdeteksi mati sebelum {0}: {1}" -f $killed, ($otherDeadEarly -join ', ')) -ForegroundColor Yellow
    }
    if ($otherDeadDuring.Count -gt 0) {
      Write-Host ("  PERINGATAN: node lain terdeteksi mati selama pemulihan {0}: {1}" -f $killed, ($otherDeadDuring -join ', ')) -ForegroundColor Yellow
    }
    if ($det -and $rec) {
      $tsPat = '^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,7})?)\d*Z'
      $detS = ''
      if ($det -match $tsPat) {
        $tDet = [DateTimeOffset]::Parse($Matches[1] + 'Z', $inv)
        $detS = ($tDet - $tKill).TotalSeconds.ToString('F3', $inv)
      }
      if ($rec -match 'PEMULIHAN SELESAI: (\d+)/(\d+) chunk, waktu pemulihan = ([\d\.]+) detik') {
        Remove-ScenarioRows $recCsv $sk
        Add-Content -Path $recCsv -Value ("{0},{1},{2},{3},{4},{5},{6},{7},{8}" -f $sk, $st, $Rf, $ChunkMb, $n, $Matches[1], $detS, $Matches[3], $Matches[2]) -Encoding ascii
        Write-Host ("  pemulihan: {0}/{1} chunk, deteksi {2} s, pemulihan {3} s" -f $Matches[1], $Matches[2], $detS, $Matches[3])
      }
    } else {
      Write-Host "  log pemulihan tidak ditemukan dalam 240 detik" -ForegroundColor Yellow
    }

    # 6. Simpan log master
    (Run "docker logs --timestamps silifs-master") | Set-Content -Path (Join-Path $logDir "master_$sk.txt") -Encoding ascii
    }
  }
}

Run "docker compose -f $cleanupCompose down -v --remove-orphans" | Out-Null
Write-Host ""
Write-Host ("Selesai dalam {0:N1} menit. Hasil di experiments\data" -f ((Get-Date) - $startAll).TotalMinutes) -ForegroundColor Green