# Uninstall.ps1 - uninstall, keep data, reinstall with kept data, Repair (plan 9.1 to 9.3, 10.3
# F3, 10.7; wizard spec U01 to U04, S07 kept-data card, M01; W9).
#
# Every removal works from a Windows-side record (state\windows-changes.json, state\install.json),
# never from a Linux value (plan 3.2 rule 2). A path is deleted only when it passes its shape
# check, and a link is never followed. Windows PowerShell 5.1, ASCII only.

$SlateOpsKept = @{
    Folder      = 'kept'
    Disk        = 'ext4.vhdx'
    Record      = 'kept.json'
    BackupName  = 'SlateOps-backups'
    InstancePattern = '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'
    HostPattern = '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.local$'
}

# ---------------------------------------------------------------------------
# An Exec job, waited for here (uninstall and maintenance run one step at a time)
# ---------------------------------------------------------------------------

function Invoke-ExecJobAndWait {
    # Submits one allow-listed job and waits for its result. Returns the Exec result, or a
    # result with code job_timeout.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][string]$Job,
        [Parameter(Mandatory = $true)][string]$RunId,
        [string]$InputText = '',
        [int]$TimeoutSeconds = 600
    )
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($InputText)
    $id = Submit-ExecRequest -Layout $Layout -Job $Job -RunId $RunId -InputBytes $bytes
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        $result = Get-ExecResult -Layout $Layout -RequestId $id
        if ($null -ne $result) { return $result }
    }
    Write-RunLog ('exec.{0}' -f $Job) 'WARN' ('no result in {0} s' -f $TimeoutSeconds)
    return @{ code = 'job_timeout'; exit_code = 3; job = $Job }
}

function Restore-ServerAfterKeepFailure {
    # A failed keep path after prepare-uninstall (TASK-0096 engine carry): prepare-uninstall
    # stops the runner timer and Docker but not the containers, and the start task alone does
    # not bring them back. The distribution is terminated (as the account, through Exec), so the
    # next Linux start runs Docker and the stack again; then the start task is on and started.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$RunId)
    $job = Invoke-ExecJobAndWait -Layout $Layout -Job 'terminate-distro' -RunId $RunId -TimeoutSeconds 120
    Write-RunLog 'uninstall.keep' 'WARN' ('keep path failed; distribution terminated: {0}' -f (Get-DictValue $job 'code'))
    Enable-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName -ErrorAction SilentlyContinue | Out-Null
    Start-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName -ErrorAction SilentlyContinue
}

function Get-EngineStatus {
    # The engine status (plan 9.3): safe codes only. instance_id is shape-checked and used only
    # to compare with kept.json (F3); no value becomes a path or an argument.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$RunId, [string]$WindowsPartVersion = '0.0.0')
    $wsl = Get-WslPackageVersion
    if ($null -eq $wsl) { return New-StepResult -Code 'unreachable' -MessageKey 'maintenance.status.unreachable' }
    $request = '{{"run_id":"{0}","windows_part_version":"{1}","wsl_version":"{2}"}}' -f $RunId, $WindowsPartVersion, $wsl.ToString()
    $result = Invoke-ExecJobAndWait -Layout $Layout -Job 'status' -RunId $RunId -InputText $request -TimeoutSeconds 120
    if ((Get-DictValue $result 'exit_code') -ne 0) { return New-StepResult -Code 'unreachable' -MessageKey 'maintenance.status.unreachable' }
    try { $output = Read-EngineOutput -Layout $Layout -Result $result } catch { return New-StepResult -Code 'unreachable' -MessageKey 'maintenance.status.unreachable' }
    $values = @{}
    foreach ($key in @('state', 'backup')) {
        $value = [string](Get-DictValue $output $key)
        if ($value -cmatch '^[a-z_]{1,32}$') { $values[$key] = $value }
    }
    $instance = [string](Get-DictValue $output 'instance_id')
    if ($instance -cmatch $SlateOpsKept.InstancePattern) { $values.instance_id = $instance }
    return New-StepResult -Code 'ok' -MessageKey 'maintenance.status.ok' -Values $values
}

# ---------------------------------------------------------------------------
# Kept data (plan 9.1 "Keep my data", 9.2, 10.3 F3)
# ---------------------------------------------------------------------------

