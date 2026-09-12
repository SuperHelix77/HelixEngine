param(
    [string]$VenvPath
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    if ($env:HELIXENGINE_VENV) {
        $VenvPath = $env:HELIXENGINE_VENV
    } else {
        $VenvPath = Join-Path $env:USERPROFILE ".helixengine-venv"
    }
}

$venvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Helix Engine venv not found: $VenvPath. User data was not touched."
}
& $venvPython -m pip uninstall --yes helixengine
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$shell = New-Object -ComObject WScript.Shell
$desktopDir = $shell.SpecialFolders.Item("Desktop")
$shortcutPath = Join-Path $desktopDir "Helix Engine.lnk"
$arguments = "-m helixengine serve --port 8769 --open"
if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
    try {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $owned = [StringComparer]::OrdinalIgnoreCase.Equals([string]$shortcut.TargetPath, [string]$venvPython) -and
            ([string]$shortcut.Arguments).Trim() -eq $arguments
    } catch {
        $owned = $false
    }
    if ($owned) {
        Remove-Item -LiteralPath $shortcutPath
        Write-Host "Removed $shortcutPath"
    }
}

Write-Host "Package removed from $VenvPath; the virtual environment and $env:USERPROFILE\.helixengine user data were preserved."
