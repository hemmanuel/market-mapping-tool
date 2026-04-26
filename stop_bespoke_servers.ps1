Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\bespoke_servers_common.ps1"

$stopFrontendCommand = @'
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

$stopBackendCommand = @'
pid_file='.server-state/pids/backend.pid'
if [ -f "$pid_file" ]; then
  pid=$(cat "$pid_file")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for i in {1..20}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "Stopped backend PID $pid."
  else
    echo "Removed stale backend PID file."
  fi
  rm -f "$pid_file"
else
  echo "No managed backend PID file found."
fi
'@

$repoInfo = Resolve-WslRepoInfo -WindowsRepoPath $PSScriptRoot
$stateDir = Join-Path $PSScriptRoot ".server-state"
$pidDir = Join-Path $stateDir "pids"
$logDir = Join-Path $stateDir "logs"
$stopLog = Join-Path $logDir "stop_bespoke_servers.log"
$frontendPidFile = Join-Path $pidDir "frontend.pid"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Content -Path $stopLog -Value "[$(Get-Date -Format s)] Stopping bespoke services from $($repoInfo.WindowsPath)"

try {
    Write-Host "Stopping bespoke frontend..."
    if (Test-Path $frontendPidFile) {
        $frontendPidText = ((Get-Content -Path $frontendPidFile | Select-Object -First 1) -join "").Trim()
        if ($frontendPidText) {
            try {
                Stop-Process -Id ([int]$frontendPidText) -Force -ErrorAction Stop
                Write-Host "Stopped frontend host PID $frontendPidText."
            } catch {
                Write-Host "Removed stale frontend PID file."
            }
        } else {
            Write-Host "Removed empty frontend PID file."
        }
        Remove-Item -Path $frontendPidFile -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "No managed frontend PID file found."
    }
    Invoke-WslInRepo -Distro $repoInfo.Distro -RepoPath $repoInfo.WslPath -Command $stopFrontendCommand -LogPath $stopLog

    Write-Host "Stopping bespoke backend..."
    Invoke-WslInRepo -Distro $repoInfo.Distro -RepoPath $repoInfo.WslPath -Command $stopBackendCommand -LogPath $stopLog

    Write-Host "Stopping bespoke data plane..."
    Invoke-WslInRepo -Distro $repoInfo.Distro -RepoPath $repoInfo.WslPath -Command "./scripts/stop_bespoke_stack.sh" -LogPath $stopLog

    Write-Host ""
    Write-Host "Bespoke services are stopped."
    Write-Host "Log: $stopLog"
    exit 0
} catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)"
    Write-Host "Full stop log: $stopLog"
    exit 1
}
