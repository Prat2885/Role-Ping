# Register a Windows scheduled task that runs one careers check on a loop.
param(
    [int]$EveryMinutes = 120,
    [string]$TaskName = "JobAlertAgent"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Config = Join-Path $Root "config.yaml"

if (-not (Test-Path $Python)) {
    throw "Missing $Python. From the project folder run: py -3 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ."
}
if (-not (Test-Path $Config)) {
    throw "Missing $Config. Copy config.example.yaml to config.yaml and edit it."
}
if ($EveryMinutes -lt 1) {
    throw "EveryMinutes must be at least 1."
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument "-m jobalert check --config `"$Config`"" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Email new job openings from configured careers pages." -Force | Out-Null
Write-Host "Scheduled task '$TaskName' runs every $EveryMinutes minutes."
