# Schedule the daily jobs with Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -File scripts\schedule-windows.ps1 -AgencyTime 06:00 -JobsTime 13:00
#
# Creates two tasks (re-running replaces them):
#   "OpenProspect Daily"  the agency track: replies -> scrape -> enrich -> verify -> score -> CRM -> send
#   "OpenProspect Jobs"   the job & freelance track: find openings -> write drafts -> send
# Output goes to data\logs\. Your PC must be on and Docker Desktop running at those times.
#
# Remove:  Unregister-ScheduledTask -TaskName "OpenProspect Daily" -Confirm:$false
#          Unregister-ScheduledTask -TaskName "OpenProspect Jobs" -Confirm:$false
param(
  [string]$AgencyTime = "06:00",
  [string]$JobsTime = "13:00",
  [switch]$NoJobs
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$uv = (Get-Command uv -ErrorAction Stop).Source

function Register-OpenProspectTask($name, $time, $command, $logPrefix) {
  $inner = "Set-Location '$repo'; New-Item -ItemType Directory -Force -Path data\logs | Out-Null; " +
           "`$env:PYTHONIOENCODING='utf-8'; " +
           "& '$uv' run openprospect $command *>&1 | Tee-Object -FilePath (Join-Path 'data\logs' ('${logPrefix}_' + (Get-Date -Format yyyyMMdd_HHmm) + '.log'))"
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$inner`"" -WorkingDirectory $repo
  $trigger = New-ScheduledTaskTrigger -Daily -At $time
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Write-Host "Scheduled '$name' daily at $time" -ForegroundColor Green
}

Register-OpenProspectTask "OpenProspect Daily" $AgencyTime "run" "run"
if (-not $NoJobs) { Register-OpenProspectTask "OpenProspect Jobs" $JobsTime "jobs daily" "jobs" }
Write-Host "Logs: $repo\data\logs"
