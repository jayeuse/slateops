<#
90-cleanup.ps1 - removes everything that the Slate Operations WSL2 boot-test kit added.

It first lists what it found and asks you to type REMOVE. Then, in this order:
  1. disables and stops the boot task \SlateOpsBootTest\Start,
  2. runs the job "unregister" as slateops-svc: stops and unregisters the distribution
     SlateOpsBootTest (this deletes its virtual disk and the test database), removes the
     account's .wslconfig, and stops that account's WSL VM,
  3. disables the account slateops-svc at once (nobody can use it from here on),
  4. deletes the scheduled tasks and the task folder \SlateOpsBootTest\,
  5. deletes the two firewall rules (Windows Defender Firewall and Hyper-V firewall),
  6. removes the sign-in screen entry, deletes the account's profile (by SID), then the account,
  7. removes the account's user rights by SID (after the account is gone),
  8. restores Sleep and Hibernate on mains power and the Task Scheduler log state,
  9. deletes C:\ProgramData\SlateOpsBootTest, except the logs folder (use -RemoveLogs).
     Deletes never follow a junction or link.
P1 items (30-p1.ps1) go first, each one on its own, so a half-finished P1 run never blocks
cleanup: the F4 test installer (silent uninstall) and its RunOnce entry, the throwaway
distribution SlateOpsSpike and the account slateops-f3 with its task, the P1 firewall rules
(TCP 443 and 80, Hyper-V UDP 5353), the hosts entry, and the P1 tasks.
-P1Only removes only the P1 items and keeps the boot-test setup. It also removes the S1 stack
inside the distribution (containers, volumes with the throwaway test data, images, units) and
the P1 files in C:\ProgramData\SlateOpsBootTest.
It reads state\state.json only when the kit folder passes the safety check (see lib\common.ps1);
otherwise it ignores the file and says which settings you must restore by hand.
WSL itself stays installed. With -RemoveWsl it also uninstalls the WSL package and turns off
VirtualMachinePlatform, but only when setup installed them (WSL was absent before setup).
Caution: -RemoveWsl also removes WSL for your own account and any distributions you use.
It never touches your own account, your own WSL distributions or your own .wslconfig.

Run in Windows PowerShell opened with "Run as administrator":
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\90-cleanup.ps1
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\90-cleanup.ps1 -WhatIf
-WhatIf lists the removals and changes nothing (no prompt, no log file).
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$RemoveWsl,
    [switch]$RemoveLogs,
    # Remove only what P1 (30-p1.ps1) added; keep the boot-test setup.
    [switch]$P1Only
)

. (Join-Path $PSScriptRoot 'lib\common.ps1')

$dryRun = [bool]$WhatIfPreference

function Get-WslUninstallEntry {
    $keys = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
    foreach ($entry in @(Get-ItemProperty -Path $keys -ErrorAction SilentlyContinue)) {
        if ($entry.PSObject.Properties['DisplayName'] -and ($entry.DisplayName -like 'Windows Subsystem for Linux*') -and ($entry.PSChildName -match '^\{[0-9A-Fa-f-]+\}$')) {
            return $entry
        }
    }
    return $null
}

