# Uninstall.Tests.ps1 - the W9 criteria that a Windows runner can prove (TASK-0096): both answers
# remove the items of plan 9.1 (W9-1) and every leftover is logged (W9-6); "Keep my data" moves
# and checks the disk (F3); "Delete everything" follows no link and keeps the S91-2 parent rule;
# kept data is read after its checks and a newer version blocks (W9-2, W9-3). Every name and
# path is the test's own: no test touches \SlateOps\, the real hosts file or the power values.

function New-UninstallLayout {
    param([Parameter(Mandatory = $true)][string]$Name)
    $root = New-TestDirectory $Name
    # The protected-tree call creates the tree root only; its parent must exist (as
    # C:\ProgramData does on Windows).
    foreach ($parent in @('ProgramData', 'Data')) { [void][System.IO.Directory]::CreateDirectory((Join-Path $root $parent)) }
    $layout = New-SlateOpsLayout -StateRoot (Join-Path $root 'ProgramData\SlateOps') -DataRoot (Join-Path $root 'Data\SlateOps')
    $null = Initialize-ProtectedTree -Tree $layout.StateTree
    return $layout
}

function Get-TestNames {
    param([Parameter(Mandatory = $true)][string]$Tag, [Parameter(Mandatory = $true)][string]$HostsPath)
    return @{
        TaskPath = ('\SlateOpsW9{0}\' -f $Tag); TaskFolder = ('SlateOpsW9{0}' -f $Tag); AccountName = ''
        HostsPath = $HostsPath; UserList = ('HKLM:\SOFTWARE\SlateOpsW9{0}\SpecialAccounts\UserList' -f $Tag)
        StoreLocation = 'LocalMachine'; Power = $false
    }
}

Test-Case 'W9-1 both answers remove the tasks, the account, the rules, the hosts line, the CA and the state folder, and keep the logs' {
    $layout = New-UninstallLayout 'w9-1-remove'
    foreach ($folder in @('settings')) { [void][System.IO.Directory]::CreateDirectory((Join-Path $layout.StateRoot $folder)) }
    $hosts = Join-Path (New-TestDirectory 'w9-1-hosts') 'hosts'
    [System.IO.File]::WriteAllText($hosts, "127.0.0.1 localhost`r`n127.0.0.1 office-pc.local # Slate Operations`r`n")
    $names = Get-TestNames -Tag 'Remove' -HostsPath $hosts
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c exit 0'
    Register-ScheduledTask -TaskPath $names.TaskPath -TaskName 'Start' -Action $action -Force | Out-Null
    $sid = New-TestUser 'slateops-w9rm'
    New-Item -Path $names.UserList -Force | Out-Null
    New-ItemProperty -LiteralPath $names.UserList -Name 'slateops-w9rm' -PropertyType DWord -Value 0 -Force | Out-Null
    $rule = 'SlateOpsW9Test-TCP'
    New-NetFirewallRule -Name $rule -DisplayName $rule -Direction Inbound -Action Allow -Protocol TCP -LocalPort 65001 -Enabled False | Out-Null
    $certificate = New-SelfSignedCertificate -Subject 'CN=Slate Operations W9 test' -CertStoreLocation 'Cert:\LocalMachine\My' -KeyUsage CertSign -TextExtension @('2.5.29.19={text}CA=true')
    $root = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
    $root.Open('ReadWrite'); $root.Add($certificate); $root.Close()
    try {
        Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{
                account_sid = $sid; firewall_rules = @($rule); hyperv_rules = @(); ca_thumbprint = $certificate.Thumbprint
                userlist_key_existed = $false; specialaccounts_key_existed = $false
            })
        [System.IO.File]::WriteAllText((Join-Path $layout.Logs 'setup\install-20261117T032000Z-abc123.log'), 'kept')
        $result = Remove-WindowsParts -Layout $layout -Names $names
        Assert-Equal 'removed' $result.code (ConvertTo-JsonText $result)
        Assert-Equal 0 @(Get-ScheduledTask -TaskPath $names.TaskPath -ErrorAction SilentlyContinue).Count 'tasks'
        Assert-Equal $null (Get-LocalUser -SID $sid -ErrorAction SilentlyContinue) 'account'
        Assert-Equal $null (Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue) 'firewall rule'
        Assert-Equal "127.0.0.1 localhost`r`n" ([System.IO.File]::ReadAllText($hosts)) 'only the hosts line of Slate Operations goes'
        Assert-Equal $false (Test-Path -LiteralPath ('Cert:\LocalMachine\Root\{0}' -f $certificate.Thumbprint)) 'CA'
        Assert-Equal $false (Test-Path -LiteralPath (Split-Path -Parent $names.UserList)) 'the keys that did not exist before go'
        Assert-Equal @('logs') @(Get-ChildItem -LiteralPath $layout.StateRoot -Force | ForEach-Object { $_.Name }) 'the logs stay'
    } finally {
        Remove-Item -LiteralPath ('Cert:\LocalMachine\My\{0}' -f $certificate.Thumbprint) -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath ('Cert:\LocalMachine\Root\{0}' -f $certificate.Thumbprint) -ErrorAction SilentlyContinue
        Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Remove-Item -LiteralPath 'HKLM:\SOFTWARE\SlateOpsW9Remove' -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Test-Case 'W9-6 an item that cannot be removed is a leftover in the result and in the log' {
    $layout = New-UninstallLayout 'w9-6-leftover'
    $hosts = Join-Path (New-TestDirectory 'w9-6-hosts') 'hosts'
    [System.IO.File]::WriteAllText($hosts, "127.0.0.1 localhost`r`n")
    $names = Get-TestNames -Tag 'Leftover' -HostsPath $hosts
    $logDir = New-TestDirectory 'w9-6-log'
    Start-RunLog -RunId 'uninstall-20261117T050000Z-w9left' -Directory $logDir -NoConsole
    # A file held open with no sharing keeps state\ in place.
    $held = [System.IO.File]::Open((Join-Path $layout.State 'held.json'), [System.IO.FileMode]::Create, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    try { $result = Remove-WindowsParts -Layout $layout -Names $names } finally { $held.Dispose() }
    Assert-Equal 'leftovers' $result.code
    Assert-Equal @('state_folder:state') @($result.values.items)
    $log = [System.IO.File]::ReadAllText((Join-Path $logDir 'uninstall-20261117T050000Z-w9left.log'))
    Assert-True ($log -match 'FAIL leftover: state_folder:state') $log
}

Test-Case 'W9-1 F3 Keep my data moves the disk with kept.json, checks it, and refuses an engine value of the wrong shape' {
    $layout = New-UninstallLayout 'w9-keep'
    $null = Initialize-ProtectedTree -Tree $layout.DataTree
    $disk = Join-Path $layout.Distro 'ext4.vhdx'
    [System.IO.File]::WriteAllBytes($disk, (New-Object byte[] 4096))
    $bad = @{ instance_id = 'abc123'; business_name = 'Riverside'; public_host = 'C:\Windows' }
    Assert-Equal 'keep_failed' (Move-KeptDisk -Layout $layout -Info $bad -Version '0.2.0' -Record).code
    Assert-Equal $true (Test-Path -LiteralPath $disk) 'nothing moved'
    $info = @{ instance_id = 'abc123'; business_name = 'Riverside Learning Center'; public_host = 'office-pc.local' }
    $result = Move-KeptDisk -Layout $layout -Info $info -Version '0.2.0' -Record
    Assert-Equal 'kept' $result.code
    Assert-Equal $false (Test-Path -LiteralPath $disk)
    Assert-Equal $true (Test-KeptAfterUnregister -Layout $layout -Bytes 4096)
    $kept = Read-JsonFile -Path (Join-Path $layout.DataRoot 'kept\kept.json')
    Assert-Equal '0.2.0 abc123 Riverside Learning Center office-pc.local' ('{0} {1} {2} {3}' -f $kept['version'], $kept['instance_id'], $kept['business_name'], $kept['public_host'])
}

Test-Case 'W9-1 Delete everything keeps the S91-2 parent rule, removes a link inside as a link, and deletes only the recorded backup folder' {
    $outside = New-TestDirectory 'w9-delete-outside'
    [System.IO.File]::WriteAllText((Join-Path $outside 'keep.txt'), 'outside')
    # An administrator-only folder on the system drive (Folders.Tests.ps1): the runner's temp
    # folders have parents that the S91-2 rule refuses.
    $root = New-AdminOnlyFolder 'SlateOpsW9Delete'
    try {
        $data = Join-Path $root 'SlateOps'
        [void][System.IO.Directory]::CreateDirectory((Join-Path $data 'distro'))
        $null = & cmd.exe /c mklink /J (Join-Path $data 'distro\linked') $outside 2>&1
        Assert-Equal 'removed' (Remove-DataFolder -DataRoot $data).code
        Assert-Equal $false (Test-Path -LiteralPath $data)
        Assert-Equal $true (Test-Path -LiteralPath (Join-Path $outside 'keep.txt')) 'the folder behind the link stays'
    } finally { Remove-PathNoFollow -Path $root }
    $open = New-TestDirectory 'w9-delete-open'
    $unsafe = Join-Path $open 'SlateOps'
    [void][System.IO.Directory]::CreateDirectory($unsafe)
    $null = & icacls.exe $open /grant '*S-1-5-11:(OI)(CI)M' 2>&1
    Assert-Equal 'data_folder_parent_unsafe' (Remove-DataFolder -DataRoot $unsafe).code
    Assert-Equal $true (Test-Path -LiteralPath $unsafe) 'nothing is removed under an unsafe parent'
    Assert-Equal 'backup_path_invalid' (Remove-BackupFolder -Folder (Join-Path $root 'SlateOps-backups')).code
    $backups = '{0}\SlateOps-backups' -f (Split-Path -Qualifier $script:TestRoot)
    $existed = Test-Path -LiteralPath $backups
    if (-not $existed) {
        # A folder that setup created: a protected list for Administrators and SYSTEM (W9-S1).
        [void][System.IO.Directory]::CreateDirectory($backups, (Get-ProtectedDirectorySecurity))
        Assert-Equal 'removed' (Remove-BackupFolder -Folder $backups).code
        Assert-Equal $false (Test-Path -LiteralPath $backups)
    }
}

Test-Case 'W9-2 W9-3 kept data is read after its checks, a newer version blocks, and the disk comes back owned by Administrators' {
    # Kept data is read only under folders that pass the S91-2 parent rule; the runner's temp
    # folders do not, so the data folder lies in an administrator-only system-drive folder.
    $root = New-AdminOnlyFolder 'SlateOpsW9Kept'
    try {
        $layout = New-SlateOpsLayout -StateRoot (Join-Path $root 'ProgramData\SlateOps') -DataRoot (Join-Path $root 'SlateOps')
        $null = Initialize-ProtectedTree -Tree $layout.DataTree
        [System.IO.File]::WriteAllBytes((Join-Path $layout.Distro 'ext4.vhdx'), (New-Object byte[] 2048))
        $info = @{ instance_id = 'abc123'; business_name = 'Riverside Learning Center'; public_host = 'office-pc.local' }
        Assert-Equal 'kept' (Move-KeptDisk -Layout $layout -Info $info -Version '0.2.1' -Record).code
        $newer = Get-KeptData -DataRoot $layout.DataRoot -SetupVersion '0.2.0'
        Assert-Equal 'kept_newer 0.2.1' ('{0} {1}' -f $newer.code, $newer.values.version)
        Assert-Equal 'kept' (Get-KeptData -DataRoot $layout.DataRoot -SetupVersion '0.2.1').code
        Assert-Equal 'kept_older' (Get-KeptData -DataRoot $layout.DataRoot -SetupVersion '0.3.0').code
        Assert-Equal $false (Test-KeptInstance -Layout $layout -Status @{ values = @{} }) 'a missing instance ID is a stop'
        Assert-Equal $false (Test-KeptInstance -Layout $layout -Status @{ values = @{ instance_id = 'other' } })
        Assert-Equal $true (Test-KeptInstance -Layout $layout -Status @{ values = @{ instance_id = 'abc123' } })
        Assert-Equal 'restored' (Restore-KeptDisk -Layout $layout).code
        $owner = (Get-Acl -LiteralPath (Join-Path $layout.Distro 'ext4.vhdx')).GetOwner([System.Security.Principal.SecurityIdentifier]).Value
        Assert-Equal 'S-1-5-32-544' $owner
        Assert-Equal 'none' (Get-KeptData -DataRoot (Join-Path $script:TestRoot 'no-such\SlateOps') -SetupVersion '0.2.1').code
    } finally { Remove-PathNoFollow -Path $root }
}

Test-Case 'W9-1 engine carry a failed keep path terminates the distribution before the start task runs again' {
    # prepare-uninstall stops Docker; only a new Linux start brings it back (TASK-0096 engine
    # carry). The Exec call is recorded here instead of running the task.
    $script:W9Jobs = New-Object System.Collections.Generic.List[string]
    function Invoke-ExecJobAndWait {
        param([hashtable]$Layout, [string]$Job, [string]$RunId, [string]$InputText = '', [int]$TimeoutSeconds = 600)
        $script:W9Jobs.Add($Job)
        return @{ code = 'terminated'; exit_code = 0; job = $Job }
    }
    $layout = New-UninstallLayout 'w9-keep-restore'
    $logDir = New-TestDirectory 'w9-keep-restore-log'
    Start-RunLog -RunId 'uninstall-20261117T060000Z-w9rest' -Directory $logDir -NoConsole
    Restore-ServerAfterKeepFailure -Layout $layout -RunId 'uninstall-20261117T060000Z-w9rest'
    Assert-Equal @('terminate-distro') @($script:W9Jobs)
    $log = [System.IO.File]::ReadAllText((Join-Path $logDir 'uninstall-20261117T060000Z-w9rest.log'))
    Assert-True ($log -match 'distribution terminated: terminated') $log
}

Test-Case 'W9 review item 4 a data folder left over keeps the scripts folder, so U04 can save a report' {
    $layout = New-UninstallLayout 'w9-review-4'
    $hosts = Join-Path (New-TestDirectory 'w9-review-4-hosts') 'hosts'
    [System.IO.File]::WriteAllText($hosts, "127.0.0.1 localhost`r`n")
    $names = Get-TestNames -Tag 'Review4' -HostsPath $hosts
    $result = Remove-WindowsParts -Layout $layout -Names $names -DataLeft
    Assert-Equal $true (Test-Path -LiteralPath $layout.Scripts) 'scripts stays'
    Assert-Equal $false (Test-Path -LiteralPath $layout.State) 'the rest goes'
    Assert-Equal 'removed' $result.code
    $plain = New-UninstallLayout 'w9-review-4c'
    $null = Remove-WindowsParts -Layout $plain -Names $names
    Assert-Equal $false (Test-Path -LiteralPath $plain.Scripts) 'without a data leftover the scripts go'
}

Test-Case 'W9 review item 5 M01 reads a changed network from the recorded rule range' {
    $layout = New-UninstallLayout 'w9-review-5'
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ hyperv_cidr = '192.168.1.0/24' })
    function Get-LanFact { return $script:W9Lan }
    $script:W9Lan = @{ address = '192.168.1.23'; prefix_length = 24 }
    Assert-Equal $false (Test-NetworkChanged -Layout $layout) 'same range'
    $script:W9Lan = @{ address = '10.0.0.5'; prefix_length = 24 }
    Assert-Equal $true (Test-NetworkChanged -Layout $layout) 'another range'
    $script:W9Lan = $null
    Assert-Equal $false (Test-NetworkChanged -Layout $layout) 'no network: no claim'
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ account_sid = 'S-1-5-21-1-2-3-1001' })
    $script:W9Lan = @{ address = '10.0.0.5'; prefix_length = 24 }
    Assert-Equal $false (Test-NetworkChanged -Layout $layout) 'no recorded range: no claim'
}

