param([switch]$Simulation,[switch]$Development,[switch]$TokenAuth)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$backendPath=Join-Path $projectRoot 'backend'
$frontendPath=Join-Path $projectRoot 'frontend'
$statePath=Join-Path $backendPath '.local'
New-Item -ItemType Directory -Force -Path $statePath | Out-Null
$nodeExecutable=(Get-Command node).Source
foreach($port in @(8000,5173)) {
    if(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is already in use. Stop its existing server or use the manual startup instructions." }
}
Push-Location $backendPath
try {
    python -m alembic upgrade head
    if($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
    python -m app.bootstrap
    if($LASTEXITCODE -ne 0) { throw 'Identity initialization failed' }
    if(-not $TokenAuth) {
        $env:LOCAL_DEMO_ORG_ID=python -c "import json; from pathlib import Path; from sqlalchemy import select; from app.database import SessionLocal,User; from app.models_extended import TokenGrant; from app.security import token_hash; data=json.loads(Path('.local/credentials.json').read_text()); db=SessionLocal(); grant=db.scalar(select(TokenGrant).where(TokenGrant.token_hash==token_hash(data['analyst']))); user=db.get(User,grant.user_id) if grant else db.scalar(select(User).where(User.token_hash==token_hash(data['analyst']))); assert user is not None; print(user.org_id); db.close()"
        if($LASTEXITCODE -ne 0) { throw 'Cannot determine the local demo organization' }
        $env:LOCAL_DEMO_MODE='true'
    } else { $env:LOCAL_DEMO_MODE='false' }
} finally { Pop-Location }
if($Simulation) { $env:EXECUTION_MODE='simulation' }
$ownedProcesses=@()
$frontendArgs=if(-not $Development -and (Test-Path -LiteralPath (Join-Path $frontendPath 'dist/index.html'))) {
    @('node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','5173','--strictPort')
} else {
    @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort')
}
$services=@(
    @{name='backend';exe=(Get-Command python).Source;args=@('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000');cwd=$backendPath},
    @{name='worker';exe=(Get-Command python).Source;args=@('-m','app.worker');cwd=$backendPath},
    @{name='frontend';exe=$nodeExecutable;args=$frontendArgs;cwd=$frontendPath}
)
foreach($service in $services) {
    $process=Start-Process -FilePath $service.exe -ArgumentList $service.args -WorkingDirectory $service.cwd -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $statePath ($service.name+'.log')) -RedirectStandardError (Join-Path $statePath ($service.name+'.error.log'))
    $ownedProcesses+=@{name=$service.name;id=$process.Id;started=$process.StartTime.ToUniversalTime().Ticks}
}
$ownedProcesses | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $statePath 'processes.json')
Write-Output 'Local services launched. Open http://127.0.0.1:5173. Local demo access needs no token unless -TokenAuth was selected. Stop with scripts/Stop-Local.ps1.'