function Get-KeptPaths {
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $folder = Join-Path $Layout.DataRoot $SlateOpsKept.Folder
    return @{ Folder = $folder; Disk = (Join-Path $folder $SlateOpsKept.Disk); Record = (Join-Path $folder $SlateOpsKept.Record); Live = (Join-Path $Layout.Distro $SlateOpsKept.Disk) }
}

function Test-NoLink {
    param([Parameter(Mandatory = $true)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    return (-not $item) -or (-not ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint))
}

function Test-KeptInfo {
    # The prepare-uninstall fields, shape-checked before they reach kept.json.
    param([AllowNull()][System.Collections.IDictionary]$Info)
    if ($null -eq $Info) { return $false }
    $name = [string](Get-DictValue $Info 'business_name')
    return ([string](Get-DictValue $Info 'instance_id') -cmatch $SlateOpsKept.InstancePattern) -and
        ([string](Get-DictValue $Info 'public_host') -cmatch $SlateOpsKept.HostPattern) -and
        ($name.Length -ge 1) -and ($name.Length -le 200) -and ($name -notmatch '[\x00-\x1f\x7f]')
}

function Move-KeptDisk {
    # Keep my data: the disk moves to <data folder>\kept with a rename on the same drive, then F3
    # checks it before anything is removed: the kept file has the old size and distro holds no
    # .vhdx. With -Record the kept.json is written (the version from Windows' own version.json,
    # advisor item 3). A failed check moves the disk back.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [System.Collections.IDictionary]$Info = $null,
        [string]$Version = '',
        # A Windows value (state\windows-changes.json), so a reinstall can give the new account
        # its rights on the backup folder.
        [string]$BackupFolder = '',
        [switch]$Record
    )
    $paths = Get-KeptPaths -Layout $Layout
    if (-not (Test-DataRootPath $Layout.DataRoot)) { return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'path' } }
    foreach ($path in @($Layout.DataRoot, $Layout.Distro, $paths.Folder, $paths.Live, $paths.Disk)) {
        if (-not (Test-NoLink $path)) { return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'link' } }
    }
    if ($Record -and -not (Test-KeptInfo $Info)) { return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'engine' } }
    $live = Get-Item -LiteralPath $paths.Live -Force -ErrorAction SilentlyContinue
    if (-not $live) { return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'no_disk' } }
    if (Test-Path -LiteralPath $paths.Disk) { return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'kept_exists' } }
    $size = [long]$live.Length
    [void][System.IO.Directory]::CreateDirectory($paths.Folder)
    [System.IO.File]::Move($paths.Live, $paths.Disk)
    Write-RunLog 'uninstall.keep' 'INFO' ('disk moved to {0} ({1} bytes)' -f $paths.Disk, $size)
    if ($Record) {
        $kept = [ordered]@{
            schema_version = 1
            version        = $Version
            instance_id    = [string]$Info['instance_id']
            business_name  = [string]$Info['business_name']
            public_host    = [string]$Info['public_host']
            backup_folder  = $(if ($BackupFolder -cmatch '^[A-Z]:\\SlateOps-backups$') { $BackupFolder } else { '' })
            kept_at        = (Get-UtcStamp)
        }
        Write-JsonFile -Path $paths.Record -Value $kept
    }
    $moved = Get-Item -LiteralPath $paths.Disk -Force -ErrorAction SilentlyContinue
    $left = @(Get-ChildItem -LiteralPath $Layout.Distro -Force -Filter '*.vhdx' -ErrorAction SilentlyContinue)
    if ((-not $moved) -or ([long]$moved.Length -ne $size) -or ($left.Count -gt 0)) {
        Write-RunLog 'uninstall.keep' 'FAIL' 'the kept disk does not match; moved back'
        if ($moved -and -not (Test-Path -LiteralPath $paths.Live)) { [System.IO.File]::Move($paths.Disk, $paths.Live) }
        return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'check' }
    }
    return New-StepResult -Code 'kept' -MessageKey 'uninstall.kept' -Values @{ bytes = $size }
}