function Get-P1Plan {
    # What P1 left on this PC (each part checked on its own).
    $plan = @()
    $f4 = Get-ItemProperty -LiteralPath $BootTest.P1.F4UninstallKey -ErrorAction SilentlyContinue
    if ($f4) { $plan += ('F4 test installer "{0}" (silent uninstall)' -f $f4.DisplayName) }
    if (Test-Path -LiteralPath (Join-Path $env:ProgramFiles 'SlateOps P1 installer test')) { $plan += 'F4 program folder' }
    if (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce' -Name $BootTest.P1.F4RunOnceName -ErrorAction SilentlyContinue) { $plan += 'F4 RunOnce entry' }
    if (Get-LocalUser -Name $BootTest.P1.F3AccountName -ErrorAction SilentlyContinue) { $plan += ('P1 account {0}, its profile, rights and task' -f $BootTest.P1.F3AccountName) }
    if (Test-Path -LiteralPath $BootTest.Spike) { $plan += ('Throwaway distribution {0} and {1}' -f $BootTest.P1.SpikeDistroName, $BootTest.Spike) }
    $rules = Get-P1RuleName
    foreach ($name in $rules.Windows) { if (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) { $plan += ('Firewall rule {0}' -f $name) } }
    foreach ($name in $rules.HyperV) { if (Get-NetFirewallHyperVRule -Name $name -ErrorAction SilentlyContinue) { $plan += ('Hyper-V firewall rule {0}' -f $name) } }
    if (@(Get-Content -LiteralPath (Get-P1HostsPath) -ErrorAction SilentlyContinue | Where-Object { $_ -like ('*' + $BootTest.P1.HostsMarker + '*') }).Count -gt 0) { $plan += 'hosts entry of P1' }
    foreach ($name in @($BootTest.P1.ProbeTaskName, $BootTest.P1.ResumeTaskName, $BootTest.P1.F3TaskName)) {
        if (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $name -ErrorAction SilentlyContinue) { $plan += ('Task {0}{1}' -f $BootTest.TaskPath, $name) }
    }
    return $plan
}

function Invoke-P1Removal {
    # Each part in its own try: a missing or half-made part never stops the others.
    param([switch]$StackToo)
    $parts = @(
        @{ Name = 'F4 test installer'; Action = {
            # The RunOnce entry first: a restart during cleanup must not start the test installer.
            Remove-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce' -Name $BootTest.P1.F4RunOnceName -ErrorAction SilentlyContinue
            $f4 = Get-ItemProperty -LiteralPath $BootTest.P1.F4UninstallKey -ErrorAction SilentlyContinue
            if ($f4 -and $f4.PSObject.Properties['UninstallString']) {
                $exe = ([string]$f4.UninstallString).Trim('"')
                if (Test-Path -LiteralPath $exe) {
                    $process = Start-Process -FilePath $exe -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
                    Write-KitLog ('  Silent uninstall exit code {0}.' -f $process.ExitCode)
                }
            }
            if (Test-Path -LiteralPath $BootTest.P1.F4UninstallKey) { Remove-Item -LiteralPath $BootTest.P1.F4UninstallKey -Recurse -Force }
            # The first run copies setup-resume.exe into the program folder before the restart.
            $programFolder = Join-Path $env:ProgramFiles 'SlateOps P1 installer test'
            if (Test-Path -LiteralPath $programFolder) { Remove-PathNoFollow -Path $programFolder }
        } },
        @{ Name = 'F3 distribution of slateops-f3'; Action = {
            if ((Get-LocalUser -Name $BootTest.P1.F3AccountName -ErrorAction SilentlyContinue) -and
                (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.F3TaskName -ErrorAction SilentlyContinue)) {
                $null = Invoke-SvcJob -Job 'f3-cleanup' -Account 'f3' -TimeoutMinutes 5 -NoThrow
            }
        } },
        @{ Name = 'P1 account slateops-f3'; Action = {
            if (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.F3TaskName -ErrorAction SilentlyContinue) {
                Unregister-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.F3TaskName -Confirm:$false
            }
            $sid = Get-BootTestF3Sid
            if ($sid) {
                foreach ($dir in @($BootTest.Root, $BootTest.Kit, $BootTest.State)) {
                    if (Test-Path -LiteralPath $dir) { Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($dir, '/remove:g', ('*{0}' -f $sid)) -Quiet -NoThrow | Out-Null }
                }
                Remove-KitLocalAccount -Name $BootTest.P1.F3AccountName -Sid $sid
            }
        } },
        @{ Name = 'Throwaway distribution SlateOpsSpike'; Action = {
            if ((Get-ServiceAccount) -and (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.ExecTaskName -ErrorAction SilentlyContinue)) {
                $null = Invoke-SvcJob -Job 'spike-unregister' -TimeoutMinutes 10 -NoThrow
            }
        } },
        @{ Name = 'S1 stack in the distribution'; Action = {
            if ($StackToo -and (Get-ServiceAccount) -and (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.ExecTaskName -ErrorAction SilentlyContinue)) {
                $null = Invoke-SvcJob -Job 's1-remove' -TimeoutMinutes 20 -NoThrow
            }
        } },
        @{ Name = 'P1 firewall rules'; Action = {
            $rules = Get-P1RuleName
            foreach ($name in $rules.Windows) { Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule }
            foreach ($name in $rules.HyperV) { Get-NetFirewallHyperVRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule }
        } },
        @{ Name = 'P1 hosts entry'; Action = {
            $removed = Remove-P1HostsEntry
            Write-KitLog ('  Removed {0} hosts line(s).' -f $removed)
        } },
        @{ Name = 'P1 tasks'; Action = {
            foreach ($name in @($BootTest.P1.ProbeTaskName, $BootTest.P1.ResumeTaskName)) {
                if (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $name -ErrorAction SilentlyContinue) {
                    Unregister-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $name -Confirm:$false
                }
            }
        } }
    )
    foreach ($part in $parts) {
        if ($dryRun) { Write-KitLog ('Would: remove {0} (if present)' -f $part.Name) 'WHATIF'; continue }
        Write-KitLog ('Remove {0}' -f $part.Name) 'STEP'
        try { & $part.Action } catch { Write-KitLog ('  {0}: {1} (cleanup continues)' -f $part.Name, $_.Exception.Message) 'WARN' }
    }
}

try {
    Assert-Administrator
    $logDir = $BootTest.Logs
    if ($RemoveLogs) { $logDir = $env:TEMP }
    Initialize-BootTestLog -Name '90-cleanup' -DryRun:$dryRun -Directory $logDir
    Write-KitLog 'Slate Operations WSL2 boot test: cleanup.' 'STEP'

    # Trust state.json only when the kit folder passes the safety check.
    $state = @{}
    $treeProblems = @(Get-BootTestTreeProblem)
    if ($treeProblems.Count -gt 0) {
        Write-KitLog ('{0} fails the safety check: {1}' -f $BootTest.Root, ($treeProblems -join '; ')) 'WARN'
        Write-KitLog 'Cleanup ignores state.json. It does not restore the power settings or the Task Scheduler log, and it does not remove WSL.' 'WARN'
        Write-KitLog 'Restore by hand if needed: Settings > System > Power > Screen and sleep.' 'WARN'
    } else {
        $state = Read-BootTestState
    }

    if ($P1Only) {
        $plan = @(Get-P1Plan)
        if ($treeProblems.Count -gt 0) { throw 'The kit folder fails the safety check; run 90-cleanup.ps1 without -P1Only.' }
        $plan += 'S1 stack in the distribution: containers, volumes (throwaway test data), images, units'
        $plan += ('P1 files in {0}: source, spike, f3-out, f4, p1-state.json, the cached F10 MSI' -f $BootTest.Root)
        Write-KitLog 'P1 cleanup will remove:'
        foreach ($item in $plan) { Write-KitLog ('  - {0}' -f $item) }
        Write-KitLog 'Caution: the S1 stack and its test data are deleted. Record the P1 results first.' 'WARN'
        if (-not $dryRun) {
            $answer = Read-Host 'Type REMOVE to continue (anything else stops)'
            if ($answer -cne 'REMOVE') { Write-KitLog 'Stopped. Nothing was removed.' 'WARN'; exit 1 }
        }
        Invoke-P1Removal -StackToo
        if (-not $dryRun) {
            # slateops-svc still exists and can change the spike folder: it empties the folder in
            # its own job, then only the empty folder is deleted here.
            if (Test-Path -LiteralPath $BootTest.Spike) {
                try {
                    $null = Invoke-SvcJob -Job 'spike-clean' -TimeoutMinutes 10 -NoThrow
                    Remove-EmptiedFolder -Path $BootTest.Spike
                } catch { Write-KitLog ('  {0}: {1}' -f $BootTest.Spike, $_.Exception.Message) 'WARN' }
            }
            # The other P1 folders are administrator-only (source, f4) or belong to slateops-f3,
            # which Invoke-P1Removal deleted before this point (f3-out).
            foreach ($path in @($BootTest.Source, $BootTest.F3Out, $BootTest.F4Dir, $BootTest.P1.StateFile)) {
                try { if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path } } catch { Write-KitLog ('  {0}: {1}' -f $path, $_.Exception.Message) 'WARN' }
            }
            foreach ($msi in @(Get-ChildItem -LiteralPath $BootTest.Cache -Filter 'wsl.*.msi' -ErrorAction SilentlyContinue)) {
                if ($msi.Name -ne ('wsl.{0}.{1}.msi' -f $BootTest.WslVersion, (Get-Architecture).ToLowerInvariant())) { Remove-PathNoFollow -Path $msi.FullName }
            }
            $kitState = Read-BootTestState
            foreach ($key in @($kitState.Keys | Where-Object { $_ -like 'p1_*' })) { $kitState.Remove($key) }
            Save-BootTestState -State $kitState
        }
        Write-KitLog 'P1 cleanup is complete. The boot-test setup stays.' 'PASS'
        exit 0
    }

    $account = Get-ServiceAccount
    $sid = $null
    if ($account) { $sid = $account.SID.Value } elseif ($state.ContainsKey('account_sid')) { $sid = [string]$state['account_sid'] }
    $tasks = @(Get-ScheduledTask -TaskPath $BootTest.TaskPath -ErrorAction SilentlyContinue)
    $execTask = $tasks | Where-Object { $_.TaskName -eq $BootTest.ExecTaskName }
    $rule = Get-NetFirewallRule -Name $BootTest.FirewallRuleName -ErrorAction SilentlyContinue
    $hyperV = Get-NetFirewallHyperVRule -Name $BootTest.HyperVRuleName -ErrorAction SilentlyContinue
    $profileObject = $null
    if ($sid) { $profileObject = Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid) -ErrorAction SilentlyContinue }
    $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    $hidden = [bool](Get-ItemProperty -LiteralPath $userList -Name $BootTest.AccountName -ErrorAction SilentlyContinue)
    $vhdx = Join-Path $BootTest.Distro 'vhd\ext4.vhdx'

    # -RemoveWsl removes WSL only when setup installed it (state says WSL was absent before).
    $removeWslPackage = $false
    $removeVmp = $false
    $wslEntry = $null
    if ($RemoveWsl) {
        $before = $null
        if ($state.ContainsKey('wsl_version_before_setup')) { $before = [string]$state['wsl_version_before_setup'] }
        if ($before -eq 'none') {
            $wslEntry = Get-WslUninstallEntry
            $removeWslPackage = [bool]$wslEntry
        } else {
            Write-KitLog ('-RemoveWsl: WSL is kept, because it existed before setup (version {0}) or the state file does not say.' -f $(if ($before) { $before } else { 'unknown' })) 'WARN'
        }
        $removeVmp = ($state.ContainsKey('vmp_enabled_by_setup') -and [bool]$state['vmp_enabled_by_setup'])
    }

    # Say what will be removed.
    $plan = @()
    if ($tasks.Count) { $plan += ('Scheduled tasks: {0}' -f (($tasks | ForEach-Object { $BootTest.TaskPath + $_.TaskName }) -join ', ')) }
    if ($account -and $execTask) { $plan += ('WSL distribution {0} of {1}, with its virtual disk and the test database' -f $BootTest.DistroName, $BootTest.AccountName) }
    elseif (Test-Path -LiteralPath $BootTest.Distro) { $plan += ('Folder {0} (distribution files)' -f $BootTest.Distro) }
    if ($rule) { $plan += ('Windows Defender Firewall rule {0}' -f $BootTest.FirewallRuleName) }
    if ($hyperV) { $plan += ('Hyper-V firewall rule {0}' -f $BootTest.HyperVRuleName) }
    if ($hidden) { $plan += ('Sign-in screen entry for {0}' -f $BootTest.AccountName) }
    if ($profileObject) { $plan += ('Profile {0}' -f $profileObject.LocalPath) }
    if ($account) { $plan += ('Local account {0} (disabled first)' -f $BootTest.AccountName) }
    if ($sid) { $plan += ('User rights of {0}: {1}' -f $sid, ($BootTest.AccountRights -join ', ')) }
    if ($state.ContainsKey('power_scheme')) {
        $plan += ('Restore power plan {0}: sleep on mains power {1} s, hibernate {2} s' -f $state['power_scheme'], $state['power_standby_ac_seconds'], $state['power_hibernate_ac_seconds'])
    }
    if ($state.ContainsKey('taskscheduler_log_enabled_before') -and (-not [bool]$state['taskscheduler_log_enabled_before'])) { $plan += 'Turn the Task Scheduler event log off again' }
    if (Test-Path -LiteralPath $BootTest.Root) {
        if ($RemoveLogs) { $plan += ('Folder {0}, logs included' -f $BootTest.Root) }
        else { $plan += ('Folder {0} except {1}' -f $BootTest.Root, $BootTest.Logs) }
    }
    if ($removeWslPackage) { $plan += ('WSL package "{0}" {1} (also for your own account)' -f $wslEntry.DisplayName, $wslEntry.DisplayVersion) }
    if ($removeVmp) { $plan += 'Windows feature VirtualMachinePlatform (setup turned it on; restart needed)' }
    $p1Plan = @(Get-P1Plan)
    $plan += $p1Plan
    if ($plan.Count -eq 0) { Write-KitLog 'Nothing from the kit was found. Nothing to remove.' 'PASS'; exit 0 }
    Write-KitLog 'Cleanup will remove or restore:'
    foreach ($item in $plan) { Write-KitLog ('  - {0}' -f $item) }
    if (-not $RemoveWsl) { Write-KitLog 'WSL itself stays installed (use -RemoveWsl to remove it, if setup installed it).' }

    if (-not $dryRun) {
        $answer = Read-Host 'Type REMOVE to continue (anything else stops)'
        if ($answer -cne 'REMOVE') { Write-KitLog 'Stopped. Nothing was removed.' 'WARN'; exit 1 }
    }

    # 0. P1 items first: the jobs that remove them need the service account and its tasks.
    if ($p1Plan.Count -gt 0) { Invoke-P1Removal }

    # 1. Boot task off.
    $startTask = $tasks | Where-Object { $_.TaskName -eq $BootTest.StartTaskName }
    if ($startTask) {
        Invoke-Step 'Disable and stop the boot task' {
            Disable-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.StartTaskName | Out-Null
            Stop-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.StartTaskName
        }
    }

    # 2. Unregister the distribution as the service account.
    $distroGone = $false
    if ($account -and $execTask) {
        if ($dryRun) { Write-KitLog ('Would: run the job "unregister" as {0}' -f $BootTest.AccountName) 'WHATIF' }
        else {
            try { Invoke-SvcJob -Job 'unregister' -TimeoutMinutes 10 | Out-Null; $distroGone = $true }
            catch { Write-KitLog ('The unregister job failed: {0}' -f $_.Exception.Message) 'WARN' }
        }
    }
    if ((-not $distroGone) -and (Test-Path -LiteralPath $vhdx) -and (-not $dryRun)) {
        Write-KitLog ('{0} still exists.' -f $vhdx) 'WARN'
        Write-KitLog 'Caution: the next step stops the WSL service. It stops all WSL distributions of all accounts, yours too.' 'WARN'
        Invoke-Step 'Stop the WSL service so the distribution disk is free' {
            Stop-Service -Name 'WSLService' -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 5
        }
    }

    # 3. Disable the account at once.
    if ($account) { Invoke-Step ('Disable the account {0}' -f $BootTest.AccountName) { Disable-LocalUser -Name $BootTest.AccountName } }

    # 4. Tasks.
    foreach ($task in $tasks) {
        Invoke-Step ('Delete task {0}{1}' -f $BootTest.TaskPath, $task.TaskName) {
            Unregister-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $task.TaskName -Confirm:$false
        }
    }
    Invoke-Step ('Delete the task folder {0}' -f $BootTest.TaskPath) {
        $scheduler = New-Object -ComObject 'Schedule.Service'
        $scheduler.Connect()
        try { $scheduler.GetFolder('\').DeleteFolder($BootTest.TaskFolder, 0) } catch { Write-KitLog '  The task folder was already gone.' }
    }

    # 5. Firewall rules.
    if ($rule) { Invoke-Step ('Delete firewall rule {0}' -f $BootTest.FirewallRuleName) { Remove-NetFirewallRule -Name $BootTest.FirewallRuleName } }
    if ($hyperV) { Invoke-Step ('Delete Hyper-V firewall rule {0}' -f $BootTest.HyperVRuleName) { Remove-NetFirewallHyperVRule -Name $BootTest.HyperVRuleName } }

    # 6. Sign-in screen entry, profile, account.
    if ($hidden) {
        Invoke-Step 'Remove the sign-in screen entry' {
            Remove-ItemProperty -LiteralPath $userList -Name $BootTest.AccountName
            $userListEmpty = @((Get-Item -LiteralPath $userList).GetValueNames()).Count -eq 0
            if ($userListEmpty -and $state.ContainsKey('userlist_key_existed') -and (-not [bool]$state['userlist_key_existed'])) {
                Remove-Item -LiteralPath $userList
                $special = Split-Path -Parent $userList
                if ((-not [bool]$state['specialaccounts_key_existed']) -and (@(Get-ChildItem -LiteralPath $special).Count -eq 0)) { Remove-Item -LiteralPath $special }
            }
        }
    }
    if ($profileObject) {
        Invoke-Step ('Delete profile {0}' -f $profileObject.LocalPath) {
            $deadline = (Get-Date).AddMinutes(2)
            while ((Get-Date) -lt $deadline) {
                $current = Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid)
                if (-not $current) { break }
                if (-not $current.Loaded) { Remove-CimInstance -InputObject $current; break }
                Start-Sleep -Seconds 5
            }
            if (Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid)) { throw 'The profile is still loaded. Restart Windows and run cleanup again.' }
        }
    }
    if ($account) { Invoke-Step ('Delete local account {0}' -f $BootTest.AccountName) { Remove-LocalUser -Name $BootTest.AccountName } }

    # 7. User rights, by SID, after the account is gone.
    if ($sid) {
        Invoke-Step ('Remove the user rights of {0}' -f $sid) {
            Initialize-LsaRightsType
            [SlateOpsBootTest.LsaRights]::Remove($sid, [string[]]$BootTest.AccountRights)
            $left = @([SlateOpsBootTest.LsaRights]::Get($sid))
            Write-KitLog ('  Rights left: {0}' -f $(if ($left.Count) { $left -join ', ' } else { 'none' }))
        }
    }

    # 8. Power and event log.
    if ($state.ContainsKey('power_scheme')) {
        Invoke-Step 'Restore Sleep and Hibernate on mains power' {
            $scheme = [string]$state['power_scheme']
            if ($null -ne $state['power_standby_ac_seconds']) {
                Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/setacvalueindex', $scheme, 'SUB_SLEEP', 'STANDBYIDLE', ([string]$state['power_standby_ac_seconds'])) | Out-Null
            }
            if ($null -ne $state['power_hibernate_ac_seconds']) {
                Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/setacvalueindex', $scheme, 'SUB_SLEEP', 'HIBERNATEIDLE', ([string]$state['power_hibernate_ac_seconds'])) | Out-Null
            }
            Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/setactive', $scheme) | Out-Null
        }
    }
    if ($state.ContainsKey('taskscheduler_log_enabled_before') -and (-not [bool]$state['taskscheduler_log_enabled_before'])) {
        Invoke-Step 'Turn the Task Scheduler event log off again' {
            $taskLog = Get-WinEvent -ListLog 'Microsoft-Windows-TaskScheduler/Operational'
            $taskLog.IsEnabled = $false
            $taskLog.SaveChanges()
        }
    }

    # 9. Folder. Remove-PathNoFollow never enters a junction or link.
    if (Test-Path -LiteralPath $BootTest.Root) {
        Invoke-Step ('Delete {0}{1}' -f $BootTest.Root, $(if ($RemoveLogs) { '' } else { ' (logs stay)' })) {
            foreach ($child in @(Get-ChildItem -LiteralPath $BootTest.Root -Force)) {
                if ((-not $RemoveLogs) -and ($child.FullName -ieq $BootTest.Logs)) { continue }
                Remove-PathNoFollow -Path $child.FullName
            }
            if ($RemoveLogs) { Remove-PathNoFollow -Path $BootTest.Root }
            elseif ($sid) {
                # The kept root must not hold an access entry for the deleted account.
                Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($BootTest.Root, '/remove:g', ('*{0}' -f $sid)) -Quiet | Out-Null
            }
        }
    }

    # Optional: WSL itself, only when setup installed it.
    if ($removeWslPackage -or $removeVmp) {
        Write-KitLog 'Caution: the next steps remove WSL for every account on this PC, yours too.' 'WARN'
        if ($removeWslPackage) {
            Invoke-Step ('Uninstall {0} {1}' -f $wslEntry.DisplayName, $wslEntry.DisplayVersion) {
                $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/x', $wslEntry.PSChildName, '/qn', '/norestart') -Wait -PassThru
                if (@(0, 3010) -notcontains $process.ExitCode) { throw ('The WSL uninstall failed with exit code {0}.' -f $process.ExitCode) }
            }
        }
        if ($removeVmp) {
            Invoke-Step 'Turn off the Windows feature VirtualMachinePlatform' {
                Disable-WindowsOptionalFeature -Online -FeatureName 'VirtualMachinePlatform' -NoRestart | Out-Null
            }
            Write-KitLog 'Restart Windows to finish.' 'WARN'
        }
    }

    Write-KitLog 'Cleanup is complete.' 'PASS'
    if (-not $RemoveLogs) { Write-KitLog ('The logs stay in {0}. Run again with -RemoveLogs to delete them.' -f $BootTest.Logs) }
    exit 0
} catch {
    Write-KitLog ('Cleanup stopped at the first error: {0}' -f $_.Exception.Message) 'ERROR'
    Write-KitLog ($_.InvocationInfo.PositionMessage) 'ERROR'
    Write-KitLog 'Fix the cause and run cleanup again; it removes only what still exists.' 'ERROR'
    exit 1
}
