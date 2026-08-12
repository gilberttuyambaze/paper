param(
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$backendExe = Join-Path $root '.venv\Scripts\python.exe'
$frontendExe = Join-Path $root 'node_modules\.bin\vite.cmd'

$backendArgs = @(
  '-m', 'uvicorn', 'main:app',
  '--reload',
  '--app-dir', 'backend',
  '--host', '0.0.0.0',
  '--port', '8000'
)

$frontendArgs = @(
  '--host', '0.0.0.0',
  '--port', '3000'
)

if ($DryRun) {
  Write-Output "[backend] $backendExe $($backendArgs -join ' ')"
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
$frontend = Start-Process -FilePath $frontendExe -ArgumentList $frontendArgs -WorkingDirectory $root -PassThru -NoNewWindow

try {
  while (-not $backend.HasExited -and -not $frontend.HasExited) {
    Start-Sleep -Milliseconds 500
  }

  if (-not $backend.HasExited) {
    Stop-Process -Id $backend.Id -Force
  }

  if (-not $frontend.HasExited) {
    Stop-Process -Id $frontend.Id -Force
  }

  if ($backend.HasExited -and $backend.ExitCode -ne 0) {
    exit $backend.ExitCode
  }

  if ($frontend.HasExited -and $frontend.ExitCode -ne 0) {
    exit $frontend.ExitCode
  }
}
finally {
  foreach ($proc in @($backend, $frontend)) {
    if ($null -ne $proc -and -not $proc.HasExited) {
      Stop-Process -Id $proc.Id -Force
    }
  }
}