function Test-KeptAfterUnregister {
    # F3, after wsl --unregister: the kept disk is still there with its size.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][long]$Bytes)
    $item = Get-Item -LiteralPath (Get-KeptPaths -Layout $Layout).Disk -Force -ErrorAction SilentlyContinue
    return [bool]($item -and ([long]$item.Length -eq $Bytes))
}

function Clear-DataTreeForKeep {
    # After the disk is kept: distro (empty) and payload go; the account's entries go while its
    # SID is known (advisor item 2), so a reinstall finds no unknown SID in the data tree.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [string]$ServiceSid = '')
    if ($ServiceSid) { Remove-ServiceAccess -Tree $Layout.DataTree -Sid $ServiceSid }
    foreach ($path in @($Layout.Distro, $Layout.Payload)) {
        if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path }
    }
}

function Get-KeptData {
    # S07 kept-data card (spec 4.3): reads kept.json after the folder checks (advisor item 3).
    # Codes: none, kept, kept_newer (W9-3), kept_unreadable.
    param([Parameter(Mandatory = $true)][string]$DataRoot, [Parameter(Mandatory = $true)][string]$SetupVersion)
    if (-not (Test-DataRootPath $DataRoot)) { return New-StepResult -Code 'none' -MessageKey 'setup.kept.none' }
    $layout = New-SlateOpsLayout -DataRoot $DataRoot
    $paths = Get-KeptPaths -Layout $layout
    if (-not (Test-Path -LiteralPath $paths.Record -PathType Leaf)) { return New-StepResult -Code 'none' -MessageKey 'setup.kept.none' }
    foreach ($path in @($DataRoot, $paths.Folder, $paths.Record, $paths.Disk)) {
        if (-not (Test-NoLink $path)) { return New-StepResult -Code 'kept_unreadable' -MessageKey 'setup.kept.kept_unreadable' }
    }
    if (@(Get-FolderParentProblem -Path $DataRoot).Count -gt 0) { return New-StepResult -Code 'kept_unreadable' -MessageKey 'setup.kept.kept_unreadable' }
    try { $kept = Read-JsonFile -Path $paths.Record } catch { return New-StepResult -Code 'kept_unreadable' -MessageKey 'setup.kept.kept_unreadable' }
    $version = [string](Get-DictValue $kept 'version')
    if ((-not (Test-ReleaseVersion $version)) -or (-not (Test-KeptInfo $kept)) -or (-not (Test-Path -LiteralPath $paths.Disk -PathType Leaf))) {
        return New-StepResult -Code 'kept_unreadable' -MessageKey 'setup.kept.kept_unreadable'
    }
    $when = ''
    try { $when = ([datetime]::Parse([string](Get-DictValue $kept 'kept_at'), [System.Globalization.CultureInfo]::InvariantCulture)).ToString('d MMMM yyyy', [System.Globalization.CultureInfo]::InvariantCulture) } catch { $when = '' }
    $values = @{ version = $version; business_name = [string]$kept['business_name']; kept_on = $when }
    if ((Compare-ReleaseVersion -Left $version -Right $SetupVersion) -gt 0) { return New-StepResult -Code 'kept_newer' -MessageKey 'setup.kept.kept_newer' -Values $values }
    if ((Compare-ReleaseVersion -Left $version -Right $SetupVersion) -lt 0) { return New-StepResult -Code 'kept_older' -MessageKey 'setup.kept.kept_older' -Values $values }
    return New-StepResult -Code 'kept' -MessageKey 'setup.kept.kept' -Values $values
}

function Restore-KeptDisk {
    # Reinstall (plan 9.2 step 3): the kept disk moves back into distro, gets Administrators as
    # owner and only the entries it inherits from distro (the new account's), so the data tree
    # check passes and the account can open it.
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $paths = Get-KeptPaths -Layout $Layout
    foreach ($path in @($paths.Folder, $paths.Disk, $Layout.Distro, $paths.Live)) {
        if (-not (Test-NoLink $path)) { return New-StepResult -Code 'kept_unsafe' -MessageKey 'setup.kept.kept_unsafe' }
    }
    if (Test-Path -LiteralPath $paths.Live) { return New-StepResult -Code 'kept_unsafe' -MessageKey 'setup.kept.kept_unsafe' }
    if (-not (Test-Path -LiteralPath $paths.Disk -PathType Leaf)) { return New-StepResult -Code 'kept_missing' -MessageKey 'setup.kept.kept_missing' }
    [System.IO.File]::Move($paths.Disk, $paths.Live)
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetOwner((New-Object System.Security.Principal.SecurityIdentifier($SlateOps.SidAdministrators)))
    $acl.SetAccessRuleProtection($false, $false)
    Set-Acl -LiteralPath $paths.Live -AclObject $acl
    Write-RunLog 'setup.kept' 'INFO' ('kept disk moved back to {0}; owner Administrators, inherited entries only' -f $paths.Live)
    return New-StepResult -Code 'restored' -MessageKey 'setup.kept.restored'
}

