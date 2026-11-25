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
    # A local account SID, as Get-RecordedServiceSid reads it.
    SidPattern  = '^S-1-5-21-[0-9]{1,10}-[0-9]{1,10}-[0-9]{1,10}-[0-9]{1,10}$'
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
    finally { Remove-EngineOutput -Layout $Layout -Result $result }
    $values = @{}
    foreach ($key in @('state', 'backup')) {
        $value = [string](Get-DictValue $output $key)
        if ($value -cmatch '^[a-z_]{1,32}$') { $values[$key] = $value }
    }
    $instance = [string](Get-DictValue $output 'instance_id')
    if ($instance -cmatch $SlateOpsKept.InstancePattern) { $values.instance_id = $instance }
    # W13b-5 (plan 7.4): the only engine value that Windows acts on; true only as a JSON true.
    $idle = Get-DictValue $output 'engine_idle'
    $values.engine_idle = (($idle -is [bool]) -and $idle)
    # AC-W6 (DEC-0041): only whether email is set up; the administrator's address in the engine's
    # answer (admin_email) is personal data and is never passed on, logged or saved.
    $email = Get-DictValue $output 'email_configured'
    if ($email -is [bool]) { $values.email_configured = $email }
    # Owner request 2026-11-25: the owner stopped Slate Operations (engine power.py).
    $stopped = Get-DictValue $output 'stopped'
    $values.stopped = (($stopped -is [bool]) -and $stopped)
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
        # W9 gap 1: the account that this uninstall removes, so a reinstall can drop its entries.
        [string]$AccountSid = '',
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
            account_sid    = $(if ($AccountSid -cmatch $SlateOpsKept.SidPattern) { $AccountSid } else { '' })
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
    # -Restored (a resumed kept reinstall, design N-1): the disk is already back in distro.
    param([Parameter(Mandatory = $true)][string]$DataRoot, [Parameter(Mandatory = $true)][string]$SetupVersion, [switch]$Restored)
    if (-not (Test-DataRootPath $DataRoot)) { return New-StepResult -Code 'none' -MessageKey 'setup.kept.none' }
    $layout = New-SlateOpsLayout -DataRoot $DataRoot
    $paths = Get-KeptPaths -Layout $layout
    if (-not (Test-Path -LiteralPath $paths.Record -PathType Leaf)) { return New-StepResult -Code 'none' -MessageKey 'setup.kept.none' }
    $disk = $(if ($Restored) { $paths.Live } else { $paths.Disk })
    foreach ($path in @($DataRoot, $paths.Folder, $paths.Record, $disk)) {
        if (-not (Test-NoLink $path)) { return New-StepResult -Code 'kept_unreadable' -MessageKey 'setup.kept.kept_unreadable' }
    }
    if (@(Get-FolderParentProblem -Path $DataRoot).Count -gt 0) { return New-StepResult -Code 'kept_unreadable' -MessageKey 'setup.kept.kept_unreadable' }
    try { $kept = Read-JsonFile -Path $paths.Record } catch { return New-StepResult -Code 'kept_unreadable' -MessageKey 'setup.kept.kept_unreadable' }
    $version = [string](Get-DictValue $kept 'version')
    if ((-not (Test-ReleaseVersion $version)) -or (-not (Test-KeptInfo $kept)) -or (-not (Test-Path -LiteralPath $disk -PathType Leaf))) {
        return New-StepResult -Code 'kept_unreadable' -MessageKey 'setup.kept.kept_unreadable'
    }
    $when = ''
    try { $when = ([datetime]::Parse([string](Get-DictValue $kept 'kept_at'), [System.Globalization.CultureInfo]::InvariantCulture)).ToString('d MMMM yyyy', [System.Globalization.CultureInfo]::InvariantCulture) } catch { $when = '' }
    # DEC-0039: the kept installation keeps its address (its certificate names it).
    $keptLabel = ''
    if (([string]$kept['public_host']) -match '^(?<label>[a-z0-9-]+)\.local$' -and (Test-AddressLabel $Matches['label'])) { $keptLabel = $Matches['label'] }
    $values = @{ version = $version; business_name = [string]$kept['business_name']; kept_on = $when; host_label = $keptLabel }
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

