# Arranca Agent City 3D en local (solo lectura) y abre el navegador.
# Uso: powershell -ExecutionPolicy Bypass -File .\start-agent-city-3d.ps1
$ErrorActionPreference = 'Stop'
$node = Join-Path $env:USERPROFILE 'tools\node\node.exe'
if (-not (Test-Path $node)) { $node = 'node' }
$puerto = 8787
$app = Split-Path -Parent $MyInvocation.MyCommand.Path
$ya = Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue
if (-not $ya) {
  Start-Process -FilePath $node -ArgumentList 'server.js' -WorkingDirectory $app -WindowStyle Minimized
  Start-Sleep -Seconds 2
}
Start-Process "http://127.0.0.1:$puerto/"
Write-Output "Agent City 3D: http://127.0.0.1:$puerto/"
