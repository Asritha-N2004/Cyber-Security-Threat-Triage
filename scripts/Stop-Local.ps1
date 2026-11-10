$ErrorActionPreference='Stop'
$statePath=Join-Path (Split-Path -Parent $PSScriptRoot) 'backend/.local/processes.json'
if(-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No launcher process record found.'; exit }
foreach($record in (Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json)) {
    $process=Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if($process -and $process.StartTime.ToUniversalTime().Ticks -eq [long]$record.started) { Stop-Process -Id $process.Id }
}
Write-Output 'Stopped the recorded local services.'
