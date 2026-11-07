param([string]$PythonPath = 'python')
$ErrorActionPreference = 'Stop'
$workerBackend = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../backend'))
$workerRuntime = Join-Path $workerBackend '.runtime'
New-Item -ItemType Directory -Path $workerRuntime -Force | Out-Null
$workerLock = [IO.File]::Open((Join-Path $workerRuntime 'supervisor.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$workerChild = $null
try {
    while ($true) {
        try {
            $workerChild = Start-Process -FilePath $PythonPath -ArgumentList @('-u', '-B', 'manage.py', 'process_smartnest_automations', '--loop', '--interval', '60') -WorkingDirectory $workerBackend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $workerRuntime 'worker-output.log') -RedirectStandardError (Join-Path $workerRuntime 'worker-error.log') -PassThru
            $workerChild.Id | Set-Content -LiteralPath (Join-Path $workerRuntime 'worker.pid')
            $workerChild.WaitForExit()
        } catch {
            'Worker launch failed; retrying.' | Set-Content -LiteralPath (Join-Path $workerRuntime 'supervisor-status.log')
        }
        Start-Sleep -Seconds 10
    }
} finally {
    if ($workerChild -and -not $workerChild.HasExited) { Stop-Process -Id $workerChild.Id }
    $workerLock.Dispose()
}
