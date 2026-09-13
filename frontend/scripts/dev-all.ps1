param(
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$frontendRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$root = Resolve-Path (Join-Path $frontendRoot '..')
$backendRoot = Join-Path $root 'backend'
$backendExe = Join-Path $root '.venv\Scripts\python.exe'
$frontendExe = Join-Path $frontendRoot 'node_modules\.bin\vite.cmd'

$backendArgs = @(
  '-m', 'uvicorn', 'main:app',
  '--reload',
  '--app-dir', 'backend',
  '--host', '0.0.0.0',
  '--port', '8000'
)

$paperWorkerArgs = @('scripts/process_paper_jobs.py')
$communicationWorkerArgs = @('scripts/process_communication_events.py')

$frontendArgs = @(
  '--host', '0.0.0.0',
  '--port', '3000'
)

if ($DryRun) {
  Write-Output "[backend] $backendExe $($backendArgs -join ' ')"
  Write-Output "[paper-worker] $backendExe $($paperWorkerArgs -join ' ')"
  Write-Output "[communication-worker] $backendExe $($communicationWorkerArgs -join ' ')"
  Write-Output "[frontend] $frontendExe $($frontendArgs -join ' ')"
  exit 0
}

if (-not (Test-Path $backendExe)) {
  throw "Backend Python executable not found: $backendExe"
}

if (-not (Test-Path $frontendExe)) {
  throw "Vite executable not found: $frontendExe"
}

$backend = Start-Process -FilePath $backendExe -ArgumentList $backendArgs -WorkingDirectory $root -PassThru -NoNewWindow
$paperWorker = Start-Process -FilePath $backendExe -ArgumentList $paperWorkerArgs -WorkingDirectory $backendRoot -PassThru -NoNewWindow
$communicationWorker = Start-Process -FilePath $backendExe -ArgumentList $communicationWorkerArgs -WorkingDirectory $backendRoot -PassThru -NoNewWindow
$frontend = Start-Process -FilePath $frontendExe -ArgumentList $frontendArgs -WorkingDirectory $frontendRoot -PassThru -NoNewWindow

try {
  while (-not $backend.HasExited -and -not $paperWorker.HasExited -and -not $communicationWorker.HasExited -and -not $frontend.HasExited) {
    Start-Sleep -Milliseconds 500
  }

  if (-not $backend.HasExited) {
    Stop-Process -Id $backend.Id -Force
  }

  if (-not $frontend.HasExited) {
    Stop-Process -Id $frontend.Id -Force
  }

  if (-not $paperWorker.HasExited) {
    Stop-Process -Id $paperWorker.Id -Force
  }

  if (-not $communicationWorker.HasExited) {
    Stop-Process -Id $communicationWorker.Id -Force
  }

  if ($backend.HasExited -and $backend.ExitCode -ne 0) {
    exit $backend.ExitCode
  }

  if ($frontend.HasExited -and $frontend.ExitCode -ne 0) {
    exit $frontend.ExitCode
  }
  if ($paperWorker.HasExited -and $paperWorker.ExitCode -ne 0) {
    exit $paperWorker.ExitCode
  }
  if ($communicationWorker.HasExited -and $communicationWorker.ExitCode -ne 0) {
    exit $communicationWorker.ExitCode
  }
}
finally {
  foreach ($proc in @($backend, $paperWorker, $communicationWorker, $frontend)) {
    if ($null -ne $proc -and -not $proc.HasExited) {
      Stop-Process -Id $proc.Id -Force
    }
  }
}
