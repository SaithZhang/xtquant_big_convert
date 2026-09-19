[CmdletBinding()]
param([ValidateSet('Local','Firewall','Lan','Stop')][string]$Mode = 'Local')
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$privateDir = Join-Path $root '.local\redis-lan'
$settings = Get-Content -LiteralPath (Join-Path $privateDir 'settings.json') -Raw | ConvertFrom-Json
$port = [int]$settings.port
$address = [string]$settings.host
$ruleName = 'BigQmtGalaxyRedisLAN'
if ($Mode -eq 'Firewall') {
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) { throw 'Run this Firewall mode from an administrator PowerShell.' }
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
if ($Mode -eq 'Stop') { & docker stop galaxy-qmt-redis; exit $LASTEXITCODE }
if ($Mode -eq 'Lan') {
    $profile = Get-NetFirewallProfile -Name Private -PolicyStore ActiveStore
    if (-not $profile.Enabled -or $profile.DefaultInboundAction -ne 'Block') { throw 'LAN publishing requires enabled Private firewall with default inbound Block.' }
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if (-not $rule -or $rule.Enabled -ne 'True' -or $rule.Action -ne 'Allow' -or $rule.Profile -ne 'Private') { throw 'Configure and verify the scoped firewall rule first.' }
    $filter = $rule | Get-NetFirewallPortFilter
    $addresses = $rule | Get-NetFirewallAddressFilter
    if ($filter.LocalPort -ne "$port" -or $addresses.LocalAddress -notcontains $address -or $addresses.RemoteAddress -contains 'Any') { throw 'Firewall rule does not match private configuration.' }
}
$names = & docker ps -a --format '{{.Names}}'
if ($names -contains 'galaxy-qmt-redis') {
    $existing = (& docker container inspect galaxy-qmt-redis | ConvertFrom-Json)[0]
    if ($existing.Config.Labels.'galaxy.owner' -ne 'xtquant-big-convert') { throw 'Container name is owned by another application.' }
    & docker rm -f galaxy-qmt-redis | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not replace owned Redis container.' }
}
$arguments = @('run','-d','--name','galaxy-qmt-redis','--label','galaxy.owner=xtquant-big-convert','--restart','unless-stopped','-p',"127.0.0.1:${port}:6379")
if ($Mode -eq 'Lan') { $arguments += @('-p',"${address}:${port}:6379") }
$arguments += @('--mount',"type=bind,source=$privateDir\redis.conf,target=/usr/local/etc/redis/redis.conf,readonly",'redis:7.4-alpine','redis-server','/usr/local/etc/redis/redis.conf')
& docker @arguments
if ($LASTEXITCODE -ne 0) { throw 'Redis container failed to start.' }
& docker image inspect redis:7.4-alpine --format '{{json .RepoDigests}}' | Set-Content -LiteralPath (Join-Path $privateDir 'image-digest.json')
Write-Output "Redis started in $Mode mode. Credentials remain in .local."
