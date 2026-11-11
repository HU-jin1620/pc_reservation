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

Write-Host "已后台启动：http://$($env.HOST):$($env:PORT)/"
Write-Host "日志：booking.out.log / booking.err.log"
Write-Host "关闭本窗口不会停止服务；停止请运行 stop.bat 或 stop.ps1"

