Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ResolvedProviderPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $providerPath = (Resolve-Path -LiteralPath $Path).ProviderPath
    if ($providerPath -match '^[A-Za-z]:\\') {
        $driveName = $providerPath.Substring(0, 1)
        $psDrive = Get-PSDrive -Name $driveName -PSProvider FileSystem
        if ($psDrive -and $psDrive.DisplayRoot) {
            $relativePath = $providerPath.Substring(2).TrimStart('\')
            if ($relativePath) {
                $providerPath = $psDrive.DisplayRoot.TrimEnd('\') + '\' + $relativePath
            } else {
                $providerPath = $psDrive.DisplayRoot
            }
        }
    }

    return $providerPath
}

function Resolve-WslRepoInfo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WindowsRepoPath
    )

    $providerPath = Get-ResolvedProviderPath -Path $WindowsRepoPath
    $match = [regex]::Match(
        $providerPath,
        '^(?<root>\\\\wsl(?:\.localhost|\$)\\(?<distro>[^\\]+))(?<rest>\\.*)?$',
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )

    if (-not $match.Success) {
        throw "Could not resolve a WSL repo path from '$providerPath'."
    }

    $repoPathPart = $match.Groups["rest"].Value
    $wslRepoPath = if ([string]::IsNullOrWhiteSpace($repoPathPart)) {
        "/"
    } else {
        ($repoPathPart -replace '\\', '/').TrimEnd('/')
    }

    [pscustomobject]@{
        WindowsPath = $providerPath
        Distro = $match.Groups["distro"].Value
        WslPath = $wslRepoPath
    }
}

function Quote-BashString {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $singleQuoteEscape = "'" + '"' + "'" + '"' + "'"
    return "'" + ($Value -replace "'", $singleQuoteEscape) + "'"
}

function Invoke-WslInRepo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Distro,
        [Parameter(Mandatory = $true)]
        [string]$RepoPath,
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string]$LogPath
    )

    $normalizedCommand = ($Command -replace "`r", "").Trim()
    $bashScript = @(
        "set -euo pipefail"
        "cd $(Quote-BashString $RepoPath)"
        $normalizedCommand
        ""
    ) -join "`n"

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "wsl.exe"
    $startInfo.Arguments = "-d $Distro bash -s --"
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo

    try {
        $process.Start() | Out-Null
        $process.StandardInput.Write($bashScript)
        $process.StandardInput.Close()

        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()

        $output = @()
        if ($stdout) {
            $output += ($stdout -split "\r?\n" | Where-Object { $_ -ne "" })
        }
        if ($stderr) {
            $output += ($stderr -split "\r?\n" | Where-Object { $_ -ne "" })
        }

        if ($LogPath) {
            $parentDir = Split-Path -Parent $LogPath
            if ($parentDir) {
                New-Item -ItemType Directory -Force -Path $parentDir | Out-Null
            }
            if ($output.Count -gt 0) {
                $output | Tee-Object -FilePath $LogPath -Append
            } else {
                Add-Content -Path $LogPath -Value ""
            }
        } elseif ($output.Count -gt 0) {
            $output | ForEach-Object { Write-Host $_ }
        }

        if ($process.ExitCode -ne 0) {
            throw "WSL command failed with exit code $($process.ExitCode): $Command"
        }
    } finally {
        $process.Dispose()
    }
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $asyncResult = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        $connected = $asyncResult.AsyncWaitHandle.WaitOne(500)
        if (-not $connected) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Wait-ForPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [int]$TimeoutSeconds = 60
    )

    Write-Host "Waiting for $Name on port $Port..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -Port $Port) {
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "$Name did not open port $Port within $TimeoutSeconds seconds."
}
