$ErrorActionPreference = "SilentlyContinue"

$port = if ($env:PORT) { $env:PORT } else { "5000" }
$listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue

if (-not $listeners) {
    Write-Host "端口 $port 上没有正在运行的服务。"
    exit 0
}

$procIds = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $procIds) {
    Stop-Process -Id $procId -Force
    Write-Host "已停止进程 PID $procId。"
}