Test-Case 'W9 review item 10 S91-2 a backup folder that a standard user can change is not deleted' {
    # Security W9-S1: before the delete, the folder passes the tree rule: owner Administrators or
    # SYSTEM, a protected list, writers only Administrators, SYSTEM and the service account.
    $sid = New-TestUser 'slateops-w9bk'
    $open = New-TestDirectory 'w9-review-10-open'
    [System.IO.File]::WriteAllText((Join-Path $open 'snapshot'), 'x')
    $null = & icacls.exe $open /grant '*S-1-5-11:(OI)(CI)M' 2>&1
    Assert-True (@(Get-BackupFolderProblem -Folder $open -ServiceSid $sid).Count -gt 0) 'Authenticated Users Modify is a problem'
    $root = New-AdminOnlyFolder 'SlateOpsW9Backup'
    try {
        $closed = Join-Path $root 'SlateOps-backups'
        $security = Get-ProtectedDirectorySecurity
        $security.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule((New-Object System.Security.Principal.SecurityIdentifier($sid)), 'Modify, Synchronize', 'ContainerInherit, ObjectInherit', 'None', 'Allow')))
        [void][System.IO.Directory]::CreateDirectory($closed, $security)
        [System.IO.File]::WriteAllText((Join-Path $closed 'snapshot'), 'x')
        $found = @(Get-BackupFolderProblem -Folder $closed -ServiceSid $sid)
        Assert-Equal 0 $found.Count ('protected folder: ' + ($found -join '; '))
        # A protected folder with an explicit Authenticated Users Modify entry: the writer rule
        # alone refuses it.
        $null = & icacls.exe $closed /grant '*S-1-5-11:(OI)(CI)M' 2>&1
        $found = @(Get-BackupFolderProblem -Folder $closed -ServiceSid $sid)
        Assert-True (@($found | Where-Object { $_ -like 'writer:*:S-1-5-11' }).Count -gt 0) ($found -join '; ')
        Assert-Equal 0 @($found | Where-Object { $_ -like 'inherits:*' }).Count 'the folder is protected'
    } finally { Remove-PathNoFollow -Path $root }
    $backups = '{0}\SlateOps-backups' -f (Split-Path -Qualifier $script:TestRoot)
    if (-not (Test-Path -LiteralPath $backups)) {
        [void][System.IO.Directory]::CreateDirectory($backups)
        $null = & icacls.exe $backups /grant '*S-1-5-11:(OI)(CI)M' 2>&1
        try {
            Assert-Equal 'backup_folder_unsafe' (Remove-BackupFolder -Folder $backups -ServiceSid $sid).code
            Assert-Equal $true (Test-Path -LiteralPath $backups) 'nothing is deleted'
        } finally { Remove-PathNoFollow -Path $backups }
    }
}
