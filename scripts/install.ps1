param(
    [string]$WheelPath,
    [switch]$Offline,
    [switch]$NoShortcut,
    [string]$VenvPath
)

$ErrorActionPreference = "Stop"
$releaseWheelUrl = "https://github.com/SuperHelix77/HelixEngine/releases/download/v0.1.0/helixengine-0.1.0-py3-none-any.whl"

if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    if ($env:HELIXENGINE_VENV) {
        $VenvPath = $env:HELIXENGINE_VENV
    } else {
        $VenvPath = Join-Path $env:USERPROFILE ".helixengine-venv"
    }
}

$pythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "py" }
$venvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $bootstrapArgs = @()
    if (-not $env:PYTHON_BIN) {
        $bootstrapArgs += "-3"
    }
    & $pythonBin @bootstrapArgs -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Virtual environment has no executable: $venvPython"
}

$source = $releaseWheelUrl
if (-not [string]::IsNullOrWhiteSpace($WheelPath)) {
    if (-not (Test-Path -LiteralPath $WheelPath -PathType Leaf)) {
        throw "Wheel does not exist: $WheelPath"
    }
    $source = (Resolve-Path -LiteralPath $WheelPath).ProviderPath
}
if ($Offline) {
    if ([string]::IsNullOrWhiteSpace($WheelPath)) {
        throw "-Offline requires -WheelPath pointing to a local wheel"
    }
    $wheelDir = Split-Path -Parent $source
    & $venvPython -m pip install --no-index --find-links $wheelDir --upgrade $source
} else {
    & $venvPython -m pip install --upgrade $source
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

function Backup-ExistingShortcut {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    $backup = "$Path.backup-$stamp"
    $index = 0
    while (Test-Path -LiteralPath $backup) {
        $index++
        $backup = "$Path.backup-$stamp-$index"
    }
    Move-Item -LiteralPath $Path -Destination $backup
    Write-Host "Preserved existing desktop shortcut as $backup"
}

function New-HelixDesktopShortcut {
    $shell = New-Object -ComObject WScript.Shell
    $desktopDir = $shell.SpecialFolders.Item("Desktop")
    if ([string]::IsNullOrWhiteSpace($desktopDir)) {
        throw "Windows Desktop folder could not be resolved"
    }
    $shortcutPath = Join-Path $desktopDir "Helix Engine.lnk"
    $arguments = "-m helixengine serve --port 8769 --open"
    $same = $false
    if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
        try {
            $existing = $shell.CreateShortcut($shortcutPath)
            $same = ([StringComparer]::OrdinalIgnoreCase.Equals([string]$existing.TargetPath, [string]$venvPython) -and
                ([string]$existing.Arguments).Trim() -eq $arguments)
        } catch {
            $same = $false
        }
        if (-not $same) {
            Backup-ExistingShortcut $shortcutPath
        }
    }
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $venvPython
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $env:USERPROFILE
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Host "Created $shortcutPath"
}

if (-not $NoShortcut) {
    New-HelixDesktopShortcut
}

Write-Host "Installed helixengine 0.1.0 in $VenvPath"
Write-Host "Run: $venvPython -m helixengine --help"