function Test-KeptInstance {
    # F3 at reinstall: the engine status must report the instance ID of kept.json. A missing
    # value is a stop, never a match (advisor item 1).
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [AllowNull()][System.Collections.IDictionary]$Status)
    try { $kept = Read-JsonFile -Path (Get-KeptPaths -Layout $Layout).Record } catch { return $false }
    $want = [string](Get-DictValue $kept 'instance_id')
    $got = ''
    if ($Status) { $got = [string](Get-DictValue (Get-DictValue $Status 'values') 'instance_id') }
    Write-RunLog 'setup.kept' 'INFO' ('instance check: kept {0}, engine {1}' -f $want, $(if ($got) { $got } else { 'none' }))
    return ($want -ne '') -and ($got -ceq $want)
}

# ---------------------------------------------------------------------------
# Delete everything (plan 9.1)
# ---------------------------------------------------------------------------

function Remove-DataFolder {
    # The data folder from the record, only when its shape and every folder above it pass the
    # S91-2 parent rule; links inside are removed as links, never followed.
    param([Parameter(Mandatory = $true)][string]$DataRoot)
    if (-not (Test-DataRootPath $DataRoot)) { return New-StepResult -Code 'data_path_invalid' -MessageKey 'uninstall.data_path_invalid' }
    if (-not (Test-Path -LiteralPath $DataRoot)) { return New-StepResult -Code 'removed' -MessageKey 'uninstall.data_removed' }
    $problems = @(Get-FolderParentProblem -Path $DataRoot)
    if (-not (Test-NoLink $DataRoot)) { $problems += 'data_root_link' }
    if ($problems.Count -gt 0) {
        foreach ($problem in $problems) { Write-RunLog 'uninstall.data' 'FAIL' $problem }
        return New-StepResult -Code 'data_folder_parent_unsafe' -MessageKey 'uninstall.data_folder_parent_unsafe'
    }
    Remove-PathNoFollow -Path $DataRoot
    Write-RunLog 'uninstall.data' 'INFO' ('data folder {0} removed' -f $DataRoot)
    return New-StepResult -Code 'removed' -MessageKey 'uninstall.data_removed'
}

function Remove-BackupFolder {
    # "Also delete the backups on E:": only exactly <drive>:\SlateOps-backups from the record.
    param([AllowEmptyString()][string]$Folder)
    if ($Folder -cnotmatch '^[A-Z]:\\SlateOps-backups$') { return New-StepResult -Code 'backup_path_invalid' -MessageKey 'uninstall.backup_path_invalid' }
    if (-not (Test-Path -LiteralPath $Folder)) { return New-StepResult -Code 'removed' -MessageKey 'uninstall.backups_removed' }
    if (-not (Test-NoLink $Folder)) { return New-StepResult -Code 'backup_link' -MessageKey 'uninstall.backup_link' }
    Remove-PathNoFollow -Path $Folder
    Write-RunLog 'uninstall.backups' 'INFO' ('backups {0} removed' -f $Folder)
    return New-StepResult -Code 'removed' -MessageKey 'uninstall.backups_removed'
}

# ---------------------------------------------------------------------------
# The Windows parts (plan 9.1 list; W9-1, W9-6)
# ---------------------------------------------------------------------------

function Get-UninstallNames {
    # The fixed names; tests pass their own, so no test touches the product's real parts.
    return @{
        TaskPath = $SlateOps.TaskPath
        TaskFolder = $SlateOps.TaskFolder
        AccountName = $SlateOps.AccountName
        HostsPath = (Join-Path $SlateOpsPaths.System32 'drivers\etc\hosts')
        UserList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
        StoreLocation = 'LocalMachine'
        Power = $true
    }
}

