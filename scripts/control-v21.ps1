param([ValidateSet('start','stop')][string]$Action)
$ErrorActionPreference = 'Stop'
$source = Split-Path $PSScriptRoot -Parent
$python = Join-Path $source '.venv\Scripts\python.exe'
$entry = Join-Path $PSScriptRoot 'v21.py'
# Windows venv redirectors can launch the base interpreter as a child.
$basePython = (& $python -c 'import sys; print(sys._base_executable)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the V21 virtual environment interpreter.' }
$allowedExecutables = @($python.ToLowerInvariant(), $basePython.ToLowerInvariant())
# Serialize start/stop controllers for this application folder.
$sha = [System.Security.Cryptography.SHA256]::Create()
$key = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($source.ToLowerInvariant())))).Replace('-','')
$mutex = New-Object System.Threading.Mutex($false, "Global\CirrusV21-$key")
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Another V21 start/stop controller is active.' }
    $running = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $allowedExecutables.Contains($_.ExecutablePath.ToLowerInvariant()) -and
        $_.CommandLine -and $_.CommandLine.Contains('"' + $entry + '" start')
    })
    if ($Action -eq 'stop') {
        foreach ($item in $running) {
            # Revalidate start time and exact executable immediately before termination.
            $process = Get-Process -Id $item.ProcessId -ErrorAction SilentlyContinue
            if ($process -and $allowedExecutables.Contains($process.Path.ToLowerInvariant()) -and [Math]::Abs(($process.StartTime.ToUniversalTime() - $item.CreationDate.ToUniversalTime()).TotalSeconds) -lt 2) {
                Stop-Process -InputObject $process
                $process.WaitForExit(15000) | Out-Null
                if (-not $process.HasExited) { throw 'V21 has not exited; do not start V20 yet.' }
            } else { throw 'Process identity changed; refusing to stop an unverified process.' }
        }
        if ($running.Count -eq 0) { Write-Host 'No V21 process from this application folder found.' }
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) { throw 'Port 8000 remains occupied. Its owner was not stopped. Inspect before restarting V20.' }
        Write-Host 'V21 stopped; port 8000 is free. You may restart V20 using its existing launcher/service.'
    } else {
        if ($running.Count -gt 0) { throw 'V21 is already running from this folder.' }
        $env:CIRRUS_V21_PROFILE = (& $python (Join-Path $PSScriptRoot 'bootstrap_v21.py') profile).Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Run setup.bat first.' }
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) { throw 'Port 8000 is occupied. Stop V20 first. No process was killed.' }
        & $python $entry check
        if ($LASTEXITCODE -ne 0) { throw 'V21 profile check failed.' }
        # The Python launcher also binds exclusively before DB access, closing the check/start race.
        $child = Start-Process -FilePath $python -ArgumentList @(('"' + $entry + '"'), 'start') -WorkingDirectory $source -PassThru
        $child.WaitForExit(3000) | Out-Null
        if ($child.HasExited) { throw "V21 exited during startup (code $($child.ExitCode)). Read its console error." }
        $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $owner = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.OwningProcess); $owner -and ($owner.ProcessId -eq $child.Id -or $owner.ParentProcessId -eq $child.Id) })
        if ($listener.Count -eq 0) { throw 'V21 startup is still pending. Inspect the console and port owner before switching versions.' }
        Write-Host "V21 started with PID $($child.Id). IIS remains pointed at 127.0.0.1:8000."
    }
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
