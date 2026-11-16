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
    [switch]$RemoveLogs
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
    if ($plan.Count -eq 0) { Write-KitLog 'Nothing from the kit was found. Nothing to remove.' 'PASS'; exit 0 }
    Write-KitLog 'Cleanup will remove or restore:'
    foreach ($item in $plan) { Write-KitLog ('  - {0}' -f $item) }
    if (-not $RemoveWsl) { Write-KitLog 'WSL itself stays installed (use -RemoveWsl to remove it, if setup installed it).' }

    if (-not $dryRun) {
        $answer = Read-Host 'Type REMOVE to continue (anything else stops)'
        if ($answer -cne 'REMOVE') { Write-KitLog 'Stopped. Nothing was removed.' 'WARN'; exit 1 }
    }

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