function Get-UninstallLeftovers {
    # W9-6: each item of 9.1 that is still on this PC, by name.
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Record, [Parameter(Mandatory = $true)][hashtable]$Names, [Parameter(Mandatory = $true)][hashtable]$Layout)
    $left = New-Object System.Collections.Generic.List[string]
    if (@(Get-ScheduledTask -TaskPath $Names.TaskPath -ErrorAction SilentlyContinue).Count -gt 0) { $left.Add('tasks') }
    $sid = [string](Get-DictValue $Record 'account_sid')
    if ($sid -and (Get-LocalUser -SID $sid -ErrorAction SilentlyContinue)) { $left.Add('account') }
    foreach ($name in @(Get-DictValue $Record 'firewall_rules')) { if ($name -and (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue)) { $left.Add(('firewall_rule:{0}' -f $name)) } }
    foreach ($name in @(Get-DictValue $Record 'hyperv_rules')) { if ($name -and (Get-NetFirewallHyperVRule -Name $name -ErrorAction SilentlyContinue)) { $left.Add(('hyperv_rule:{0}' -f $name)) } }
    if ((Test-Path -LiteralPath $Names.HostsPath) -and (@([System.IO.File]::ReadAllLines($Names.HostsPath) | Where-Object { $_.EndsWith($SlateOps.HostsMarker) }).Count -gt 0)) { $left.Add('hosts') }
    $thumbprint = [string](Get-DictValue $Record 'ca_thumbprint')
    if ($thumbprint -and (Test-Path -LiteralPath ('Cert:\{0}\Root\{1}' -f $Names.StoreLocation, $thumbprint))) { $left.Add('ca') }
    foreach ($folder in @('state', 'requests', 'svc-out', 'scripts', 'settings')) {
        if (Test-Path -LiteralPath (Join-Path $Layout.StateRoot $folder)) { $left.Add(('state_folder:{0}' -f $folder)) }
    }
    # Plain array output: the callers wrap it in @(), so no leftover is an empty list (a
    # comma-wrapped array became one item, and an empty one broke the log line).
    return $left.ToArray()
}

function Invoke-UninstallPart {
    # One removal; an error is logged and the next part still runs, so it shows as a leftover
    # (W9-6) instead of stopping the uninstall half way.
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][scriptblock]$Body)
    try { & $Body } catch { Write-RunLog 'uninstall.windows' 'WARN' ('{0}: {1}' -f $Name, $_.Exception.Message) }
}

