# Runs the Charter Intervention Monitor once, logging output to monitor.log.
# Intended to be triggered weekly by Windows Task Scheduler (see docs/SCHEDULING.md).

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$secrets = Join-Path $PSScriptRoot "secrets.ps1"
if (Test-Path $secrets) {
    . $secrets
} else {
    Write-Error "secrets.ps1 not found. Copy secrets.example.ps1 to secrets.ps1 and fill it in first."
    exit 1
}

$logFile = Join-Path $PSScriptRoot "monitor.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "`n===== Run at $timestamp =====" -Encoding utf8

# uv/python routinely print informational text to stderr (e.g. package installs).
# With $ErrorActionPreference = "Stop", PowerShell would otherwise treat that as a
# fatal error even on success, so relax it just for this one command and check the
# real exit code instead.
#
# Piping through Out-File (instead of the *>> redirection operator) keeps the
# encoding consistent with Add-Content above -- mixing the two caused garbled
# (mojibake) text in monitor.log previously.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
uv run --with requests --with beautifulsoup4 --with lxml python run_monitor.py *>&1 |
    Out-File -FilePath $logFile -Append -Encoding utf8
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $previousPreference

if ($exitCode -ne 0) {
    Add-Content -Path $logFile -Value "run_monitor.py exited with code $exitCode -- see above for details" -Encoding utf8
    Write-Error "run_monitor.py failed (exit code $exitCode). See monitor.log for details."
    exit $exitCode
}

Add-Content -Path $logFile -Value "Run finished successfully." -Encoding utf8
