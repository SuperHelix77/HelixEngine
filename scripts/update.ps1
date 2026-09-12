param(
    [string]$WheelPath,
    [switch]$Offline,
    [switch]$NoShortcut,
    [string]$VenvPath
)

$ErrorActionPreference = "Stop"
$installUrl = "https://raw.githubusercontent.com/SuperHelix77/HelixEngine/v0.1.0/scripts/install.ps1"

# A checkout can call its sibling directly.  When this file is piped through
# Invoke-Expression, PSScriptRoot is unavailable, so fetch the pinned helper.
if ($PSScriptRoot) {
    $localInstaller = Join-Path $PSScriptRoot "install.ps1"
    if (Test-Path -LiteralPath $localInstaller -PathType Leaf) {
        & $localInstaller -WheelPath $WheelPath -Offline:$Offline -NoShortcut:$NoShortcut -VenvPath $VenvPath
        exit $LASTEXITCODE
    }
}

$installerText = Invoke-RestMethod -Uri $installUrl
$installer = [scriptblock]::Create([string]$installerText)
& $installer -WheelPath $WheelPath -Offline:$Offline -NoShortcut:$NoShortcut -VenvPath $VenvPath
exit $LASTEXITCODE