function Remove-OldAccountAccess {
    # W9 gap 1 (kept reinstall): the backup folder of the kept installation drops every explicit
    # entry of the account that the uninstall removed (P2-3), and its items get Administrators as
    # owner, so the folder passes the W9-S1 rule again. The new account's entry comes from
    # Initialize-BackupFolder. Links are removed from the walk, never followed. Every item is
    # checked: a folder that .NET created with a protected list gives its children copies of its
    # entries that Windows does not mark as inherited, so each item can hold its own entry of the
    # old account. Returns one line per changed item: "<path below the folder>:<what changed>"
    # ("." is the folder itself; "owner", "entry").
    param([Parameter(Mandatory = $true)][string]$Folder, [AllowEmptyString()][string]$OldSid, [string]$ServiceSid = '')
    $changes = New-Object System.Collections.Generic.List[string]
    if ($OldSid -cnotmatch $SlateOpsKept.SidPattern) { return $changes.ToArray() }
    $item = Get-Item -LiteralPath $Folder -Force -ErrorAction SilentlyContinue
    if ((-not $item) -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { return $changes.ToArray() }
    # W9-S2: the walk reads and writes access lists by path, so it runs only on a folder that no
    # standard user can change (the tree rule, with the old account accepted).
    $problems = @(Get-BackupFolderProblem -Folder $Folder -ServiceSid $ServiceSid -OldSid $OldSid)
    if ($problems.Count -gt 0) {
        foreach ($problem in $problems) { Write-RunLog 'setup.kept' 'WARN' $problem }
        Write-RunLog 'setup.kept' 'WARN' ('backup folder {0} fails the tree rule; old-account walk skipped' -f $Folder)
        return $changes.ToArray()
    }
    $base = $item.FullName.TrimEnd('\')
    $sidType = [System.Security.Principal.SecurityIdentifier]
    $old = New-Object System.Security.Principal.SecurityIdentifier($OldSid)
    $admins = New-Object System.Security.Principal.SecurityIdentifier($SlateOps.SidAdministrators)
    $stack = New-Object System.Collections.Generic.Stack[object]
    $stack.Push($item)
    while ($stack.Count -gt 0) {
        $item = $stack.Pop()
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { continue }
        $acl = Get-Acl -LiteralPath $item.FullName
        $what = @()
        if ($acl.GetOwner($sidType).Value -eq $OldSid) { $acl.SetOwner($admins); $what += 'owner' }
        if (@($acl.GetAccessRules($true, $false, $sidType) | Where-Object { $_.IdentityReference.Value -eq $OldSid }).Count -gt 0) { $acl.PurgeAccessRules($old); $what += 'entry' }
        if ($what.Count -gt 0) {
            Set-Acl -LiteralPath $item.FullName -AclObject $acl
            $relative = $item.FullName.Substring($base.Length).TrimStart('\')
            if (-not $relative) { $relative = '.' }
            $changes.Add(('{0}:{1}' -f $relative, ($what -join ' ')))
        }
        if ($item.PSIsContainer) { foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force)) { $stack.Push($child) } }
    }
    Write-RunLog 'setup.kept' 'INFO' ('backup folder {0}: moved from the earlier account {1}: {2}' -f $Folder, $OldSid, ($changes -join ', '))
    return $changes.ToArray()
}

function Test-AclFreeFileSystem {
    # W9-S3: only FAT, FAT32 and exFAT have no access lists. Every other format, an unknown one
    # and an unreadable one (empty) get the tree rule and a protected list.
    param([AllowEmptyString()][string]$Format)
    return (@('FAT', 'FAT32', 'exFAT') -contains $Format)
}

function Get-VolumeFormat {
    # The file system of the volume that holds a path; '' when it cannot be read.
    param([Parameter(Mandatory = $true)][string]$Path)
    try { return [string](New-Object System.IO.DriveInfo((Split-Path -Qualifier $Path))).DriveFormat } catch { return '' }
}

function Get-BackupFolderProblem {
    # The backup folder tree rule (Security W9-S1, W9-S2, F-2, W9-S3, W9-S4; S91-2 class), before any
    # elevated delete or access-list write: the folder owned by Administrators, SYSTEM or this
    # administrator, a protected list, and below it no link, no other owner than those, the
    # service account and the account that a kept reinstall replaces (-OldSid), and no writer
    # other than Administrators, SYSTEM and those two accounts. Only FAT, FAT32 and exFAT (no
    # access lists) skip it; they keep the shape and link checks.
    param([Parameter(Mandatory = $true)][string]$Folder, [string]$ServiceSid = '', [string]$OldSid = '')
    $problems = New-Object System.Collections.Generic.List[string]
    if (Test-AclFreeFileSystem -Format (Get-VolumeFormat -Path $Folder)) { return $problems.ToArray() }
    # Security W9-S4: the folders above must keep the folder in place (the S91-2 parent rule), or
    # a standard user could swap it for a junction after this check passes.
    foreach ($problem in @(Get-FolderParentProblem -Path $Folder)) { $problems.Add($problem) }
    $sidType = [System.Security.Principal.SecurityIdentifier]
    $trusted = @($SlateOps.SidAdministrators, $SlateOps.SidSystem, [Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
    $writers = @($SlateOps.SidAdministrators, $SlateOps.SidSystem)
    if ($ServiceSid) { $writers += $ServiceSid }
    if ($OldSid) { $writers += $OldSid }
    $root = Get-Acl -LiteralPath $Folder
    if ($trusted -notcontains $root.GetOwner($sidType).Value) { $problems.Add(('owner:{0}' -f $Folder)) }
    if (-not $root.AreAccessRulesProtected) { $problems.Add(('inherits:{0}' -f $Folder)) }
    $stack = New-Object System.Collections.Generic.Stack[object]
    $stack.Push((Get-Item -LiteralPath $Folder -Force))
    while ($stack.Count -gt 0) {
        $item = $stack.Pop()
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { $problems.Add(('reparse_point:{0}' -f $item.FullName)); continue }
        try { $acl = Get-Acl -LiteralPath $item.FullName } catch { $problems.Add(('acl_unreadable:{0}' -f $item.FullName)); continue }
        $owner = $acl.GetOwner($sidType).Value
        if (($trusted -notcontains $owner) -and ($writers -notcontains $owner)) { $problems.Add(('owner:{0}:{1}' -f $item.FullName, $owner)) }
        foreach ($rule in $acl.GetAccessRules($true, $true, $sidType)) {
            if ($rule.AccessControlType -ne 'Allow') { continue }
            if ($writers -contains $rule.IdentityReference.Value) { continue }
            if (-not (Test-RuleReadOnly $rule)) { $problems.Add(('writer:{0}:{1}' -f $item.FullName, $rule.IdentityReference.Value)) }
        }
        if ($item.PSIsContainer) { foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force)) { $stack.Push($child) } }
    }
    return $problems.ToArray()
}

function Remove-BackupFolder {
    # "Also delete the backups on E:": only exactly <drive>:\SlateOps-backups from the record, and
    # on NTFS only after the tree rule (W9-S1); a folder that fails it stays and is a leftover.
    param([AllowEmptyString()][string]$Folder, [string]$ServiceSid = '')
    if ($Folder -cnotmatch '^[A-Z]:\\SlateOps-backups$') { return New-StepResult -Code 'backup_path_invalid' -MessageKey 'uninstall.backup_path_invalid' }
    if (-not (Test-Path -LiteralPath $Folder)) { return New-StepResult -Code 'removed' -MessageKey 'uninstall.backups_removed' }
    if (-not (Test-NoLink $Folder)) { return New-StepResult -Code 'backup_link' -MessageKey 'uninstall.backup_link' }
    $problems = @(Get-BackupFolderProblem -Folder $Folder -ServiceSid $ServiceSid)
    if ($problems.Count -gt 0) {
        foreach ($problem in $problems) { Write-RunLog 'uninstall.backups' 'FAIL' $problem }
        return New-StepResult -Code 'backup_folder_unsafe' -MessageKey 'uninstall.backup_folder_unsafe'
    }
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
        # R-10: the startup task that finishes a profile removal (outside \SlateOps\).
        FinishTaskPath = '\'
        FinishTaskPrefix = 'SlateOpsFinishRemoval-'
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
    # R-10: a profile that a startup task removes at the next restart is not a leftover.
    if ($sid -and (Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid) -ErrorAction SilentlyContinue) -and
        -not (Get-ScheduledTask -TaskPath $Names.FinishTaskPath -TaskName ('{0}{1}' -f $Names.FinishTaskPrefix, $sid) -ErrorAction SilentlyContinue)) { $left.Add('profile') }
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

function Get-AccountProcesses {
    # R-9, R-10: the processes that run as the account (id and name only), by the token owner.
    # A process whose owner cannot be read is skipped and counted in unreadable.
    param([Parameter(Mandatory = $true)][string]$Sid)
    $found = New-Object System.Collections.Generic.List[object]
    $unreadable = 0
    foreach ($process in @(Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue)) {
        try {
            $owner = Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid -ErrorAction Stop
            if (($owner.ReturnValue -eq 0) -and ($owner.Sid -eq $Sid)) { $found.Add(@{ id = [int]$process.ProcessId; name = [string]$process.Name }) }
        } catch { $unreadable++ }
    }
    return @{ processes = $found.ToArray(); unreadable = $unreadable }
}

function Stop-AccountProcesses {
    # R-9 (exec-path CI): ends every process that runs as the service account, so its profile
    # can unload. Its scheduled tasks are already stopped and removed. Only an S-1-5-21- SID (a
    # local or domain account; Remove-ServiceProfile calls it only for the profile folder of the
    # service account), never the account of this process. Every end and every failure is
    # logged. Returns the number of ended processes.
    param([Parameter(Mandatory = $true)][string]$Sid)
    if ($Sid -notmatch '^S-1-5-21(-[0-9]+)+$') { return 0 }
    if ($Sid -eq [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { return 0 }
    $count = 0
    foreach ($process in @((Get-AccountProcesses -Sid $Sid).processes)) {
        try {
            Stop-Process -Id $process.id -Force -ErrorAction Stop
            Write-RunLog 'uninstall.windows' 'INFO' ('ended {0} ({1}) of the service account' -f $process.name, $process.id)
            $count++
        } catch { Write-RunLog 'uninstall.windows' 'WARN' ('{0} ({1}) of the service account did not end: {2}' -f $process.name, $process.id, $_.Exception.Message) }
    }
    return $count
}

function Get-ServiceProfileFacts {
    # R-10 (exec-path CI): one log line about what keeps the profile of the service account
    # loaded: its hive under HKEY_USERS (read from the key list, which opens no hive), the
    # profile list values, and its processes (names and ids only). For the log and Save report.
    param([Parameter(Mandatory = $true)][string]$Sid)
    $parts = New-Object System.Collections.Generic.List[string]
    try { $parts.Add(('hive loaded {0}' -f (@([Microsoft.Win32.Registry]::Users.GetSubKeyNames()) -contains $Sid))) } catch { $parts.Add('hive unreadable') }
    try {
        $list = Get-Item -LiteralPath ('HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\{0}' -f $Sid) -ErrorAction Stop
        $parts.Add(('profile list RefCount {0}, State {1}' -f $list.GetValue('RefCount', '-'), $list.GetValue('State', '-')))
    } catch { $parts.Add('profile list entry absent') }
    try {
        $found = Get-AccountProcesses -Sid $Sid
        $names = @($found.processes | ForEach-Object { '{0} ({1})' -f $_.name, $_.id })
        $parts.Add(('processes of the account {0} [{1}], owner unreadable for {2}' -f $names.Count, ($names -join ', '), $found.unreadable))
    } catch { $parts.Add('processes unreadable') }
    return ($parts.ToArray() -join '; ')
}

function Remove-ServiceProfile {
    # R-9, R-10 (exec-path CI): the profile of the service account, its record and its C:\Users
    # folder. Its tasks are already removed and its account still exists. The account's
    # processes end, then the profile is checked again until its hive unloads or the limit
    # (inside the 90 s of the windows step), and deleted. True when no profile is left. At the
    # limit it is logged with what still holds it, and false: the caller then leaves the rest
    # to a task at the next startup (R-10).
    param(
        [Parameter(Mandatory = $true)][string]$Sid,
        [int]$LimitSeconds = 45,
        [int]$WaitMilliseconds = 1000,
        [string]$AccountName = $SlateOps.AccountName,
        [scriptblock]$StopProcesses = { param([string]$Sid) Stop-AccountProcesses -Sid $Sid },
        [scriptblock]$FindProfile = { param([string]$Sid) Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $Sid) -ErrorAction SilentlyContinue },
        [scriptblock]$DeleteProfile = { param($UserProfile) Remove-CimInstance -InputObject $UserProfile -ErrorAction Stop },
        [scriptblock]$Facts = { param([string]$Sid) Get-ServiceProfileFacts -Sid $Sid }
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($LimitSeconds)
    $problem = 'it is still loaded'
    $userProfile = & $FindProfile $Sid
    if (-not $userProfile) { return $true }
    # Only the profile folder of the service account (slateops-svc, or slateops-svc.<suffix>
    # when Windows had to pick another name): any other profile is never ended or deleted.
    $leaf = ([string]$userProfile.LocalPath) -replace '^.*[\\/]', ''
    if ($leaf -notmatch ('^{0}(\..+)?$' -f [regex]::Escape($AccountName))) {
        Write-RunLog 'uninstall.windows' 'WARN' ('the profile of {0} is not the service account profile; setup leaves it' -f $Sid)
        return $true
    }
    $attempt = 0
    while ($true) {
        $attempt++
        $null = & $StopProcesses $Sid
        $userProfile = & $FindProfile $Sid
        if (-not $userProfile) { return $true }
        if ($attempt -eq 1) { Write-RunLog 'uninstall.windows' 'INFO' ('profile of {0}: loaded {1}; {2}' -f $Sid, [bool]$userProfile.Loaded, (& $Facts $Sid)) }
        if (-not $userProfile.Loaded) {
            try {
                & $DeleteProfile $userProfile
                if (-not (& $FindProfile $Sid)) {
                    Write-RunLog 'uninstall.windows' 'INFO' ('profile of {0} removed after {1} checks' -f $Sid, $attempt)
                    return $true
                }
                $problem = 'its record is still there after the delete'
            } catch { $problem = $_.Exception.Message }
        }
        if ([DateTime]::UtcNow -ge $deadline) {
            Write-RunLog 'uninstall.windows' 'WARN' ('profile of {0} not removed in {1} s ({2}); {3}' -f $Sid, $LimitSeconds, $problem, (& $Facts $Sid))
            return $false
        }
        Start-Sleep -Milliseconds $WaitMilliseconds
    }
}

function Get-ProfileFinishScript {
    # R-10: the script of the startup task, inline (the scripts folder is gone by then). As
    # SYSTEM at startup, before the account could sign in: the profile is deleted when it is not
    # loaded, and the task deletes itself only when no profile record is left; else it stays
    # and tries again at the next startup. The SID passes the strict pattern before it goes in.
    param([Parameter(Mandatory = $true)][string]$Sid, [Parameter(Mandatory = $true)][string]$TaskPath, [Parameter(Mandatory = $true)][string]$TaskName)
    if ($Sid -cnotmatch $SlateOpsKept.SidPattern) { throw ('not an account SID: {0}' -f $Sid) }
    if (($TaskPath + $TaskName) -cnotmatch '^[\\A-Za-z0-9_.-]+$') { throw 'not a task name' }
    $lines = @(
        '$ErrorActionPreference = ''Stop'''
        ('$filter = "SID=''{0}''"' -f $Sid)
        '$userProfile = Get-CimInstance -ClassName Win32_UserProfile -Filter $filter'
        'if ($userProfile -and $userProfile.Loaded) { return }'
        'if ($userProfile) { Remove-CimInstance -InputObject $userProfile }'
        'if (Get-CimInstance -ClassName Win32_UserProfile -Filter $filter) { return }'
        ('Unregister-ScheduledTask -TaskPath ''{0}'' -TaskName ''{1}'' -Confirm:$false' -f $TaskPath, $TaskName)
    )
    return ($lines -join "`r`n")
}

function Register-ProfileFinishTask {
    # R-10 (exec-path CI): when the profile of the removed account stays loaded past the wait,
    # one task (SYSTEM, at startup) deletes it at the next restart, then deletes itself. The
    # task name holds the SID and is the only record; it is outside \SlateOps\ (C29 reads that
    # folder as an installation). True only when the task reads back as registered.
    param([Parameter(Mandatory = $true)][string]$Sid, [hashtable]$Names = (Get-UninstallNames))
    $name = '{0}{1}' -f $Names.FinishTaskPrefix, $Sid
    try {
        $finishScript = Get-ProfileFinishScript -Sid $Sid -TaskPath $Names.FinishTaskPath -TaskName $name
        $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($finishScript))
        $powershell = Join-Path $SlateOpsPaths.System32 'WindowsPowerShell\v1.0\powershell.exe'
        $action = New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {0}' -f $encoded)
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
        $description = 'Slate Operations setup: removes the profile of the removed account {0} at startup, then this task.' -f $Sid
        Register-ScheduledTask -TaskPath $Names.FinishTaskPath -TaskName $name -Action $action -Principal $principal -Settings $settings -Trigger (New-ScheduledTaskTrigger -AtStartup) -Description $description -Force | Out-Null
    } catch {
        Write-RunLog 'uninstall.windows' 'WARN' ('the startup task {0} could not be registered: {1}' -f $name, $_.Exception.Message)
        return $false
    }
    $registered = [bool](Get-ScheduledTask -TaskPath $Names.FinishTaskPath -TaskName $name -ErrorAction SilentlyContinue)
    if ($registered) { Write-RunLog 'uninstall.windows' 'INFO' ('the profile of {0} goes at the next restart: task {1}{2} (SYSTEM, at startup)' -f $Sid, $Names.FinishTaskPath, $name) }
    return $registered
}

function Remove-WindowsParts {
    # Both answers: removes what the record names, restores the power values, then checks each
    # item and logs every leftover (W9-1, W9-6). WSL and VirtualMachinePlatform stay.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [hashtable]$Names = (Get-UninstallNames),
        [switch]$DataLeft,
        [scriptblock]$RemoveProfile = { param([string]$Sid, [int]$LimitSeconds = 45) Remove-ServiceProfile -Sid $Sid -LimitSeconds $LimitSeconds },
        [scriptblock]$RegisterFinish = { param([string]$Sid) Register-ProfileFinishTask -Sid $Sid -Names $Names }
    )
    $step = 'uninstall.windows'
    $record = Read-WindowsChanges -Layout $Layout
    $outcome = @{ profile_left = $false; at_restart = $false }
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
    # R-10: a startup task of an earlier removal goes once its profile is gone (a short try
    # here); while that profile is still there, the task stays and finishes at the restart.
    Invoke-UninstallPart 'finish_tasks' {
        foreach ($task in @(Get-ScheduledTask -TaskPath $Names.FinishTaskPath -ErrorAction SilentlyContinue | Where-Object { $_.TaskName.StartsWith($Names.FinishTaskPrefix) })) {
            $old = $task.TaskName.Substring($Names.FinishTaskPrefix.Length)
            if (($old -cmatch $SlateOpsKept.SidPattern) -and ($old -ne $sid) -and (& $RemoveProfile $old 5)) {
                Unregister-ScheduledTask -TaskPath $Names.FinishTaskPath -TaskName $task.TaskName -Confirm:$false
                Write-RunLog $step 'INFO' ('task {0}{1} removed: the profile of {2} is gone' -f $Names.FinishTaskPath, $task.TaskName, $old)
            }
        }
    }
    Invoke-UninstallPart 'account' {
        if ($sid) {
            # R-9, R-10: the order is the tasks (above), the account's processes, the wait for its
            # hive to unload, the profile, then the account. A profile still loaded at the limit
            # goes at the next restart (a startup task); only when that task cannot be
            # registered does the record keep the SID for the next start.
            $outcome.profile_left = -not (& $RemoveProfile $sid)
            if ($outcome.profile_left -and (& $RegisterFinish $sid)) {
                $outcome.profile_left = $false
                $outcome.at_restart = $true
            }
            $account = Get-LocalUser -SID $sid -ErrorAction SilentlyContinue
            if ($account) {
                Remove-ItemProperty -LiteralPath $Names.UserList -Name $account.Name -ErrorAction SilentlyContinue
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
    # R-9: with the profile left and no startup task (R-10), the record keeps only the account
    # SID; the next start sees it, runs the removal again and removes the profile, and nothing
    # else.
    $keepRecord = Join-Path $Layout.State 'windows-changes.json'
    if ($outcome.profile_left) { Invoke-UninstallPart 'record' { Write-JsonFile -Path $keepRecord -Value ([ordered]@{ account_sid = $sid }) } }
    foreach ($folder in @('state', 'requests', 'svc-out', 'settings')) {
        $path = Join-Path $Layout.StateRoot $folder
        Invoke-UninstallPart ('state_folder:{0}' -f $folder) {
            if (-not (Test-Path -LiteralPath $path)) { return }
            if ($outcome.profile_left -and ($folder -eq 'state')) {
                foreach ($item in @(Get-ChildItem -LiteralPath $path -Force)) { if ($item.Name -ne 'windows-changes.json') { Remove-PathNoFollow -Path $item.FullName } }
            } else { Remove-PathNoFollow -Path $path }
        }
    }
    # AC-O2 (owner, rc.28): what stays of the state folder (logs, and scripts when data is left)
    # keeps no entry or ownership of the service account, so the next start accepts it.
    if ($sid) {
        Invoke-UninstallPart 'state_entries' {
            $changed = Clear-TreeAccount -Tree $Layout.StateTree -Sid $sid
            Write-RunLog $step 'INFO' ('state folder: the entries of {0} removed ({1} items)' -f $sid, $changed)
        }
    }
    $left = @(Get-UninstallLeftovers -Record $record -Names $Names -Layout $Layout | Where-Object { $_ -ne 'state_folder:scripts' })
    # W9 review item 4: a data folder that is left over keeps the scripts too.
    if (($left.Count -eq 0) -and -not $DataLeft) {
        $scripts = Join-Path $Layout.StateRoot 'scripts'
        Invoke-UninstallPart 'state_folder:scripts' { if (Test-Path -LiteralPath $scripts) { Remove-PathNoFollow -Path $scripts } }
        $left = @(Get-UninstallLeftovers -Record $record -Names $Names -Layout $Layout)
    }
    foreach ($item in $left) { Write-RunLog $step 'FAIL' ('leftover: {0}' -f $item) }
    if ($left.Count -gt 0) { return New-StepResult -Code 'leftovers' -MessageKey 'uninstall.leftovers' -Values @{ items = $left } }
    Write-RunLog $step 'INFO' 'every item removed; WSL and VirtualMachinePlatform stay'
    # R-10: the wizard's last line then says that Windows finishes at the next restart.
    if ($outcome.at_restart) { return New-StepResult -Code 'removed_at_restart' -MessageKey 'uninstall.removed_at_restart' }
    return New-StepResult -Code 'removed' -MessageKey 'uninstall.removed'
}

# ---------------------------------------------------------------------------
# DEC-0041 (TASK-0097 AC-W3, AC-W4): the removal of a setup run that did not finish. Setup is a
# complete installation or nothing: Cancel, closing the window, a failed install and an earlier
# run found at start remove what setup added. Kept data is never deleted, and WSL and Virtual
# Machine Platform go only when setup turned them on and no other distribution is registered.
# ---------------------------------------------------------------------------

function Invoke-LimitedProcess {
    # Runs a program hidden and waits at most LimitSeconds. Returns its exit code, or -1 when it
    # did not end in time (it is left running and logged; nothing waits for it).
    param([Parameter(Mandatory = $true)][string]$File, [string[]]$Arguments = @(), [Parameter(Mandatory = $true)][int]$LimitSeconds)
    Write-RunLog 'setup.remove' 'INFO' ('> {0} {1} (limit {2} s)' -f $File, ($Arguments -join ' '), $LimitSeconds)
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    # Windows PowerShell 5.1 gives the exit code only when the handle was read before the end.
    $null = $process.Handle
    if (-not $process.WaitForExit($LimitSeconds * 1000)) {
        Write-RunLog 'setup.remove' 'WARN' ('{0} did not end in {1} s; setup goes on' -f (Split-Path -Leaf $File), $LimitSeconds)
        return -1
    }
    Write-RunLog 'setup.remove' 'INFO' ('  exit code {0}' -f $process.ExitCode)
    return [int]$process.ExitCode
}

function Test-UserSid {
    # R-7 (Security S97-9): a person's account: a local or domain user (S-1-5-21-) or a
    # Microsoft Entra ID user (S-1-12-1-); not a service or a hive's _Classes key.
    param([AllowNull()][AllowEmptyString()][string]$Sid)
    return [bool]($Sid -match '^S-1-(5-21|12-1)(-[0-9]+)+$')
}

function Get-WslDistroNames {
    # Every WSL distribution of every user whose registry hive is loaded (the per-user Lxss key
    # that "wsl --list" reads, read here for all users at once and without the UTF-16 output of
    # wsl.exe). ok is false when a local profile's hive is not loaded, so its list cannot be read;
    # the caller then keeps WSL. The service account's own profile holds only our distribution.
    param([string]$ServiceSid = '')
    $names = New-Object System.Collections.Generic.List[string]
    $loaded = @{}
    foreach ($key in @(Get-ChildItem -LiteralPath 'Registry::HKEY_USERS' -ErrorAction Stop)) {
        $sid = [string]$key.PSChildName
        if (-not (Test-UserSid $sid)) { continue }
        $loaded[$sid] = $true
        $lxss = 'Registry::HKEY_USERS\{0}\Software\Microsoft\Windows\CurrentVersion\Lxss' -f $sid
        if (-not (Test-Path -LiteralPath $lxss)) { continue }
        foreach ($distro in @(Get-ChildItem -LiteralPath $lxss -ErrorAction Stop)) {
            $name = [string](Get-ItemProperty -LiteralPath $distro.PSPath -ErrorAction Stop).DistributionName
            if ($name) { $names.Add($name) }
        }
    }
    $ok = $true
    foreach ($userProfile in @(Get-CimInstance -ClassName Win32_UserProfile -ErrorAction Stop)) {
        $sid = [string]$userProfile.SID
        if ((-not (Test-UserSid $sid)) -or $userProfile.Special -or $loaded.ContainsKey($sid) -or ($ServiceSid -and ($sid -eq $ServiceSid))) { continue }
        Write-RunLog 'setup.remove' 'INFO' ('the distributions of {0} cannot be read (its profile is not loaded)' -f $sid)
        $ok = $false
    }
    return @{ ok = $ok; names = $names.ToArray() }
}

function Remove-SetupFeatures {
    # WSL and Virtual Machine Platform, only when both rules hold (parent addition to AC-W3):
    # (1) setup turned them on: windows-changes.json says so (vmp_enabled_by_setup, written when
    # S05 enabled the feature; wsl_version_before_setup = none, written before the first WSL
    # install, so an upgrade of an older WSL never counts); (2) no WSL distribution other than
    # ours is registered. A failed or unclear check keeps both. Setup never touches another
    # distribution and never restarts: Windows finishes at the next restart.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [scriptblock]$ListDistros = { Get-WslDistroNames -ServiceSid (Get-RecordedServiceSid -Layout $Layout) },
        [scriptblock]$Run = { param([string]$File, [string[]]$Arguments, [int]$LimitSeconds) Invoke-LimitedProcess -File $File -Arguments $Arguments -LimitSeconds $LimitSeconds }
    )
    $record = Read-WindowsChanges -Layout $Layout
    $vmp = ((Get-DictValue $record 'vmp_enabled_by_setup') -eq $true)
    $wsl = ([string](Get-DictValue $record 'wsl_version_before_setup') -ceq 'none')
    if (-not ($vmp -or $wsl)) {
        Write-RunLog 'setup.remove' 'INFO' 'WSL and Virtual Machine Platform were on this PC before setup; they stay'
        return New-StepResult -Code 'kept' -MessageKey 'setup.features.kept' -Values @{ reason = 'not_by_setup' }
    }
    $check = $null
    try { $check = & $ListDistros } catch { Write-RunLog 'setup.remove' 'WARN' ('distribution check failed: {0}' -f $_.Exception.Message) }
    if (($null -eq $check) -or ($check['ok'] -ne $true)) {
        Write-RunLog 'setup.remove' 'INFO' 'the distribution check failed or is unclear; WSL and Virtual Machine Platform stay'
        return New-StepResult -Code 'kept' -MessageKey 'setup.features.kept' -Values @{ reason = 'check_failed' }
    }
    $others = @(@($check['names']) | Where-Object { $_ -and ([string]$_ -ine $SlateOps.DistroName) })
    if ($others.Count -gt 0) {
        Write-RunLog 'setup.remove' 'INFO' ('{0} other distribution(s) registered; WSL and Virtual Machine Platform stay' -f $others.Count)
        return New-StepResult -Code 'kept' -MessageKey 'setup.features.kept' -Values @{ reason = 'other_distribution' }
    }
    $done = @{ wsl = $false; vmp = $false }
    if ($wsl) { $done.wsl = ((& $Run (Get-WslExe) @('--uninstall') 90) -eq 0) }
    if ($vmp) {
        # dism 3010: done, a restart finishes it.
        $code = & $Run (Join-Path $SlateOpsPaths.System32 'dism.exe') @('/Online', '/Disable-Feature', '/FeatureName:VirtualMachinePlatform', '/NoRestart', '/Quiet') 90
        $done.vmp = (@(0, 3010) -contains $code)
    }
    Write-RunLog 'setup.remove' 'INFO' ('WSL removed: {0}; Virtual Machine Platform off: {1}; Windows finishes at the next restart' -f $done.wsl, $done.vmp)
    if (-not ($done.wsl -or $done.vmp)) { return New-StepResult -Code 'remove_failed' -MessageKey 'setup.features.remove_failed' -Values @{ wsl = $done.wsl; vmp = $done.vmp } }
    return New-StepResult -Code 'removed' -MessageKey 'setup.features.removed' -Values @{ wsl = $done.wsl; vmp = $done.vmp; restart_needed = $true }
}

function Remove-SetupData {
    # The data folder of a setup run that did not finish (state\install.json names it). A data
    # folder that holds kept\ is never deleted: a disk that a kept reinstall moved back goes to
    # kept\ first (the Keep path), then the distribution is unregistered and only this run's
    # distro and payload folders go. Any other data folder: unregister, then the S91-2 delete.
    # The uninstaller keeps its own paths (uninstall-data, kept-return).
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [string]$RunId = '',
        [scriptblock]$ExecJob = {
            param([string]$Job)
            if (-not (Get-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.ExecTaskName -ErrorAction SilentlyContinue)) { return @{ code = 'no_task'; exit_code = 1 } }
            return Invoke-ExecJobAndWait -Layout $Layout -Job $Job -RunId $RunId -TimeoutSeconds 60
        }
    )
    $state = $null
    try { $state = Read-InstallState -Layout $Layout } catch { $state = $null }
    if ($null -eq $state) { return New-StepResult -Code 'nothing' -MessageKey 'setup.remove.nothing' }
    Set-LayoutDataRoot -Layout $Layout -DataRoot $state.data_root
    $paths = Get-KeptPaths -Layout $Layout
    if (Test-Path -LiteralPath $paths.Folder) {
        # R-5 (Architect N-6, Security S97-8): any failure here returns keep_failed and deletes
        # nothing more; the wizard then stops the removal and keeps the state record, so the
        # next start tries again. Kept data is never deleted.
        try {
            if (Test-Path -LiteralPath $paths.Live -PathType Leaf) {
                $null = & $ExecJob 'terminate-distro'
                $moved = Move-KeptDisk -Layout $Layout
                if ($moved.code -ne 'kept') {
                    Write-RunLog 'setup.remove' 'FAIL' 'the kept disk could not go back to kept\; nothing is deleted'
                    return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'move' }
                }
            }
            $job = & $ExecJob 'unregister-distro'
            Write-RunLog 'setup.remove' 'INFO' ('unregister: {0}' -f (Get-DictValue $job 'code'))
            if ((Get-DictValue $job 'exit_code') -ne 0) {
                Write-RunLog 'setup.remove' 'FAIL' 'the distribution was not unregistered; distro and payload stay'
                return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'unregister' }
            }
            foreach ($path in @($Layout.Distro, $Layout.Payload)) { if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path } }
        } catch {
            Write-RunLog 'setup.remove' 'FAIL' ('kept branch: {0}; nothing more is deleted' -f $_.Exception.Message)
            return New-StepResult -Code 'keep_failed' -MessageKey 'uninstall.keep_failed' -Values @{ reason = 'error' }
        }
        Write-RunLog 'setup.remove' 'INFO' ('kept data stays in {0}' -f $paths.Folder)
        return New-StepResult -Code 'returned' -MessageKey 'setup.kept.returned'
    }
    $job = & $ExecJob 'unregister-distro'
    Write-RunLog 'setup.remove' 'INFO' ('unregister: {0}' -f (Get-DictValue $job 'code'))
    return Remove-DataFolder -DataRoot $state.data_root
}

