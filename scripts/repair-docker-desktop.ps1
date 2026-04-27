param()

$ErrorActionPreference = "Stop"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Please run this script in an Administrator PowerShell window."
    }
}

function Resolve-InstallerPath {
    $candidates = @(
        "C:\Users\pc\AppData\Local\Temp\DockerDesktopInstaller.exe",
        "C:\Users\pc\Downloads\Docker Desktop Installer.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "Docker Desktop installer not found in the expected locations."
}

Assert-Admin

$installerPath = Resolve-InstallerPath
$dockerDataPath = "C:\ProgramData\DockerDesktop"

Write-Host "Using installer:" $installerPath

if (Test-Path $dockerDataPath) {
    Write-Host "Repairing permissions on $dockerDataPath ..."
    takeown /F $dockerDataPath /A /R /D Y | Out-Null
    icacls $dockerDataPath /setowner "*S-1-5-32-544" /T /C | Out-Null
    icacls $dockerDataPath /grant "*S-1-5-32-544:(OI)(CI)F" /T /C | Out-Null
}

Write-Host "Updating WSL ..."
try {
    wsl --update
}
catch {
    Write-Warning "WSL update failed. Continue after checking whether WSL is installed correctly."
}

Write-Host "Launching Docker Desktop installer ..."
Start-Process -FilePath $installerPath -Verb RunAs -Wait

Write-Host ""
Write-Host "After the installer finishes, restart PowerShell and run:"
Write-Host "  docker version"
Write-Host "  docker compose config"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 compose-config"
