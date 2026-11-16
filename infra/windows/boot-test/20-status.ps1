<#
20-status.ps1 - shows the state of the Slate Operations WSL2 boot test on this PC.

It shows, in this order:
  1. Windows: last boot, boot type (cold, Fast Startup, hibernation), Fast Startup setting.
  2. The scheduled tasks: state, last run, last result, and the effective settings of the
     boot task (logon type, ExecutionTimeLimit, triggers) from its exported XML.
  3. The account slateops-svc and the two firewall rules (and the network category now).
  4. The test web service from this PC: http://127.0.0.1:8443/ (mirrored mode forwards it).
  5. Inside the distribution, through the "status" job as slateops-svc: WSL version, the
     distribution state, systemd, Docker, the test stack. The job never starts a stopped
     distribution, so it does not change the test result. Because the job starts a batch logon
     of slateops-svc, the script reads attach_number and linux_boot_id before and after the
     job and says if they changed.
  6. Event log entries since the last boot: boot, shutdown, unexpected shutdown, power loss,
     sign-in and sign-out (Winlogon 7001 and 7002), and Task Scheduler events of the kit's tasks.
  7. The last lines of svc-out\start-distro.log (the boot task log).
The LAN check (from another device) is in the README; this PC cannot reach its own LAN
address through mirrored mode, so it uses 127.0.0.1.

Run in Windows PowerShell opened with "Run as administrator":
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\20-status.ps1
-WhatIf: skip the "status" job and write no log; all other parts only read.
Exit code: 0 when the status is fresh, 1 when it answers but is not fresh, 2 when this PC
cannot reach it (then check from another LAN device; that check decides).
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    # Skip part 5 (the job inside the distribution).
    [switch]$NoDistroCheck
)

. (Join-Path $PSScriptRoot 'lib\common.ps1')

$dryRun = [bool]$WhatIfPreference
$fresh = $false
$reached = $false
$beforeJob = $null

function Get-XmlValue {
    # Returns a child element's text (or the element when it has children), or "(not set)".
    # Task Scheduler leaves default values out of the XML.
    param($Node, [string]$Name)
    $child = $null
    if ($Node) { $child = $Node.SelectSingleNode(('*[local-name()="{0}"]' -f $Name)) }
    if ($null -eq $child) { return '(not set, default)' }
    if ($child.HasChildNodes -and ($child.ChildNodes.Count -gt 1 -or $child.FirstChild.NodeType -eq 'Element')) { return ,$child }
    return $child.InnerText
}

function Show-Section { param([string]$Title) Write-KitLog ('==== {0} ====' -f $Title) 'STEP' }

function Invoke-Probe {
    # Runs one read-only probe. A failed probe is a result, so the script continues.
    param([string]$Name, [scriptblock]$Probe)
    try { & $Probe } catch { Write-KitLog ('{0}: {1}' -f $Name, $_.Exception.Message) 'FAIL' }
}