# ---------------------------------------------------------------------------
# Repair (plan 9.3, 10.7 "The service account cannot sign in"; spec M01)
# ---------------------------------------------------------------------------

function Repair-BackupAccess {
    # Option b (parent decision, TASK-0096): Repair gives the account its entry on the recorded
    # backup folder again when the drive is present (a kept reinstall with the drive out, or a
    # lost entry), and moves the folder from the account that a kept reinstall replaced
    # (kept_account_sid in the record). With the drive absent it logs a skip.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$ServiceSid)
    $step = 'maintenance.repair'
    $folder = [string](Get-DictValue (Read-WindowsChanges -Layout $Layout) 'backup_folder')
    if ($folder -cnotmatch '^[A-Z]:\\SlateOps-backups$') {
        Write-RunLog $step 'INFO' 'no backup folder recorded; backup folder rights skipped'
        return New-StepResult -Code 'none' -MessageKey 'maintenance.backup.none'
    }
    $drive = $folder.Substring(0, 2)
    if (-not (Test-Path -LiteralPath ('{0}\' -f $drive))) {
        Write-RunLog $step 'INFO' ('backup drive {0} is not present; backup folder rights skipped' -f $drive)
        return New-StepResult -Code 'drive_missing' -MessageKey 'maintenance.backup.drive_missing'
    }
    if (-not $Layout.DataRoot) { Set-LayoutDataRoot -Layout $Layout -DataRoot (Read-InstallState -Layout $Layout).data_root }
    $old = [string](Get-DictValue (Read-WindowsChanges -Layout $Layout) 'kept_account_sid')
    if ($old -cnotmatch $SlateOpsKept.SidPattern) { $old = '' }
    $backup = Initialize-BackupFolder -Drive $drive -DataRoot $Layout.DataRoot -ServiceSid $ServiceSid -Layout $Layout -OldSid $old
    Write-RunLog $step 'INFO' ('backup folder {0}: {1}' -f $folder, $backup.code)
    if ($backup.code -ne 'ready') { return $backup }
    $record = Read-WindowsChanges -Layout $Layout
    if ($old) {
        if ($old -ne $ServiceSid) { $null = Remove-OldAccountAccess -Folder $folder -OldSid $old -ServiceSid $ServiceSid }
        $record.Remove('kept_account_sid')
        Save-WindowsChanges -Layout $Layout -Record $record
    }
    return $backup
}

function Invoke-Repair {
    # Sets the Windows parts up again: a new password for the account and its rights, both
    # tasks, the firewall rules for the current network, the hosts entry, the boot start. The
    # data does not change. R7 is read again right before the new password exists (11.1 W9).
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $step = 'maintenance.repair'
    # W14-D5 (spec 7.6 "M01 Repair"): one progress line as each of the seven stages starts.
    Write-HelperProgress -Job 'repair' -Number 1 -Total 7 -Key 'r7'
    try { $covered = @(Get-PasswordModuleLogged) } catch { return New-StepResult -Code 'logging_policy_unreadable' -MessageKey 'check.c18.unreadable' }
    if ($covered.Count -gt 0) { return New-StepResult -Code 'logging_policy' -MessageKey 'check.c18.policy' }
    $sid = Get-RecordedServiceSid -Layout $Layout
    $account = $null
    if ($sid) { $account = Get-LocalUser -SID $sid -ErrorAction SilentlyContinue }
    if (-not $account) { return New-StepResult -Code 'account_missing' -MessageKey 'setup.account.missing' }
    $password = New-RandomPassword
    Register-LogSecret $password
    try {
        Write-HelperProgress -Job 'repair' -Number 2 -Total 7 -Key 'account'
        Set-LocalUser -SID $sid -Password (ConvertTo-SecureText -Text $password)
        Initialize-LsaRightsType
        [SlateOpsSetup.LsaRights]::Add($sid, [string[]]$SlateOps.AccountRights)
        Write-RunLog $step 'INFO' 'account password set again (not stored, not shown); rights set again'
        Write-HelperProgress -Job 'repair' -Number 3 -Total 7 -Key 'tasks'
        Register-ServiceTasks -Layout $Layout -AccountName $account.Name -Password $password
    } finally { $password = $null }
    $steps = @()
    Write-HelperProgress -Job 'repair' -Number 4 -Total 7 -Key 'firewall'
    $lan = Get-LanFact
    if ($lan) { $steps += Set-FirewallRules -Layout $Layout -Cidr (ConvertTo-NetworkCidr -Address $lan.address -PrefixLength $lan.prefix_length) }
    Write-HelperProgress -Job 'repair' -Number 5 -Total 7 -Key 'hosts'
    # DEC-0039: the stored address label, not the computer name.
    $label = Get-InstallAddressLabel -Layout $Layout
    if ($label) { $steps += Set-HostsEntry -Layout $Layout -HostName ('{0}.local' -f $label) }
    else {
        Write-RunLog $step 'WARN' 'no address label recorded; the hosts entry is not written'
        $steps += New-StepResult -Code 'label_missing' -MessageKey 'install.windows.label_missing'
    }
    # The start task runs before the result of the steps above is read (unchanged order), so
    # the start is stage 6 and the backup folder rights stage 7.
    Write-HelperProgress -Job 'repair' -Number 6 -Total 7 -Key 'start'
    Enable-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName | Out-Null
    Start-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName
    $failed = @($steps | Where-Object { $_.code -ne 'added' })
    if ($failed.Count -gt 0) { return $failed[0] }
    # Option b: the backup folder rights (a skip when the drive is out is not a failure).
    Write-HelperProgress -Job 'repair' -Number 7 -Total 7 -Key 'backup'
    $backup = Repair-BackupAccess -Layout $Layout -ServiceSid $sid
    if (@('ready', 'none', 'drive_missing') -notcontains $backup.code) { return $backup }
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