function Remove-WindowsParts {
    # Both answers: removes what the record names, restores the power values, then checks each
    # item and logs every leftover (W9-1, W9-6). WSL and VirtualMachinePlatform stay.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [hashtable]$Names = (Get-UninstallNames)
    )
    $step = 'uninstall.windows'
    $record = Read-WindowsChanges -Layout $Layout
    Invoke-UninstallPart 'tasks' {
        foreach ($task in @(Get-ScheduledTask -TaskPath $Names.TaskPath -ErrorAction SilentlyContinue)) {
            Stop-ScheduledTask -TaskPath $Names.TaskPath -TaskName $task.TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskPath $Names.TaskPath -TaskName $task.TaskName -Confirm:$false
            Write-RunLog $step 'INFO' ('task {0}{1} removed' -f $Names.TaskPath, $task.TaskName)
        }
        try { $scheduler = New-Object -ComObject 'Schedule.Service'; $scheduler.Connect(); $scheduler.GetFolder('\').DeleteFolder($Names.TaskFolder, 0) } catch { $null = $_ }
    }
    # The account: sign-in list entry, profile, account, rights; the UserList keys as they were.
    $sid = [string](Get-DictValue $record 'account_sid')
    Invoke-UninstallPart 'account' {
        if ($sid) {
            $account = Get-LocalUser -SID $sid -ErrorAction SilentlyContinue
            if ($account) {
                Remove-ItemProperty -LiteralPath $Names.UserList -Name $account.Name -ErrorAction SilentlyContinue
                $userProfile = Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid) -ErrorAction SilentlyContinue
                if ($userProfile -and -not $userProfile.Loaded) { Remove-CimInstance -InputObject $userProfile }
                Remove-LocalUser -SID $sid
                Write-RunLog $step 'INFO' ('account {0} removed' -f $sid)
            }
            Initialize-LsaRightsType
            [SlateOpsSetup.LsaRights]::Remove($sid, [string[]]$SlateOps.AccountRights)
        }
        if ((Get-DictValue $record 'userlist_key_existed') -eq $false) { Remove-Item -LiteralPath $Names.UserList -Force -ErrorAction SilentlyContinue }
        if ((Get-DictValue $record 'specialaccounts_key_existed') -eq $false) { Remove-Item -LiteralPath (Split-Path -Parent $Names.UserList) -Force -ErrorAction SilentlyContinue }
    }
    Invoke-UninstallPart 'firewall' {
        foreach ($name in @(Get-DictValue $record 'firewall_rules')) { if ($name) { Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule } }
        foreach ($name in @(Get-DictValue $record 'hyperv_rules')) { if ($name) { Get-NetFirewallHyperVRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule } }
    }
    # The hosts line, in the encoding the file has (P3-5).
    Invoke-UninstallPart 'hosts' {
        if (Test-Path -LiteralPath $Names.HostsPath) {
            $reader = New-Object System.IO.StreamReader($Names.HostsPath, [System.Text.Encoding]::Default, $true)
            try { $existing = $reader.ReadToEnd(); $encoding = $reader.CurrentEncoding } finally { $reader.Dispose() }
            $lines = @($existing -split "`r?`n" | Where-Object { -not $_.EndsWith($SlateOps.HostsMarker) })
            $content = (($lines -join "`r`n").TrimEnd("`r", "`n")) + "`r`n"
            if ($content -ne $existing) { [System.IO.File]::WriteAllText($Names.HostsPath, $content, $encoding) }
        }
    }
    # Our CA, by the recorded thumbprint only.
    $thumbprint = [string](Get-DictValue $record 'ca_thumbprint')
    Invoke-UninstallPart 'ca' {
        if ($thumbprint -cmatch '^[0-9A-F]{40}$') {
            $store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', $Names.StoreLocation)
            $store.Open('ReadWrite')
            try { foreach ($certificate in @($store.Certificates.Find([System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint, $thumbprint, $false))) { $store.Remove($certificate) } } finally { $store.Close() }
        }
    }
    # The power values on mains power, as they were (plan 9.1).
    $scheme = [string](Get-DictValue $record 'power_scheme')
    Invoke-UninstallPart 'power' {
        if ($Names.Power -and ($scheme -match '^[0-9a-fA-F-]{36}$')) {
            foreach ($setting in @(@{ group = 'SUB_SLEEP'; name = 'STANDBYIDLE'; key = 'power_standby_ac' }, @{ group = 'SUB_SLEEP'; name = 'HIBERNATEIDLE'; key = 'power_hibernate_ac' }, @{ group = 'SUB_BUTTONS'; name = 'LIDACTION'; key = 'power_lid_ac' })) {
                $old = Get-DictValue $record $setting.key
                if ($null -eq $old) { continue }
                $null = Invoke-Logged -Step $step -FilePath 'powercfg.exe' -ArgumentList @('/setacvalueindex', $scheme, $setting.group, $setting.name, ([string][long]$old)) -NoThrow
            }
            $null = Invoke-Logged -Step $step -FilePath 'powercfg.exe' -ArgumentList @('/setactive', $scheme) -NoThrow
        }
    }
    # The resume entries, then the state folder apart from its logs. The scripts go last and only
    # with no leftover, so U04 can still save a report (and the next setup run removes the rest,
    # plan 10.7).
    Invoke-UninstallPart 'resume' { $null = Clear-SetupResume -Layout $Layout }
    foreach ($folder in @('state', 'requests', 'svc-out', 'settings')) {
        $path = Join-Path $Layout.StateRoot $folder
        Invoke-UninstallPart ('state_folder:{0}' -f $folder) { if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path } }
    }
    $left = @(Get-UninstallLeftovers -Record $record -Names $Names -Layout $Layout | Where-Object { $_ -ne 'state_folder:scripts' })
    if ($left.Count -eq 0) {
        $scripts = Join-Path $Layout.StateRoot 'scripts'
        Invoke-UninstallPart 'state_folder:scripts' { if (Test-Path -LiteralPath $scripts) { Remove-PathNoFollow -Path $scripts } }
        $left = @(Get-UninstallLeftovers -Record $record -Names $Names -Layout $Layout)
    }
    foreach ($item in $left) { Write-RunLog $step 'FAIL' ('leftover: {0}' -f $item) }
    if ($left.Count -gt 0) { return New-StepResult -Code 'leftovers' -MessageKey 'uninstall.leftovers' -Values @{ items = $left } }
    Write-RunLog $step 'INFO' 'every item removed; WSL and VirtualMachinePlatform stay'
    return New-StepResult -Code 'removed' -MessageKey 'uninstall.removed'
}

