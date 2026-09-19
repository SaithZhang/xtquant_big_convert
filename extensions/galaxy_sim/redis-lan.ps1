[CmdletBinding()]
param([ValidateSet('Prepare','Firewall','Lan','Stop','Status')][string]$Mode = 'Status')
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$privateDir = Join-Path $root '.local\redis-lan'
$settings = Get-Content -LiteralPath (Join-Path $privateDir 'settings.json') -Raw | ConvertFrom-Json
$port = [int]$settings.port
$address = [string]$settings.host
$ruleName = 'BigQmtGalaxyRedisLAN'
$serviceName = 'BigQmtGalaxyRedis'
$version = '7.4.11'
$archiveName = "Redis-$version-Windows-x64-cygwin-with-Service"
$expectedHash = '2289eca02c25e96a918812c3b05083c3a8bc9440f1b268cc48e14bd93ed2acb0'
$native = Join-Path $privateDir 'native'
$archive = Join-Path $native "$archiveName.zip"
$installDir = Join-Path $native "$version\$archiveName"
$exe = Join-Path $installDir 'RedisService.exe'
$configFile = Join-Path $privateDir 'redis.conf'
$dataDir = Join-Path $privateDir 'service-data'
if ($Mode -eq 'Prepare') {
    New-Item -ItemType Directory -Force -Path $native | Out-Null
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/redis-windows/redis-windows/releases/download/$version/$archiveName.zip" -OutFile $archive
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Redis release SHA256 mismatch.' }
    if (-not (Test-Path -LiteralPath $installDir)) {
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $native $version)
    }
    Write-Output "Windows Redis $version prepared; release SHA256 verified."
    return
}
if ($Mode -eq 'Status') {
    Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    return
}
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Run Firewall/Lan/Stop modes from an administrator PowerShell.' }
if ($Mode -eq 'Firewall') {
    $interface = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $address
    $network = Get-NetConnectionProfile -InterfaceIndex $interface.InterfaceIndex
    if ($network.NetworkCategory -ne 'Private') { throw 'LAN interface must already be Private; review Windows settings.' }
    # Explicit interface subnet; never infer trust from all private address space.
    $bytes = ([Net.IPAddress]::Parse($address)).GetAddressBytes()
    $prefix = [int]$interface.PrefixLength
    for ($i=0; $i -lt 4; $i++) {
        $bits = [Math]::Max(0, [Math]::Min(8, $prefix - 8*$i))
        $bytes[$i] = $bytes[$i] -band (256 - [Math]::Pow(2,8-$bits))
    }
    $subnet = ([Net.IPAddress]::new($bytes)).ToString() + '/' + $prefix
    Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -Name $ruleName -DisplayName 'Big QMT Redis - trusted LAN only' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -LocalAddress $address -RemoteAddress $subnet -Profile Private | Out-Null
    Write-Output 'Scoped Private-profile Redis firewall rule configured.'
    return
}
if ($Mode -eq 'Stop') { Stop-Service -Name $serviceName; return }
if ($Mode -eq 'Lan') {
    $profile = Get-NetFirewallProfile -Name Private -PolicyStore ActiveStore
    if (-not $profile.Enabled -or $profile.DefaultInboundAction -ne 'Block') { throw 'LAN publishing requires enabled Private firewall with default inbound Block.' }
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if (-not $rule -or $rule.Enabled -ne 'True' -or $rule.Action -ne 'Allow' -or $rule.Profile -ne 'Private') { throw 'Configure and verify the scoped firewall rule first.' }
    $filter = $rule | Get-NetFirewallPortFilter
    $addresses = $rule | Get-NetFirewallAddressFilter
    if ($filter.LocalPort -ne "$port" -or $addresses.LocalAddress -notcontains $address -or $addresses.RemoteAddress -contains 'Any') { throw 'Firewall rule does not match private configuration.' }
}
if (-not (Test-Path -LiteralPath $exe)) { throw 'Run Prepare first.' }
# Check the archive and installed binaries together to detect local drift.
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Redis release SHA256 mismatch.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    foreach ($entry in $zip.Entries | Where-Object { $_.Name -match '\.(exe|dll)$' }) {
        $disk = Join-Path (Split-Path $installDir -Parent) $entry.FullName
        $stream = $entry.Open()
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
        finally { $stream.Dispose(); $sha.Dispose() }
        if ((Get-FileHash -LiteralPath $disk -Algorithm SHA256).Hash -ne $hash) { throw 'Installed Redis binary differs from verified archive.' }
    }
} finally { $zip.Dispose() }
$lines = Get-Content -LiteralPath $configFile
if ($lines -notcontains "bind 127.0.0.1 $address" -or $lines -notcontains "port $port" -or
    $lines -notcontains 'protected-mode yes' -or $lines -notcontains ('requirepass ' + $settings.password)) {
    throw 'Private Redis config does not match the authenticated LAN settings.'
}
$existing = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
if ($existing -and (-not $existing.PathName.Contains($exe) -or -not $existing.PathName.Contains($configFile))) {
    throw 'Existing service is not owned by this checkout.'
}
if ($existing -and $existing.State -eq 'Running') { Stop-Service -Name $serviceName }
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
# The service runs without administrator rights. Only its data directory is writable.
& icacls.exe $installDir /grant '*S-1-5-19:(OI)(CI)RX' /T /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not grant LocalService binary access.' }
& icacls.exe $configFile /grant '*S-1-5-19:R' /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not grant LocalService config access.' }
& icacls.exe $dataDir /grant '*S-1-5-19:(OI)(CI)M' /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not grant LocalService data access.' }
if (-not $existing) {
    & $exe install --service-name $serviceName --display-name 'Big QMT Galaxy Redis' --start-mode auto -c $configFile --dir $dataDir
    if ($LASTEXITCODE -ne 0) { throw 'Windows Redis service installation failed.' }
    # The upstream installer starts the service automatically.
    Stop-Service -Name $serviceName
}
& sc.exe config $serviceName obj= 'NT AUTHORITY\LocalService' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not configure LocalService identity.' }
Set-Service -Name $serviceName -StartupType Automatic
Start-Service -Name $serviceName
(Get-Service -Name $serviceName).WaitForStatus('Running', [TimeSpan]::FromSeconds(15))
Write-Output "Windows Redis $version service started. Credentials remain in .local."
