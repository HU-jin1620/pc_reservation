$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not $env:HOST) { $env:HOST = "0.0.0.0" }
if (-not $env:PORT) { $env:PORT = "5000" }

$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}

$outLog = Join-Path $PSScriptRoot "booking.out.log"
$errLog = Join-Path $PSScriptRoot "booking.err.log"

Start-Process -WindowStyle Hidden `
    -FilePath $python `
    -ArgumentList "app.py" `
    -WorkingDirectory $PSScriptRoot `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

$lanIp = $null
$candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.IPAddress -ne '0.0.0.0'
    }
if ($candidates) {
    $gwIf = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty InterfaceIndex -Unique)
    $preferred = $candidates | Where-Object { $gwIf -contains $_.InterfaceIndex }
    if ($preferred) {
        $lanIp = ($preferred | Select-Object -First 1).IPAddress
    } else {
        $lanIp = ($candidates | Select-Object -First 1).IPAddress
    }
}

Write-Host ""
Write-Host "服务已后台启动："
Write-Host "  本机访问：   http://127.0.0.1:$($env:PORT)/"
if ($lanIp) {
    Write-Host "  局域网访问： http://${lanIp}:$($env:PORT)/"
} else {
    Write-Host "  局域网访问： 未能自动获取，请运行 ipconfig 查看 IPv4 地址"
}
Write-Host ""
Write-Host "日志：booking.out.log / booking.err.log"
Write-Host "关闭本窗口不会停止服务；停止请运行 stop.bat 或 stop.ps1"
