<#
start-distro.ps1 - the action of the boot task \SlateOpsBootTest\Start (runs as slateops-svc).

At Windows startup, with nobody signed in, Task Scheduler runs this script. It starts the
distribution and keeps one process attached to it (linux/keepalive.sh, "sleep infinity"),
so WSL does not stop the distribution. systemd in the distribution then starts Docker, and
Docker starts the test stack (restart: unless-stopped).

It passes Windows boot facts to Linux as one base64 argument, so the status JSON shows
which Windows boot it belongs to: last boot time, boot ID, and the boot type from the
Kernel-Boot event 27 (0 cold boot, 1 hybrid boot = Fast Startup, 2 resume from hibernation;
this mapping is from common usage, not from a Microsoft page checked for this kit).

If wsl.exe ends (for example after "wsl --update" or "wsl --shutdown"), the script logs the
exit code, waits 30 s and attaches again. It never ends by itself; the task has no time
limit (ExecutionTimeLimit PT0S). Log: C:\ProgramData\SlateOpsBootTest\svc-out\start-distro.log

-WhatIf: log the wsl.exe command once and change nothing.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()

. (Join-Path $PSScriptRoot 'common.ps1')

$dryRun = [bool]$WhatIfPreference
Initialize-BootTestLog -Name 'start-distro' -Append -DryRun:$dryRun -Directory $BootTest.SvcOut
$taskStartedAt = Get-UtcStamp

function Get-WindowsBootFact {
    param([int]$Attach)
    $facts = [ordered]@{
        windows_last_boot        = $null
        windows_boot_id          = $null
        windows_boot_type        = $null
        windows_boot_type_name   = $null
        start_task_started_at    = $taskStartedAt
        attach_number            = $Attach
        attached_at              = (Get-UtcStamp)
    }
    try { $facts.windows_last_boot = Get-UtcStamp -Time (Get-CimInstance -ClassName Win32_OperatingSystem).LastBootUpTime } catch { }
    try {
        $key = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters'
        $facts.windows_boot_id = [int](Get-ItemProperty -LiteralPath $key -Name BootId).BootId
    } catch { }
    try {
        $bootEvent = Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-Kernel-Boot'; Id = 27 } -MaxEvents 1
        $type = [int]$bootEvent.Properties[0].Value
        $facts.windows_boot_type = $type
        $facts.windows_boot_type_name = switch ($type) {
            0 { 'cold boot' }
            1 { 'hybrid boot (Fast Startup)' }
            2 { 'resume from hibernation' }
            default { 'other' }
        }
    } catch { }
    return $facts
}

$attach = 0
while ($true) {
    $attach++
    $facts = Get-WindowsBootFact -Attach $attach
    $json = ConvertTo-Json -InputObject $facts -Compress
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($json))
    $arguments = @('-d', $BootTest.DistroName, '-u', 'root', '--exec', ('{0}/keepalive.sh' -f $BootTest.LinuxLib), $encoded)
    if ($dryRun) {
        Write-KitLog ('Would run: wsl.exe {0}' -f ($arguments -join ' ')) 'WHATIF'
        break
    }
    Write-KitLog ('Attach {0}: starting {1}. Windows facts: {2}' -f $attach, $BootTest.DistroName, $json)
    $exitCode = $null
    try {
        # -PassThru and WaitForExit() wait for wsl.exe only. Start-Process -Wait would also wait
        # for every child process of wsl.exe. Reading Handle first keeps ExitCode available.
        $process = Start-Process -FilePath (Get-WslExe) -ArgumentList $arguments -NoNewWindow -PassThru `
            -RedirectStandardOutput (Join-Path $BootTest.SvcOut 'keepalive-stdout.log') `
            -RedirectStandardError (Join-Path $BootTest.SvcOut 'keepalive-stderr.log')
        $null = $process.Handle
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    } catch {
        Write-KitLog ('Attach {0}: could not start wsl.exe: {1}' -f $attach, $_.Exception.Message) 'ERROR'
    }
    Write-KitLog ('Attach {0}: wsl.exe ended (exit code {1}). Attaching again in 30 s.' -f $attach, $exitCode) 'WARN'
    Start-Sleep -Seconds 30
}
