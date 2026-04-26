Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\bespoke_servers_common.ps1"

$backendStartCommand = @'
mkdir -p '.server-state/pids' '.server-state/logs'
pid_file='.server-state/pids/backend.pid'
if [ -f "$pid_file" ]; then
  old_pid=$(cat "$pid_file")
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "Backend already running with PID $old_pid."
    exit 0
  fi
  rm -f "$pid_file"
fi
nohup ./scripts/run_bespoke_backend.sh > '.server-state/logs/backend.log' 2>&1 &
echo $! > "$pid_file"
'@

$stopStrayFrontendCommand = @'
repo_frontend_root="$(pwd)/frontend"
stray_pids=$(pgrep -f "$repo_frontend_root/node_modules/.bin/next dev" || true)
if [ -n "$stray_pids" ]; then
  for pid in $stray_pids; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      for i in {1..20}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      echo "Stopped stray frontend PID $pid."
    fi
  done
fi
'@

$repoInfo = Resolve-WslRepoInfo -WindowsRepoPath $PSScriptRoot
$stateDir = Join-Path $PSScriptRoot ".server-state"
$pidDir = Join-Path $stateDir "pids"
$logDir = Join-Path $stateDir "logs"
$startLog = Join-Path $logDir "start_bespoke_servers.log"
$frontendPidFile = Join-Path $pidDir "frontend.pid"
$frontendLog = Join-Path $logDir "frontend.log"

New-Item -ItemType Directory -Force -Path $pidDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Content -Path $startLog -Value "[$(Get-Date -Format s)] Starting bespoke services from $($repoInfo.WindowsPath)"

try {
    Write-Host "Starting bespoke data plane..."
    Invoke-WslInRepo -Distro $repoInfo.Distro -RepoPath $repoInfo.WslPath -Command "./scripts/start_bespoke_stack.sh" -LogPath $startLog

    Wait-ForPort -Port 55432 -Name "Bespoke PostgreSQL"
    Wait-ForPort -Port 17687 -Name "Bespoke Neo4j"
    Wait-ForPort -Port 19000 -Name "Bespoke MinIO"

    Write-Host "Applying bespoke database migrations..."
    Invoke-WslInRepo -Distro $repoInfo.Distro -RepoPath $repoInfo.WslPath -Command "./scripts/migrate_bespoke_db.sh" -LogPath $startLog

    Write-Host "Starting bespoke backend..."
    Invoke-WslInRepo -Distro $repoInfo.Distro -RepoPath $repoInfo.WslPath -Command $backendStartCommand -LogPath $startLog
    Wait-ForPort -Port 8100 -Name "Bespoke backend"

    Write-Host "Starting bespoke frontend..."
    $shouldStartFrontend = $true
    if (Test-Path $frontendPidFile) {
        $existingPidText = ((Get-Content -Path $frontendPidFile | Select-Object -First 1) -join "").Trim()
        if ($existingPidText) {
            try {
                $null = Get-Process -Id ([int]$existingPidText) -ErrorAction Stop
                Write-Host "Managed frontend host already running with PID $existingPidText."
                $shouldStartFrontend = $false
            } catch {
                Remove-Item -Path $frontendPidFile -Force -ErrorAction SilentlyContinue
            }
        } else {
            Remove-Item -Path $frontendPidFile -Force -ErrorAction SilentlyContinue
        }
    }

    if ($shouldStartFrontend) {
        Invoke-WslInRepo -Distro $repoInfo.Distro -RepoPath $repoInfo.WslPath -Command $stopStrayFrontendCommand -LogPath $startLog
        Set-Content -Path $frontendLog -Value ""
        $frontendCommand = "set -euo pipefail; cd $(Quote-BashString $repoInfo.WslPath); exec ./scripts/run_bespoke_frontend.sh > .server-state/logs/frontend.log 2>&1"
        $frontendProcess = Start-Process -FilePath "wsl.exe" -ArgumentList @("-d", $repoInfo.Distro, "bash", "-lc", $frontendCommand) -WindowStyle Hidden -PassThru
        Set-Content -Path $frontendPidFile -Value $frontendProcess.Id
    }
    Wait-ForPort -Port 3300 -Name "Bespoke frontend"

    Write-Host ""
    Write-Host "Bespoke services are up."
    Write-Host "Frontend: http://localhost:3300"
    Write-Host "Backend:  http://localhost:8100"
    Write-Host "Neo4j:    http://localhost:17474"
    Write-Host "MinIO:    http://localhost:19001"
    Write-Host "Logs:     $logDir"
    exit 0
} catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)"
    Write-Host "Full startup log: $startLog"
    exit 1
}