try {
    Assert-Administrator
    Initialize-BootTestLog -Name '20-status' -DryRun:$dryRun
    $now = Get-Date
    Write-KitLog ('Slate Operations WSL2 boot test: status at {0} (UTC), {1} local time.' -f (Get-UtcStamp), $now.ToString('yyyy-MM-dd HH:mm:ss'))

    Show-Section 'Windows'
    Invoke-Probe 'Windows' {
        $win = Get-WindowsInfo
        $uptime = $now - $win.LastBoot
        Write-KitLog ('Last boot {0} UTC (uptime {1:%d}d {1:hh}h {1:mm}m).' -f (Get-UtcStamp -Time $win.LastBoot), $uptime)
        $bootEvent = Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-Kernel-Boot'; Id = 27 } -MaxEvents 1 -ErrorAction SilentlyContinue
        if ($bootEvent) {
            $type = [int]$bootEvent.Properties[0].Value
            $name = switch ($type) { 0 { 'cold boot' } 1 { 'hybrid boot (Fast Startup)' } 2 { 'resume from hibernation' } default { 'other' } }
            Write-KitLog ('Last boot type: {0} ({1}), event at {2} UTC.' -f $type, $name, (Get-UtcStamp -Time $bootEvent.TimeCreated))
        }
        $power = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -ErrorAction SilentlyContinue
        if ($power -and $power.PSObject.Properties['HiberbootEnabled']) { Write-KitLog ('Fast Startup: {0}.' -f $(if ($power.HiberbootEnabled -eq 1) { 'on' } else { 'off' })) }
        $sessions = @(Get-CimInstance -ClassName Win32_LogonSession -Filter 'LogonType = 2 OR LogonType = 10' -ErrorAction SilentlyContinue)
        Write-KitLog ('Interactive or Remote Desktop logon sessions now: {0}.' -f $sessions.Count)
    }

    Show-Section 'Scheduled tasks'
    Invoke-Probe 'Tasks' {
        $tasks = @(Get-ScheduledTask -TaskPath $BootTest.TaskPath -ErrorAction SilentlyContinue)
        if ($tasks.Count -eq 0) { Write-KitLog ('No tasks under {0}.' -f $BootTest.TaskPath) 'FAIL'; return }
        foreach ($task in $tasks) {
            $info = Get-ScheduledTaskInfo -TaskPath $task.TaskPath -TaskName $task.TaskName
            Write-KitLog ('{0}{1}: state {2}, last run {3}, last result 0x{4:X8}, run as {5} ({6}).' -f $task.TaskPath, $task.TaskName, $task.State,
                $info.LastRunTime, $info.LastTaskResult, $task.Principal.UserId, $task.Principal.LogonType)
        }
        $start = $tasks | Where-Object { $_.TaskName -eq $BootTest.StartTaskName }
        if ($start) {
            [xml]$xml = Export-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.StartTaskName
            $settings = $xml.Task.Settings
            $limit = Get-XmlValue $settings 'ExecutionTimeLimit'
            $level = $(if ($limit -eq 'PT0S') { 'PASS' } else { 'FAIL' })
            Write-KitLog ('Boot task ExecutionTimeLimit: {0} (PT0S = no limit).' -f $limit) $level
            $restart = Get-XmlValue $settings 'RestartOnFailure'
            if ($restart -is [System.Xml.XmlElement]) { Write-KitLog ('Boot task RestartOnFailure: every {0}, {1} times.' -f (Get-XmlValue $restart 'Interval'), (Get-XmlValue $restart 'Count')) }
            Write-KitLog ('Boot task MultipleInstancesPolicy: {0}; DisallowStartIfOnBatteries: {1}; StopIfGoingOnBatteries: {2}; StartWhenAvailable: {3}; Priority: {4}.' -f
                (Get-XmlValue $settings 'MultipleInstancesPolicy'), (Get-XmlValue $settings 'DisallowStartIfOnBatteries'),
                (Get-XmlValue $settings 'StopIfGoingOnBatteries'), (Get-XmlValue $settings 'StartWhenAvailable'), (Get-XmlValue $settings 'Priority'))
            foreach ($trigger in @($xml.Task.Triggers.ChildNodes)) {
                $repeat = Get-XmlValue $trigger 'Repetition'
                $interval = $(if ($repeat -is [System.Xml.XmlElement]) { Get-XmlValue $repeat 'Interval' } else { 'none' })
                Write-KitLog ('Boot task trigger: {0}, repetition {1}.' -f $trigger.LocalName, $interval)
            }
            Write-KitLog ('Boot task logon type: {0}.' -f (Get-XmlValue $xml.Task.Principals.Principal 'LogonType'))
        }
    }

    Show-Section 'Account and firewall'
    Invoke-Probe 'Account' {
        $account = Get-ServiceAccount
        if ($account) { Write-KitLog ('Account {0}: enabled {1}, SID {2}.' -f $account.Name, $account.Enabled, $account.SID.Value) }
        else { Write-KitLog ('Account {0}: missing.' -f $BootTest.AccountName) 'FAIL' }
    }
    Invoke-Probe 'Firewall' {
        $rule = Get-NetFirewallRule -Name $BootTest.FirewallRuleName -ErrorAction SilentlyContinue
        if ($rule) {
            $port = $rule | Get-NetFirewallPortFilter
            $address = $rule | Get-NetFirewallAddressFilter
            Write-KitLog ('Windows firewall rule: enabled {0}, profile {1}, TCP {2}, remote {3}.' -f $rule.Enabled, $rule.Profile, $port.LocalPort, ($address.RemoteAddress -join ','))
        } else { Write-KitLog 'Windows firewall rule: missing.' 'FAIL' }
        $lan = Get-LanInfo
        if ($lan) {
            $level = $(if (($lan.Category -eq 'Private') -or ($lan.Category -eq 'DomainAuthenticated')) { 'PASS' } else { 'FAIL' })
            Write-KitLog ('LAN now: {0} on "{1}", category {2}.' -f $lan.Address, $lan.InterfaceAlias, $lan.Category) $level
            Write-KitLog ('Check from another LAN device: http://{0}:{1}/' -f $lan.Address, $BootTest.Port)
        }
    }

    # The Hyper-V firewall objects are printed with all their properties, so this part does
    # not depend on property names.
    Invoke-Probe 'Hyper-V firewall rule' {
        $hyperV = Get-NetFirewallHyperVRule -Name $BootTest.HyperVRuleName -ErrorAction SilentlyContinue
        if (-not $hyperV) { Write-KitLog 'Hyper-V firewall rule: missing.' 'FAIL'; return }
        Write-KitLog 'Hyper-V firewall rule:'
        foreach ($line in (($hyperV | Format-List -Property * | Out-String -Width 200) -split "`r?`n")) { if ($line.Trim()) { Write-KitLog ('  {0}' -f $line.TrimEnd()) } }
    }
    Invoke-Probe 'Hyper-V firewall setting for WSL' {
        $vmSetting = Get-NetFirewallHyperVVMSetting -PolicyStore ActiveStore -Name $BootTest.WslVmCreatorId
        Write-KitLog 'Hyper-V firewall setting for the WSL VM (DefaultInboundAction should be Block):'
        foreach ($line in (($vmSetting | Format-List -Property * | Out-String -Width 200) -split "`r?`n")) { if ($line.Trim()) { Write-KitLog ('  {0}' -f $line.TrimEnd()) } }
    }

    Show-Section ('Test web service from this PC: {0}' -f $BootTest.StatusUrl)
    $lanUrl = $null
    $lanNow = Get-LanInfo
    if ($lanNow) { $lanUrl = 'http://{0}:{1}/' -f $lanNow.Address, $BootTest.Port }
    $json = $null
    try { $json = Get-StatusJson -TimeoutSec 10 }
    catch {
        Write-KitLog ('This PC cannot read {0}: {1}' -f $BootTest.StatusUrl, $_.Exception.Message) 'WARN'
        Write-KitLog ('That alone does not prove a failure. Check from another device: {0}' -f $lanUrl) 'WARN'
    }
    if ($json) {
        Invoke-Probe 'Web service' {
            $s = $json.status
            $script:reached = $true
            $script:fresh = [bool]$json.fresh
            Write-KitLog ('fresh {0}, status age {1} s, same Linux boot {2}, web network {3}.' -f $json.fresh, $json.status_age_seconds, $json.same_linux_boot, $json.web_network) $(if ($json.fresh) { 'PASS' } else { 'FAIL' })
            if ($s) {
                Write-KitLog ('heartbeat_count {0}; first_heartbeat {1}; last_heartbeat {2}.' -f $s.heartbeat_count, $s.first_heartbeat, $s.last_heartbeat)
                Write-KitLog ('largest_gap_seconds {0} (ended {1}); gaps_over_120s {2}.' -f $s.largest_gap_seconds, $s.largest_gap_ended_at, $s.gaps_over_120s)
                Write-KitLog ('Linux boot ID {0}; Linux uptime {1} s; heartbeat container started {2}; PostgreSQL started {3}.' -f
                    $s.linux_boot_id, $s.linux_uptime_seconds, $s.heartbeat_container_started_at, $s.postgres_started_at)
                if ($s.windows) {
                    Write-KitLog ('Windows facts from the boot task: last boot {0}, boot ID {1}, boot type {2}, attach {3} at {4}.' -f
                        $s.windows.windows_last_boot, $s.windows.windows_boot_id, $s.windows.windows_boot_type_name, $s.windows.attach_number, $s.windows.attached_at)
                    $script:beforeJob = @{ Attach = [string]$s.windows.attach_number; Boot = [string]$s.linux_boot_id }
                }
            }
            Write-KitLog ('Raw JSON: {0}' -f ($json | ConvertTo-Json -Compress -Depth 5))
        }
    }

    if (-not $NoDistroCheck) {
        Show-Section 'Inside the distribution (job "status" as slateops-svc)'
        if ($dryRun) { Write-KitLog 'Would: run the job "status" as slateops-svc (read-only).' 'WHATIF' }
        else {
            Invoke-Probe 'Status job' { Invoke-SvcJob -Job 'status' -TimeoutMinutes 3 | Out-Null }
            # The job is a batch logon of slateops-svc. Check that it did not restart or re-attach
            # the distribution (it must observe, not change, the test).
            if ($beforeJob) {
                Invoke-Probe 'Effect of the status job' {
                    Start-Sleep -Seconds 5
                    $after = Get-StatusJson -TimeoutSec 10
                    $afterAttach = [string]$after.status.windows.attach_number
                    $afterBoot = [string]$after.status.linux_boot_id
                    if (($afterAttach -eq $beforeJob.Attach) -and ($afterBoot -eq $beforeJob.Boot)) {
                        Write-KitLog ('The status job changed nothing: attach_number {0} and linux_boot_id {1} are the same before and after.' -f $afterAttach, $afterBoot) 'PASS'
                    } else {
                        Write-KitLog ('The status job coincided with a change: attach_number {0} -> {1}, linux_boot_id {2} -> {3}. Record this in the notes.' -f $beforeJob.Attach, $afterAttach, $beforeJob.Boot, $afterBoot) 'WARN'
                    }
                }
            }
        }
    }

    Show-Section 'Event log since the last boot'
    Invoke-Probe 'Events' {
        $since = (Get-WindowsInfo).LastBoot.AddMinutes(-30)
        $system = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = $since; Id = @(12, 13, 27, 41, 1074, 6005, 6006, 6008, 7001, 7002) } -ErrorAction SilentlyContinue |
                Where-Object { $_.ProviderName -match 'Kernel-General|Kernel-Boot|Kernel-Power|User32|EventLog|Winlogon' } | Select-Object -First 25)
        foreach ($e in $system) {
            $message = ($e.Message -split "`r?`n")[0]
            Write-KitLog ('System {0} UTC id {1} {2}: {3}' -f (Get-UtcStamp -Time $e.TimeCreated), $e.Id, $e.ProviderName, $message)
        }
        $previous = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = @(41, 6008) } -MaxEvents 3 -ErrorAction SilentlyContinue)
        foreach ($e in $previous) { Write-KitLog ('Last unexpected shutdown record: {0} UTC id {1} {2}.' -f (Get-UtcStamp -Time $e.TimeCreated), $e.Id, $e.ProviderName) }
        $taskEvents = @(Get-WinEvent -FilterHashtable @{ LogName = 'Microsoft-Windows-TaskScheduler/Operational'; StartTime = $since } -ErrorAction SilentlyContinue |
                Where-Object { $_.Message -match [regex]::Escape($BootTest.TaskPath) } | Select-Object -First 20)
        if ($taskEvents.Count -eq 0) { Write-KitLog 'Task Scheduler: no events for the kit tasks since the last boot (or the log is off).' 'WARN' }
        foreach ($e in $taskEvents) {
            $message = ($e.Message -split "`r?`n")[0]
            Write-KitLog ('TaskScheduler {0} UTC id {1}: {2}' -f (Get-UtcStamp -Time $e.TimeCreated), $e.Id, $message)
        }
    }

    Show-Section 'Boot task log (last 15 lines)'
    Invoke-Probe 'Boot task log' {
        $log = Join-Path $BootTest.SvcOut 'start-distro.log'
        if (Test-Path -LiteralPath $log) { foreach ($line in (Get-Content -LiteralPath $log -Tail 15)) { Write-KitLog ('  | {0}' -f $line) } }
        else { Write-KitLog ('{0} does not exist yet.' -f $log) 'WARN' }
    }

    if ($fresh) { Write-KitLog 'Overall: the test service answers with a fresh heartbeat.' 'PASS'; exit 0 }
    if (-not $reached) {
        Write-KitLog ('Overall: not confirmed from this PC. Check from another device: {0}' -f $lanUrl) 'WARN'
        exit 2
    }
    Write-KitLog 'Overall: the test service answers, but with no fresh heartbeat.' 'FAIL'
    exit 1
} catch {
    Write-KitLog ('Status stopped: {0}' -f $_.Exception.Message) 'ERROR'
    Write-KitLog ($_.InvocationInfo.PositionMessage) 'ERROR'
    exit 1
}