# ---------------------------------------------------------------------------
# Repair (plan 9.3, 10.7 "The service account cannot sign in"; spec M01)
# ---------------------------------------------------------------------------

function Invoke-Repair {
    # Sets the Windows parts up again: a new password for the account and its rights, both
    # tasks, the firewall rules for the current network, the hosts entry, the boot start. The
    # data does not change. R7 is read again right before the new password exists (11.1 W9).
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $step = 'maintenance.repair'
    try { $covered = @(Get-PasswordModuleLogged) } catch { return New-StepResult -Code 'logging_policy_unreadable' -MessageKey 'check.c18.unreadable' }
    if ($covered.Count -gt 0) { return New-StepResult -Code 'logging_policy' -MessageKey 'check.c18.policy' }
    $sid = Get-RecordedServiceSid -Layout $Layout
    $account = $null
    if ($sid) { $account = Get-LocalUser -SID $sid -ErrorAction SilentlyContinue }
    if (-not $account) { return New-StepResult -Code 'account_missing' -MessageKey 'setup.account.missing' }
    $password = New-RandomPassword
    Register-LogSecret $password
    try {
        Set-LocalUser -SID $sid -Password (ConvertTo-SecureText -Text $password)
        Initialize-LsaRightsType
        [SlateOpsSetup.LsaRights]::Add($sid, [string[]]$SlateOps.AccountRights)
        Write-RunLog $step 'INFO' 'account password set again (not stored, not shown); rights set again'
        Register-ServiceTasks -Layout $Layout -AccountName $account.Name -Password $password
    } finally { $password = $null }
    $steps = @()
    $lan = Get-LanFact
    if ($lan) { $steps += Set-FirewallRules -Layout $Layout -Cidr (ConvertTo-NetworkCidr -Address $lan.address -PrefixLength $lan.prefix_length) }
    $hostName = ([string](Get-CimInstance -ClassName Win32_ComputerSystem).DNSHostName).ToLowerInvariant()
    $steps += Set-HostsEntry -Layout $Layout -HostName ('{0}.local' -f $hostName)
    Enable-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName | Out-Null
    Start-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName
    $failed = @($steps | Where-Object { $_.code -ne 'added' })
    if ($failed.Count -gt 0) { return $failed[0] }
    return New-StepResult -Code 'repaired' -MessageKey 'maintenance.repaired'
}

function Get-SecurityCodeFromStore {
    # "Show the phone code": the security code of our CA in LocalMachine Root, by the recorded
    # thumbprint, computed on Windows (spec M01, plan 6.3).
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $thumbprint = [string](Get-DictValue (Read-WindowsChanges -Layout $Layout) 'ca_thumbprint')
    if ($thumbprint -cnotmatch '^[0-9A-F]{40}$') { return New-StepResult -Code 'missing' -MessageKey 'maintenance.code.missing' }
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
    $store.Open('ReadOnly')
    try { $found = @($store.Certificates.Find([System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint, $thumbprint, $false)) } finally { $store.Close() }
    if ($found.Count -ne 1) { return New-StepResult -Code 'missing' -MessageKey 'maintenance.code.missing' }
    return New-StepResult -Code 'found' -MessageKey 'maintenance.code.found' -Values @{ security_code = (Get-CaSecurityCode -Certificate $found[0]) }
}
