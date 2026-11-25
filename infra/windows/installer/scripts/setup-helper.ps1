<#
setup-helper.ps1 - the hidden helper that the setup program starts for each Windows-side
action (wizard spec 5.2 "How the check runs", plan F4b). Setup runs elevated; Inno Setup makes
{tmp} administrator-only, and this script runs from {tmp}\scripts (or, for maintenance, from
C:\ProgramData\SlateOps\scripts).

  powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File setup-helper.ps1
      -Action <name> -RunId <run ID> -OutFile <result .json> [action options]

The action is one name from a fixed list. The result is one JSON object in -OutFile with a safe
code and a message key (W8 maps them to the spec's copy). Progress lines go to the run log
(plan 10.1). Paths: -OutFile and -InputFile must be inside the helper's own root folder, and
every other path is fixed or comes from the administrator-only state folder.
Windows PowerShell 5.1, ASCII only.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('state-check', 'check', 'recheck', 'facts', 'time-zone', 'fix-network-private', 'remove-kit',
        'save-progress', 'clear-resume', 'restart', 'prepare-pc', 'prepare-data', 'service', 'job', 'job-result',
        'start-boot', 'windows-steps', 'account-sid', 'r7', 'provider-detect', 'drives', 'drive-check', 'prepare-backup',
        'printers', 'data-check', 'name-check', 'https-check', 'job-stop', 'report-collect', 'report-zip', 'fix-mdns',
        'uninstall-info', 'uninstall-stop', 'uninstall-data', 'remove-windows', 'kept-read', 'restore-kept', 'kept-status',
        'kept-return', 'kept-done', 'setup-remove-data', 'remove-features', 'engine-status', 'repair', 'security-code', 'update-prepare', 'update-wsl', 'update-done',
        'start-with-windows-on', 'start-with-windows-off')]
    [string]$Action,
    [Parameter(Mandatory = $true)][string]$RunId,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string]$DataRoot = '',
    [string]$SetupPath = '',
    [ValidateSet('', 'check_restart', 'feature_restart', 'continue_later', 'install_started', 'install_finished', 'key_saved')][string]$Stage = '',
    [string]$Job = '',
    [string]$InputFile = '',
    [string]$RequestId = '',
    [string]$PemFile = '',
    [ValidatePattern('^$|^[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63}){1,8}$')][string]$Domain = '',
    [ValidatePattern('^$|^[A-Z]:$')][string]$Drive = '',
    [switch]$Firmware,
    [switch]$Lid,
    [switch]$Cancel,
    [switch]$Keep,
    [switch]$DeleteBackups,
    [switch]$UseKept,
    [switch]$KeptMark,
    [switch]$Prepared,
    # DEC-0039: the label of <label>.local (the S08 short name); the full rule is Test-AddressLabel.
    [ValidatePattern('^$|^[a-z0-9]+(-[a-z0-9]+)*$')][string]$Label = '',
    [switch]$DataLeft,
    [switch]$Restored
)

# S91-6: modules load only from Windows PowerShell's own folder, never from a folder in the
# caller's module path.
$env:PSModulePath = Join-Path $PSHOME 'Modules'
foreach ($name in @('Common', 'Checks', 'Facts', 'Exec', 'Service', 'Windows', 'Report', 'Uninstall', 'Mdns')) { . (Join-Path $PSScriptRoot ('lib\{0}.ps1' -f $name)) }

$helperRoot = Split-Path -Parent $PSScriptRoot
$layout = New-SlateOpsLayout

function Assert-InsideRoot {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($helperRoot.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'path_outside_root' }
    return $full
}

function Write-HelperResult {
    # "code" and "message_key" come first in the file (P2-2; the setup program reads the first
    # "code").
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Result)
    $text = ConvertTo-HelperResultText -Result $Result -Action $Action -RunId $RunId
    $temp = $script:outPath + '.tmp'
    [System.IO.File]::WriteAllText($temp, $text, (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $script:outPath) { Remove-PathNoFollow -Path $script:outPath }
    [System.IO.File]::Move($temp, $script:outPath)
}

function Read-HelperVersion {
    return Read-SetupVersion -Path (Join-Path $PSScriptRoot 'version.json')
}

