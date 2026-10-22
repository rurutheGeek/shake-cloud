# Wi-Fi AP の比較計測（Windows 端末用）。iperf3 と ping の結果を results.csv へ1行ずつ足す。
#
#   .\measure.ps1 -Ap flint3 -Location ap-room
#   .\measure.ps1 -Ap aterm  -Location far-room -Runs 5
#
# 前提: iperf3.exe に PATH が通っていること（winget install ar51an.iPerf3）。
# Windows PowerShell 5.1 が日本語を読めるよう、このファイルは BOM 付き UTF-8 で保存する。
param(
    [Parameter(Mandatory)][ValidateSet('aterm', 'flint3')][string]$Ap,
    [Parameter(Mandatory)][ValidateSet('ap-room', 'next-room', 'far-room')][string]$Location,
    [string]$Server = '192.168.10.10',
    [int]$Runs = 3,
    [int]$Seconds = 30,
    [int]$Streams = 4,
    [string]$Out = ''
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 では param の既定値の中で $PSScriptRoot が空になる。
if (-not $Out) { $Out = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'results.csv' }

# Tailscale が LAN への経路を広告していると、計測が無線ではなく VPN を通ってしまう。
$route = Find-NetRoute -RemoteIPAddress $Server | Select-Object -First 1
if ($route.InterfaceAlias -match 'Tailscale') {
    throw "$Server への経路が Tailscale を通っています。Tailscale を切断してから実行してください。"
}

# netsh の項目名は表示言語と文字コードで変わるので、項目名ではなく値の形で拾う。
function Get-Wlan {
    $values = @(netsh wlan show interfaces | ForEach-Object {
        if ($_ -match '^\s+\S.*?\s:\s(.*?)\s*$') { $Matches[1] }
    })
    $lines = @(netsh wlan show interfaces)
    function First([string]$pattern) {
        foreach ($value in $values) { if ($value -match $pattern) { return $Matches[1] } }
        return ''
    }
    $rates = @($lines | Where-Object { $_ -match '\(Mbps\)\s*:\s*([\d.]+)' } | ForEach-Object { [regex]::Match($_, ':\s*([\d.]+)\s*$').Groups[1].Value })
    # チャネルは「5 GHz」の行の次にある整数。
    $channel = ''
    for ($i = 0; $i -lt $values.Count - 1; $i++) {
        if ($values[$i] -match '^[\d.]+ GHz$' -and $values[$i + 1] -match '^\d+$') { $channel = $values[$i + 1]; break }
    }
    [ordered]@{
        ssid     = [regex]::Match(($lines -join "`n"), '(?m)^\s+SSID\s+:\s(.*?)\s*$').Groups[1].Value
        bssid    = [regex]::Match(($lines -join "`n"), '(?m)BSSID\s+:\s(.*?)\s*$').Groups[1].Value
        radio    = First '^(802\.11\w+)$'
        band     = First '^([\d.]+ GHz)$'
        channel  = $channel
        rx_mbps  = if ($rates.Count -ge 1) { $rates[0] } else { '' }
        tx_mbps  = if ($rates.Count -ge 2) { $rates[1] } else { '' }
        signal   = First '^(\d+)%$'
        rssi     = [regex]::Match(($lines -join "`n"), '(?mi)^\s+Rssi\s+:\s(-?\d+)').Groups[1].Value
    }
}

function Get-PingMs([int]$count) {
    $ping = New-Object System.Net.NetworkInformation.Ping
    $times = @()
    for ($i = 0; $i -lt $count; $i++) {
        $reply = $ping.Send($Server, 1000)
        if ($reply.Status -eq 'Success') { $times += $reply.RoundtripTime }
        Start-Sleep -Milliseconds 200
    }
    if (-not $times) { return '' }
    [math]::Round(($times | Measure-Object -Average).Average, 1)
}

function Invoke-Iperf([switch]$Reverse) {
    $iperfArgs = @('-c', $Server, '-t', $Seconds, '-P', $Streams, '-J')
    if ($Reverse) { $iperfArgs += '-R' }
    # 負荷中の遅延は、iperf3 を裏で流している間の ping で測る。
    $job = Start-Job { param($a) & iperf3 @a } -ArgumentList (, $iperfArgs)
    Start-Sleep -Seconds 5
    $loaded = Get-PingMs 10
    $json = (Receive-Job $job -Wait -AutoRemoveJob) -join "`n" | ConvertFrom-Json
    if ($json.error) { throw "iperf3: $($json.error)" }
    [pscustomobject]@{
        mbps   = [math]::Round($json.end.sum_received.bits_per_second / 1e6, 1)
        loaded = $loaded
    }
}

# 列が違う古い結果へ追記すると Export-Csv が失敗するので、退避してから始める。
if ((Test-Path $Out) -and ((Get-Content $Out -TotalCount 1) -notmatch 'rssi')) {
    Move-Item $Out ($Out -replace '\.csv$', ('-old-{0}.csv' -f (Get-Date).ToString('HHmmss')))
}

for ($run = 1; $run -le $Runs; $run++) {
    foreach ($direction in 'up', 'down') {
        $wlan = Get-Wlan
        $idle = Get-PingMs 5
        $result = Invoke-Iperf -Reverse:($direction -eq 'down')
        $row = [ordered]@{
            time      = (Get-Date).ToString('s')
            ap        = $Ap
            device    = $env:COMPUTERNAME
            location  = $Location
            direction = $direction
            run       = $run
        } + $wlan + [ordered]@{
            mbps           = $result.mbps
            ping_idle_ms   = $idle
            ping_loaded_ms = $result.loaded
        }
        [pscustomobject]$row | Export-Csv -Path $Out -Append -NoTypeInformation -Encoding utf8
        '{0} {1} run {2}: {3} Mbps (ping {4} -> {5} ms, {6} ch {7}, link {8}/{9} Mbps, rssi {10})' -f $Ap, $direction, $run, $result.mbps, $idle, $result.loaded, $wlan.band, $wlan.channel, $wlan.rx_mbps, $wlan.tx_mbps, $wlan.rssi
    }
}
