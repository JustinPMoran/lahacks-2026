$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$RepoPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
Set-Location $ScriptDir

function Ensure-UserPathContains {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Directory
    )

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) {
        $userPath = ""
    }

    if ($userPath -notlike "*$Directory*") {
        $newUserPath = if ($userPath) { "$userPath;$Directory" } else { $Directory }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
        Write-Host "Added mpv directory to user PATH: $Directory"
    }
}

function Resolve-MpvPath {
    $candidatePaths = @(
        (Get-Command mpv -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\mpv.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\mpv\mpv.exe"),
        "C:\Program Files\MPV Player\mpv.exe",
        "C:\Program Files\mpv\mpv.exe",
        "C:\Program Files (x86)\mpv\mpv.exe"
    ) | Where-Object { $_ }

    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            return (Split-Path -Parent $candidate)
        }
    }

    return $null
}

function Ensure-Mpv {
    $mpvDir = Resolve-MpvPath
    if ($mpvDir) {
        Ensure-UserPathContains -Directory $mpvDir
        if ($env:Path -notlike "*$mpvDir*") {
            $env:Path = "$mpvDir;$env:Path"
        }
        return
    }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "mpv not found. Attempting to install it with winget..."
        winget install --id shinchiro.mpv --exact --source winget --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Automatic mpv install failed. Install it manually:"
            Write-Host "Windows download: https://mpv.io/installation/"
            exit $LASTEXITCODE
        }
    }

    $mpvDir = Resolve-MpvPath
    if ($mpvDir) {
        Ensure-UserPathContains -Directory $mpvDir
        if ($env:Path -notlike "*$mpvDir*") {
            $env:Path = "$mpvDir;$env:Path"
        }
        return
    }

    if (-not (Get-Command mpv -ErrorAction SilentlyContinue)) {
        Write-Host "mpv not found on PATH. Install it and rerun this script."
        Write-Host "Windows download: https://mpv.io/installation/"
        exit 1
    }
}

Ensure-Mpv

if (-not (Test-Path $RepoPython)) {
    python -m venv (Join-Path $RepoRoot ".venv")
}

& $RepoPython -m pip install --upgrade pip
& $RepoPython -m pip install -r (Join-Path $RepoRoot "requirements.txt") -r (Join-Path $ScriptDir "requirements.txt")

Write-Host "Setup complete. Activate with: .\\..\\.venv\\Scripts\\Activate.ps1"
Write-Host "Then run: python main.py --trigger manual"