$exitCode = 0
try {
    if (-not (Test-RunId $RunId)) { throw 'run_id_invalid' }
    $script:outPath = Assert-InsideRoot $OutFile
    if (-not (Test-Administrator)) { throw 'not_administrator' }
    # W14-D5: the step that runs, for the setup program (spec 7.6).
    Set-HelperProgressFile -Path ($script:outPath + '.progress')

    # Log: the state tree's setup folder when it exists and passes the quick check, else the
    # helper's own folder (before S07 creates the state tree, plan 10.1 item 4).
    # P2-3: the SID from the administrator-only record, also after a partial service step.
    $serviceSid = Get-RecordedServiceSid -Layout $layout
    # W9: uninstall and maintenance runs log in their own folders (plan 10.1 item 4).
    $kind = 'setup'
    if ($RunId -like 'uninstall-*') { $kind = 'uninstall' } elseif ($RunId -like 'maintenance-*') { $kind = 'maintenance' }
    $logDir = Open-LogDirectory -Layout $layout -Kind $kind -ServiceSid $serviceSid
    if (-not $logDir) {
        $logDir = Join-Path $helperRoot 'logs'
        if (-not (Test-Path -LiteralPath $logDir)) { [void][System.IO.Directory]::CreateDirectory($logDir) }
    }
    Start-RunLog -RunId $RunId -Directory $logDir -Append -NoConsole
    Write-RunLog ('helper.{0}' -f $Action) 'INFO' ('start (setup helper, {0})' -f $PSScriptRoot)

    $result = [ordered]@{}
    switch ($Action) {
        'state-check' {
            $step = Test-StateFolder -Layout $layout -ServiceSid $serviceSid
            # AC-O2: the entries of setup's own removed account (an earlier removal) are repaired.
            if (-not $serviceSid) { $step = Repair-StaleStateFolder -Layout $layout -Step $step }
            if ($step.code -eq 'safe') { $null = Invoke-LogRotation -Directory (Join-Path $layout.Logs 'setup') }
            $result = $step
            # W8: the installed version decides M01 or M05 (spec 4.1).
            $setupVersion = ''
            try { $setupVersion = (Read-HelperVersion).version } catch { $setupVersion = '' }
            $program = Get-InstalledProgram
            $installed = [string]$program.version
            $unreadable = ($program.state -eq 'unreadable')
            if ($unreadable) { Write-RunLog 'setup.entry' 'WARN' 'the installed program record cannot be read; setup removes nothing' }
            if ($step.code -eq 'safe') {
                # DEC-0041 (AC-W4): a progress file that cannot be read still counts as a record of
                # an earlier run (Test-SetupLeftover), so it is removed, not resumed.
                $progress = $null
                try { $progress = Read-SetupProgress -Layout $layout } catch { Write-RunLog 'setup.progress' 'WARN' ('progress not readable: {0}' -f $_.Exception.Message) }
                $result.values = @{ entry = (Get-SetupEntry -Progress $progress -Installed $installed -SetupVersion $setupVersion -Leftover:(Test-SetupLeftover -Layout $layout) -ProgramUnreadable:$unreadable) }
            }
            elseif ($step.code -eq 'absent') { $result.values = @{ entry = (Get-SetupEntry -Progress $null -Installed $installed -SetupVersion $setupVersion -ProgramUnreadable:$unreadable) } }
        }
        { $_ -in @('check', 'recheck') } {
            $pinned = [version]'0.0.0.0'
            try { $pinned = (Read-HelperVersion).wsl_version } catch { Write-RunLog 'helper.check' 'WARN' 'version.json not readable; C26 compares with 0.0.0.0' }
            $only = @()
            if ($Action -eq 'recheck') { $only = $SlateOpsCheck.RecheckIds }
            $facts = Get-PcCheckFacts -ProgressJob $Action -ProgressIds $only
            $items = @(Invoke-PcCheck -Facts $facts -PinnedWsl $pinned -Only $only)
            foreach ($item in $items) { Write-RunLog ('check.{0}' -f $item.id.ToLowerInvariant()) 'INFO' ('{0} {1}' -f $item.class, $item.code) }
            $verdict = Get-PcVerdict -Results $items
            Write-RunLog 'check.verdict' 'INFO' $verdict.verdict
            # W8: each row is ordered (id, class, code, values), so the setup program finds the
            # rows by their first key.
            $rows = @($items | ForEach-Object { [ordered]@{ id = $_.id; class = $_.class; code = $_.code; values = $_.values } })
            $result = @{ code = $verdict.verdict; message_key = $verdict.message_key; values = @{ verdict = $verdict; rows = $rows } }
        }
        'facts' {
            $setupVersion = ''
            try { $setupVersion = (Read-HelperVersion).version } catch { $setupVersion = '' }
            $dataDrive = ''
            if ($DataRoot -and (Test-DataRootPath $DataRoot)) { $dataDrive = $DataRoot.Substring(0, 2) }
            $facts = Get-EnvironmentFacts -SetupVersion $setupVersion -DataDrive $dataDrive
            Write-RunLog 'facts' 'INFO' (Protect-LogText (ConvertTo-JsonText $facts))
            $result = @{ code = 'recorded'; message_key = 'facts.recorded'; values = $facts }
        }
        'time-zone' {
            $windowsId = (Get-TimeZone).Id
            $iana = ConvertTo-IanaTimeZone -WindowsId $windowsId
            Write-RunLog 'helper.time_zone' 'INFO' ('{0} -> {1}' -f $windowsId, $iana)
            if ($iana) { $result = New-StepResult -Code 'mapped' -MessageKey 'setup.time_zone.mapped' -Values @{ windows_id = $windowsId; iana = $iana } }
            else { $result = New-StepResult -Code 'unmapped' -MessageKey 'setup.time_zone.unmapped' -Values @{ windows_id = $windowsId } }
        }
        'fix-network-private' {
            $lan = Get-LanFact
            if (-not $lan) { $result = New-StepResult -Code 'no_network' -MessageKey 'check.c09.not_connected' }
            else {
                Write-RunLog 'check.c10.fix' 'INFO' ('network "{0}" was {1}' -f $lan.network_name, $lan.category)
                Set-NetConnectionProfile -InterfaceIndex $lan.interface_index -NetworkCategory Private
                $result = New-StepResult -Code 'fixed' -MessageKey 'check.c10.fixed'
            }
        }
        'remove-kit' { $result = Remove-KitLeftovers }
        'uninstall-info' {
            # U01 and U02 values, from Windows records only (plan 3.2 rule 2).
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            $disk = Get-Item -LiteralPath (Join-Path $layout.Distro 'ext4.vhdx') -Force -ErrorAction SilentlyContinue
            $backup = [string](Get-DictValue (Read-WindowsChanges -Layout $layout) 'backup_folder')
            if ($backup -cnotmatch '^[A-Z]:\\SlateOps-backups$') { $backup = '' }
            $result = New-StepResult -Code 'info' -MessageKey 'uninstall.info' -Values @{ data_root = $state.data_root; backup_folder = $backup; disk_gb = $(if ($disk) { [int][math]::Ceiling($disk.Length / 1GB) } else { 0 }) }
        }
        'uninstall-stop' {
            # U03 stage 1: the start task off; with "Keep my data" the engine stops the services
            # cleanly and gives the kept.json values (prepare-uninstall, plan 9.1).
            Disable-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName -ErrorAction SilentlyContinue | Out-Null
            Stop-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName -ErrorAction SilentlyContinue
            $result = New-StepResult -Code 'stopped' -MessageKey 'uninstall.stopped'
            if ($Keep) {
                $jobResult = Invoke-ExecJobAndWait -Layout $layout -Job 'prepare-uninstall' -RunId $RunId -InputText ('{{"run_id":"{0}"}}' -f $RunId) -TimeoutSeconds 600
                $info = $null
                if ((Get-DictValue $jobResult 'exit_code') -eq 0) { try { $info = Read-EngineOutput -Layout $layout -Result $jobResult } catch { $info = $null } }
                if (-not (Test-KeptInfo $info)) {
                    $result = New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = [string](Get-DictValue $jobResult 'code') }
                    # Nothing was removed: the server starts again (Docker comes back with the next
                    # Linux start).
                    Restore-ServerAfterKeepFailure -Layout $layout -RunId $RunId
                }
                else { Write-JsonFile -Path (Join-Path $layout.State 'kept-pending.json') -Value ([ordered]@{ instance_id = [string]$info['instance_id']; business_name = [string]$info['business_name']; public_host = [string]$info['public_host'] }) }
            }
        }
        'uninstall-data' {
            # U03 stage 2. Keep: stop the distribution, move the disk, check (F3), unregister, check
            # again. Delete: unregister, delete the data folder (S91-2 rule), the backups if chosen.
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            if ($Keep) {
                $info = Read-JsonFile -Path (Join-Path $layout.State 'kept-pending.json')
                $null = Invoke-ExecJobAndWait -Layout $layout -Job 'terminate-distro' -RunId $RunId -TimeoutSeconds 120
                $version = ''
                try { $version = (Read-SetupVersion -Path (Join-Path $layout.Scripts 'version.json')).version } catch { $version = '' }
                $backupFolder = [string](Get-DictValue (Read-WindowsChanges -Layout $layout) 'backup_folder')
                $result = Move-KeptDisk -Layout $layout -Info $info -Version $version -BackupFolder $backupFolder -AccountSid $serviceSid -Record
                if ($result.code -eq 'kept') {
                    $bytes = [long]$result.values.bytes
                    $jobResult = Invoke-ExecJobAndWait -Layout $layout -Job 'unregister-distro' -RunId $RunId -TimeoutSeconds 300
                    if (((Get-DictValue $jobResult 'exit_code') -ne 0) -or -not (Test-KeptAfterUnregister -Layout $layout -Bytes $bytes)) {
                        $result = New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'unregister' }
                        # Still registered: the disk goes back where the distribution expects it.
                        $kept = Get-KeptPaths -Layout $layout
                        if ((Test-Path -LiteralPath $kept.Disk) -and -not (Test-Path -LiteralPath $kept.Live)) { [System.IO.File]::Move($kept.Disk, $kept.Live) }
                    } else { Clear-DataTreeForKeep -Layout $layout -ServiceSid $serviceSid }
                }
                if ($result.code -ne 'kept') { Restore-ServerAfterKeepFailure -Layout $layout -RunId $RunId }
            } else {
                $jobResult = Invoke-ExecJobAndWait -Layout $layout -Job 'unregister-distro' -RunId $RunId -TimeoutSeconds 300
                Write-RunLog 'uninstall.data' 'INFO' ('unregister: {0}' -f (Get-DictValue $jobResult 'code'))
                $result = Remove-DataFolder -DataRoot $state.data_root
                if (($result.code -eq 'removed') -and $DeleteBackups) {
                    $backups = Remove-BackupFolder -Folder ([string](Get-DictValue (Read-WindowsChanges -Layout $layout) 'backup_folder')) -ServiceSid $serviceSid
                    if ($backups.code -ne 'removed') { $result = $backups }
                }
            }
        }
        # DEC-0041 (AC-W3, AC-W4): the setup removal's data step (kept data never deleted) and
        # the WSL and Virtual Machine Platform step (only what setup turned on, no other
        # distribution); both before remove-windows, which removes the records they read.
        'setup-remove-data' { $result = Remove-SetupData -Layout $layout -RunId $RunId }
        'remove-features' { $result = Remove-SetupFeatures -Layout $layout }
        # W9 review item 4: with the data folder left over, the scripts stay for Save report.
        'remove-windows' { $result = Remove-WindowsParts -Layout $layout -DataLeft:$DataLeft }
        'kept-read' {
            $setupVersion = ''
            try { $setupVersion = (Read-HelperVersion).version } catch { $setupVersion = '0.0.0' }
            # Design N-1: -Restored reads kept.json after restore-kept moved the disk back.
            $result = Get-KeptData -DataRoot $DataRoot -SetupVersion $setupVersion -Restored:$Restored
        }
        'restore-kept' {
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            $result = Restore-KeptDisk -Layout $layout
            # The kept backup folder gets the new account's rights and goes back into the record.
            if ($result.code -eq 'restored') {
                $kept = Read-JsonFile -Path (Get-KeptPaths -Layout $layout).Record
                $folder = [string](Get-DictValue $kept 'backup_folder')
                $old = [string](Get-DictValue $kept 'account_sid')
                if ($old -notmatch $SlateOpsKept.SidPattern) { $old = '' }
                $done = $false
                if (($folder -cmatch '^[A-Z]:\\SlateOps-backups$') -and (Test-Path -LiteralPath $folder)) {
                    $backup = Initialize-BackupFolder -Drive $folder.Substring(0, 2) -DataRoot $state.data_root -ServiceSid $serviceSid -Layout $layout -OldSid $old
                    Write-RunLog 'setup.kept' 'INFO' ('backup folder {0}: {1}' -f $folder, $backup.code)
                    # W9 gap 1: the removed account's entries and owned items go (P2-3).
                    if ($backup.code -eq 'ready') {
                        if ($old -and ($old -ne $serviceSid)) { $null = Remove-OldAccountAccess -Folder $folder -OldSid $old -ServiceSid $serviceSid }
                        $done = $true
                    }
                }
                # Option b (parent decision): with the drive out, the record keeps the folder and the
                # replaced account, so Repair finishes both when the drive is back (kept.json goes
                # at the end of this install).
                if ((-not $done) -and ($folder -cmatch '^[A-Z]:\\SlateOps-backups$')) {
                    Write-RunLog 'setup.kept' 'INFO' ('backup folder {0} not ready; Repair sets its rights later' -f $folder)
                    $record = Read-WindowsChanges -Layout $layout
                    $record['backup_folder'] = $folder
                    if ($old -and ($old -ne $serviceSid)) { $record['kept_account_sid'] = $old }
                    Save-WindowsChanges -Layout $layout -Record $record
                }
            }
        }
        'kept-status' {
            # F3 at reinstall: the engine must report the instance ID of kept.json.
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            $version = '0.0.0'
            try { $version = (Read-HelperVersion).version } catch { $version = '0.0.0' }
            $status = Get-EngineStatus -Layout $layout -RunId $RunId -WindowsPartVersion $version
            if (Test-KeptInstance -Layout $layout -Status $status) { $result = New-StepResult -Code 'match' -MessageKey 'setup.kept.match' }
            else { $result = New-StepResult -Code 'mismatch' -MessageKey 'setup.kept.mismatch' }
        }
        'kept-return' {
            # A failure after the kept disk moved back: the Keep path again, never a delete
            # (advisor item 1).
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            $null = Invoke-ExecJobAndWait -Layout $layout -Job 'terminate-distro' -RunId $RunId -TimeoutSeconds 120
            $result = Move-KeptDisk -Layout $layout
            if ($result.code -eq 'kept') {
                $jobResult = Invoke-ExecJobAndWait -Layout $layout -Job 'unregister-distro' -RunId $RunId -TimeoutSeconds 300
                if (((Get-DictValue $jobResult 'exit_code') -ne 0) -or -not (Test-KeptAfterUnregister -Layout $layout -Bytes ([long]$result.values.bytes))) {
                    $result = New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'unregister' }
                } else { $result = New-StepResult -Code 'returned' -MessageKey 'setup.kept.returned' }
            }
        }
        'kept-done' {
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            $kept = Get-KeptPaths -Layout $layout
            if ((Test-Path -LiteralPath $kept.Folder) -and -not (Test-Path -LiteralPath $kept.Disk)) { Remove-PathNoFollow -Path $kept.Folder }
            $result = New-StepResult -Code 'done' -MessageKey 'setup.kept.done'
        }
        'start-with-windows-on' {
            $null = Set-StartWithWindows -Layout $layout -On $true
            $result = New-StepResult -Code 'start_with_windows_on' -MessageKey 'maintenance.autostart.on'
        }
        'start-with-windows-off' {
            $null = Set-StartWithWindows -Layout $layout -On $false
            $result = New-StepResult -Code 'start_with_windows_off' -MessageKey 'maintenance.autostart.off'
        }
        'engine-status' {
            # Owner request 2026-11-25: with Start with Windows off and no Start since this PC
            # started, nothing asks the engine, because an Exec job would start Linux and Docker.
            if (-not (Test-StartAllowed -Layout $layout)) {
                $result = New-StepResult -Code 'not_started' -MessageKey 'maintenance.status.not_started' -Values @{ start_with_windows = $false }
                break
            }
            $version = '0.0.0'
            try { $version = (Read-HelperVersion).version } catch { $version = '0.0.0' }
            $result = Get-EngineStatus -Layout $layout -RunId $RunId -WindowsPartVersion $version
            if ($result.code -eq 'ok') { $result.values.backup_folder = [string](Get-DictValue (Read-WindowsChanges -Layout $layout) 'backup_folder') }
            # W9 review item 5 (plan 10.7): the network against the recorded rule range.
            $result.values.network_changed = (Test-NetworkChanged -Layout $layout)
            $result.values.start_with_windows = (Get-StartWithWindows -Layout $layout).on
        }
        'repair' { $result = Invoke-Repair -Layout $layout }
        # W13b part 2 (plan 7.4 setup-program path, M05): the five receive parts of this setup
        # into the data folder's payload folder; the WSL step; after the engine succeeded, the
        # scripts that the tasks run (P2-2).
        'update-prepare' {
            $version = Read-HelperVersion
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            $result = Copy-PayloadPart -Layout $layout -SourceDir (Join-Path $helperRoot 'payload') -Names @(Get-ReceivePartNames -Version $version.version) -ServiceSid $serviceSid
        }
        'update-wsl' {
            $version = Read-HelperVersion
            $result = Invoke-UpdateWsl -Layout $layout -RunId $RunId -Version $version -MsiPath (Join-Path (Join-Path $helperRoot 'payload') $version.wsl_msi_name)
        }
        'update-done' {
            $result = Install-ScriptsCopy -Layout $layout -SourceDir $PSScriptRoot
            # Parent decision (DEC-0036): the receive parts of other versions go. A failure here
            # is logged only; the update itself is done.
            if ($result.code -eq 'copied') {
                try {
                    $state = Read-InstallState -Layout $layout
                    Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
                    $null = Remove-OldPayloadParts -Layout $layout -Version (Read-HelperVersion).version -ServiceSid $serviceSid
                } catch { Write-RunLog 'update.payload' 'WARN' ('old parts not removed: {0}' -f $_.Exception.Message) }
            }
        }
        'security-code' { $result = Get-SecurityCodeFromStore -Layout $layout }
        'fix-mdns' {
            # C17 "Fix it for me": turns on the existing built-in rule for Private networks only;
            # never creates a rule; the old state goes to the log (spec 5.3, 12 item 4).
            $mdns = Get-MdnsFact
            if ((-not $mdns.private_rule) -or $mdns.rule_from_policy) { $result = New-StepResult -Code 'policy' -MessageKey 'check.c17.policy' }
            else {
                $rule = Get-NetFirewallRule -Name $mdns.private_rule
                Write-RunLog 'check.c17.fix' 'INFO' ('rule {0} was enabled {1}, profile {2}' -f $rule.Name, $rule.Enabled, $rule.Profile)
                Enable-NetFirewallRule -Name $mdns.private_rule
                $result = New-StepResult -Code 'fixed' -MessageKey 'check.c17.fixed'
            }
        }
        'save-progress' {
            if (-not $Stage) { throw 'stage_missing' }
            $ready = Initialize-StateFolder -Layout $layout -ServiceSid $serviceSid
            if ($ready.code -ne 'ready') { $result = $ready; break }
            $marks = @{}
            # W9 review item 1: a kept reinstall stays kept on resume.
            if ($KeptMark) { $marks.kept = $true }
            # AC-W9: S05 ran before this check restart, so the resume goes on after S05.
            if ($Prepared) { $marks.prepared = $true }
            $saverVersion = ''
            try { $saverVersion = (Read-HelperVersion).version } catch { $saverVersion = '' }
            Save-SetupProgress -Layout $layout -Stage $Stage -RunId $RunId -Marks $marks -SetupVersion $saverVersion
            if (@('check_restart', 'feature_restart') -contains $Stage) { $result = Register-SetupResume -SetupPath $SetupPath }
            else { $result = New-StepResult -Code 'saved' -MessageKey 'setup.progress.saved' }
        }
        'clear-resume' {
            if ($Cancel -and (Test-Path -LiteralPath $layout.State)) { Assert-TreeWritable -Tree $layout.StateTree -Directory $layout.State -ServiceSid $serviceSid }
            $result = Clear-SetupResume -Layout $layout -Progress:$Cancel
        }
        'restart' { $result = Invoke-PcRestart -Firmware:$Firmware }
        'prepare-pc' {
            $version = Read-HelperVersion
            $ready = Initialize-StateFolder -Layout $layout -ServiceSid $serviceSid
            if ($ready.code -ne 'ready') { $result = $ready; break }
            Write-HelperProgress -Job 'pc' -Number 1 -Total 3 -Key 'vmp'
            $feature = Enable-VirtualMachinePlatform -Layout $layout
            $msi = Join-Path (Join-Path $helperRoot 'payload') $version.wsl_msi_name
            Write-HelperProgress -Job 'pc' -Number 2 -Total 3 -Key 'wsl'
            $wsl = Install-WslPackage -Layout $layout -MsiPath $msi -Sha256 $version.wsl_msi_sha256 -PinnedVersion $version.wsl_version
            Write-HelperProgress -Job 'pc' -Number 3 -Total 3 -Key 'check'
            $restart = [bool]$feature.values.restart_needed -or ($wsl.values.ContainsKey('restart_needed') -and [bool]$wsl.values.restart_needed)
            if (@('present', 'installed') -notcontains $wsl.code) { $result = $wsl }
            else { $result = New-StepResult -Code 'prepared' -MessageKey 'prepare.prepared' -Values @{ restart_needed = $restart; feature = $feature.code; wsl = $wsl.code } }
        }
        # DEC-0041 (AC-W1): S07 Next, read only; the data folder is made on S12.
        'data-check' { $result = Test-DataFolderChoice -DataRoot $DataRoot -AllowKept:$UseKept }
        'prepare-data' {
            # S07, and every resume with the background preparation not done (TASK-0097 AC-1).
            $result = Invoke-PrepareData -Layout $layout -DataRoot $DataRoot -ScriptsDir $PSScriptRoot -PayloadDir (Join-Path $helperRoot 'payload') -Version (Read-HelperVersion) -ServiceSid $serviceSid -AllowKept:$UseKept -Label $Label
        }
        'name-check' {
            # DEC-0039 (P-3 a): S08 Next asks the network whether another device answers for
            # <label>.local; a check, no work: nothing is written.
            if (-not (Test-AddressLabel $Label)) { $result = New-StepResult -Code 'label_invalid' -MessageKey 'setup.name.label_invalid'; break }
            $inUse = $null
            try { $inUse = Test-MdnsNameInUse -Name $Label } catch { Write-RunLog 'setup.name' 'WARN' ('probe failed: {0}' -f $_.Exception.Message) }
            if ($inUse -eq $true) { $result = New-StepResult -Code 'in_use' -MessageKey 'setup.name.in_use' }
            elseif ($inUse -eq $false) { $result = New-StepResult -Code 'free' -MessageKey 'setup.name.free' }
            else { $result = New-StepResult -Code 'unreadable' -MessageKey 'setup.name.unreadable' }
        }
        'service' {
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            $result = Install-ServiceAccountAndTasks -Layout $layout
        }
        'job' {
            $bytes = New-Object byte[] 0
            if ($InputFile) { $bytes = [System.IO.File]::ReadAllBytes((Assert-InsideRoot $InputFile)) }
            Assert-TreeWritable -Tree $layout.StateTree -Directory $layout.Requests -ServiceSid $serviceSid
            $id = Submit-ExecRequest -Layout $layout -Job $Job -RunId $RunId -InputBytes $bytes -RequestId $RequestId
            $result = New-StepResult -Code 'started' -MessageKey 'exec.started' -Values @{ request_id = $id }
        }
        'job-result' {
            $value = Get-ExecResult -Layout $layout -RequestId $RequestId
            if ($null -eq $value) {
                $info = Get-ScheduledTaskInfo -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.ExecTaskName
                # W8 correction 5: the wizard asks once, at its time limit; a sign-in failure of the
                # account is named (spec 7.5).
                $result = New-StepResult -Code 'waiting' -MessageKey 'exec.waiting' -Values @{ last_task_result = [long]$info.LastTaskResult; logon_failed = (Test-TaskLogonFailure -LastResult ([long]$info.LastTaskResult)) }
            } else {
                $values = @{ exec = $value }
                if (((Get-DictValue $value 'job') -eq 'log-bundle') -and ((Get-DictValue $value 'exit_code') -eq 0)) {
                    $output = Read-EngineOutput -Layout $layout -Result $value
                    $values.bundle = Save-LogBundle -Output $output -DestinationPath (Join-Path $helperRoot ('linux-{0}.tar.gz' -f $RunId))
                }
                # AC-O9: a refused job's detail goes to this setup log (Save report holds it) and
                # to the wizard, which shows it under Details on S13.
                if ((Get-DictValue $value 'exit_code') -ne 0) {
                    $detail = Get-EngineRefusalDetail -Layout $layout -Result $value
                    if ($detail) {
                        Write-RunLog ('exec.{0}' -f (Get-DictValue $value 'job')) 'WARN' ('refused {0}: {1}' -f (Get-DictValue $value 'code'), $detail)
                        $values.detail = $detail
                    }
                }
                # P2-3: a failed update names its journal state and the space it needs.
                if (((Get-DictValue $value 'job') -eq 'update') -and ((Get-DictValue $value 'exit_code') -ne 0)) {
                    $outcome = Get-UpdateOutcome -Layout $layout -Result $value
                    $values.update_state = $outcome.update_state
                    $values.needs_gb = $outcome.needs_gb
                }
                $result = New-StepResult -Code 'done' -MessageKey 'exec.done' -Values $values
            }
        }
        'start-boot' {
            # Owner request 2026-11-25: a start from setup or the settings program counts until
            # the next PC start, also when Start with Windows is off.
            $null = Set-StartWithWindows -Layout $layout -Started
            Start-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName
            $result = New-StepResult -Code 'started' -MessageKey 'setup.boot.started'
        }
        'windows-steps' {
            $lan = Get-LanFact
            if (-not $lan) { $result = New-StepResult -Code 'no_network' -MessageKey 'check.c09.not_connected'; break }
            $cidr = ConvertTo-NetworkCidr -Address $lan.address -PrefixLength $lan.prefix_length
            Assert-TreeWritable -Tree $layout.StateTree -Directory $layout.State -ServiceSid $serviceSid
            # DEC-0039: the address is the stored label (install.json), not the computer name.
            $hostName = Get-InstallAddressLabel -Layout $layout
            if (-not $hostName) { $result = New-StepResult -Code 'label_missing' -MessageKey 'install.windows.label_missing'; break }
            $steps = @()
            Write-HelperProgress -Job 'win' -Number 1 -Total 4 -Key 'firewall'
            $steps += Set-FirewallRules -Layout $layout -Cidr $cidr
            Write-HelperProgress -Job 'win' -Number 2 -Total 4 -Key 'hosts'
            $steps += Set-HostsEntry -Layout $layout -HostName ('{0}.local' -f $hostName)
            $pem = [System.IO.File]::ReadAllText((Assert-InsideRoot $PemFile), [System.Text.Encoding]::ASCII)
            Write-HelperProgress -Job 'win' -Number 3 -Total 4 -Key 'trust'
            $ca = Install-TrustedCa -Layout $layout -Pem $pem
            $steps += $ca
            # 7.6: win.lid when the person chose it on S02 (C22), else win.power.
            if ($Lid) { Write-HelperProgress -Job 'win' -Number 4 -Total 4 -Key 'lid' }
            else { Write-HelperProgress -Job 'win' -Number 4 -Total 4 -Key 'power' }
            $steps += Set-KeepAwake -Layout $layout -Lid:$Lid
            $failed = @($steps | Where-Object { @('added', 'set') -notcontains $_.code })
            if ($failed.Count -gt 0) { $result = $failed[0] }
            else { $result = New-StepResult -Code 'done' -MessageKey 'install.windows.done' -Values @{ security_code = $ca.values.security_code } }
        }
        'account-sid' {
            # The SID for the pipe's access list (plan 3.2 check 1).
            if ($serviceSid) { $result = New-StepResult -Code 'found' -MessageKey 'setup.account.found' -Values @{ sid = $serviceSid } }
            else { $result = New-StepResult -Code 'missing' -MessageKey 'setup.account.missing' }
        }
        'r7' { $result = Get-PasswordPolicyState }
        'provider-detect' { $result = Get-MailProvider -Domain $Domain }
        'drives' {
            # Ordered rows, "letter" first, so the setup program finds each row by it.
            $rows = @(Get-DriveFact | ForEach-Object { [ordered]@{ letter = $_.letter; drive_type = $_.drive_type; file_system = $_.file_system; free_bytes = $_.free_bytes; compressed = $_.compressed; encrypted = $_.encrypted } })
            $result = New-StepResult -Code 'listed' -MessageKey 'setup.drives.listed' -Values @{ drives = $rows }
        }
        'drive-check' { $result = Test-BackupDrive -Drive $Drive }
        'prepare-backup' {
            $state = Read-InstallState -Layout $layout
            $result = Initialize-BackupFolder -Drive $Drive -DataRoot $state.data_root -ServiceSid $serviceSid -Layout $layout
        }
        'printers' { $result = New-StepResult -Code 'listed' -MessageKey 'setup.printers.listed' -Values @{ printers = @(Get-PrinterFact) } }
        'https-check' { $result = Test-HttpsFromWindows -Layout $layout }
        'job-stop' {
            Stop-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.ExecTaskName -ErrorAction SilentlyContinue
            $result = New-StepResult -Code 'stopped' -MessageKey 'exec.stopped'
        }
        'report-collect' {
            $innoLog = ''
            if ($InputFile) { $innoLog = Assert-InsideRoot $InputFile }
            $bundle = Join-Path $helperRoot ('linux-{0}.tar.gz' -f $RunId)
            $staging = Join-Path $helperRoot ('report-{0}' -f $RunId)
            $trusted = ((Test-StateFolder -Layout $layout -ServiceSid $serviceSid).code -eq 'safe')
            $version = ''
            try { $version = (Read-HelperVersion).version } catch { $version = '' }
            $absent = ((Test-StateFolder -Layout $layout -ServiceSid $serviceSid).code -eq 'absent')
            $made = New-ReportStaging -Layout $layout -StagingDir $staging -RunId $RunId -InnoLog $innoLog -LinuxBundle $bundle -SetupVersion $version -StateTrusted:$trusted -StateAbsent:$absent -HelperLogs (Join-Path $helperRoot 'logs')
            $result = New-StepResult -Code 'collected' -MessageKey 'report.collected' -Values $made
        }
        'report-zip' {
            $staging = Join-Path $helperRoot ('report-{0}' -f $RunId)
            $path = Complete-Report -StagingDir $staging -RunId $RunId
            Remove-PathNoFollow -Path $staging
            $result = New-StepResult -Code 'saved' -MessageKey 'report.saved' -Values @{ path = $path }
        }
    }
    Write-RunLog ('helper.{0}' -f $Action) 'INFO' ('result {0}' -f $result.code)
    Write-HelperResult -Result $result
} catch {
    $code = $_.Exception.Message
    if ($code -notmatch '^[a-z0-9_]{1,64}$') { $code = 'helper_failed' }
    try { Write-RunLog ('helper.{0}' -f $Action) 'ERROR' ('{0} {1}' -f $_.Exception.Message, $_.InvocationInfo.PositionMessage) } catch { $null = $_ }
    try { if ($script:outPath) { Write-HelperResult -Result @{ code = $code; message_key = ('helper.{0}' -f $code) } } } catch { $null = $_ }
    $exitCode = 1
}
exit $exitCode
