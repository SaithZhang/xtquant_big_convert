[CmdletBinding()]
param(
    [string]$QmtRoot = 'D:\银河证券QMT测试 - 交易终端',
    [switch]$Legacy,
    [switch]$ZmqRollback,
    [string]$LanAddress
)
$ErrorActionPreference = 'Stop'
if (-not $Legacy -and -not $ZmqRollback) {
    Push-Location $PSScriptRoot
    try {
        $arguments = @('-m', 'extensions.galaxy_sim.redis_package', '--qmt-root', $QmtRoot)
        if ($LanAddress) { $arguments += @('--host', $LanAddress) }
        & "$PSScriptRoot\.venv\Scripts\python.exe" @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Redis package deployment failed.' }
    } finally { Pop-Location }
    return
}
function Get-Sha256([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
$filename = if ($Legacy) { 'BIGQMT_GATEWAY.py' } else { 'BIGQMT_GALAXY_SIM.py' }
if ($Legacy) {
    $source = Join-Path $PSScriptRoot "qmt\$filename"
} else {
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Create .venv first; see FORK.md.' }
    Push-Location $PSScriptRoot
    try {
        & $python -m extensions.galaxy_sim.build
        if ($LASTEXITCODE -ne 0) { throw 'Galaxy build failed.' }
    } finally { Pop-Location }
    $source = Join-Path $PSScriptRoot "build\$filename"
}
$targetDir = Join-Path $QmtRoot 'python'
$target = Join-Path $targetDir $filename
if (-not (Test-Path -LiteralPath (Join-Path $targetDir '_PyContextInfo.py') -PathType Leaf)) {
    throw "Not a recognized Big QMT python directory: $targetDir"
}
if ((Get-Item -LiteralPath $targetDir).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Refusing a redirected QMT python directory.'
}
$sourceHash = Get-Sha256 $source
if (Test-Path -LiteralPath $target) {
    if ((Get-Sha256 $target) -eq $sourceHash) {
        Write-Output "Already deployed (SHA256 verified): $target"
        return
    }
    # Never overwrite an existing QMT/user file, even one with this name.
    throw "Target already exists with different contents. Stop the gateway and rename that file manually before deployment: $target"
}
$inputStream = [IO.File]::OpenRead($source)
try {
    $outputStream = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
} finally { $inputStream.Dispose() }
if ((Get-Sha256 $target) -ne $sourceHash) {
    throw "SHA256 mismatch: $target"
}
Write-Output "Deployed (SHA256 verified): $target"
Write-Output 'Next: open this file in the QMT strategy editor and click Run; native/standalone Python OFF.'
