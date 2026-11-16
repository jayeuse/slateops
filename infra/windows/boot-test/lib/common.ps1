# common.ps1 - shared settings and helpers for the Slate Operations WSL2 boot-test kit.
#
# Every kit script dot-sources this file. It holds the pinned versions and checksums,
# the names of everything the kit creates, logging, the dry-run (-WhatIf) wrapper, and
# small Windows helpers. Windows PowerShell 5.1 only. Keep this file ASCII only:
# Windows PowerShell 5.1 reads a file without a byte order mark as ANSI.

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------------------
# Names, paths, pinned versions
# ---------------------------------------------------------------------------

$BootTest = @{
    Root             = Join-Path $env:ProgramData 'SlateOpsBootTest'
    AccountName      = 'slateops-svc'
    DistroName       = 'SlateOpsBootTest'
    TaskPath         = '\SlateOpsBootTest\'
    TaskFolder       = 'SlateOpsBootTest'
    StartTaskName    = 'Start'
    ExecTaskName     = 'Exec'
    ResumeTaskName   = 'ResumeSetup'
    Port             = 8443
    FirewallRuleName = 'SlateOpsBootTest-TCP-8443'
    HyperVRuleName   = 'SlateOpsBootTest-HyperV-TCP-8443'
    FirewallGroup    = 'SlateOps boot test'
    # The VM creator ID of WSL, from the WSL networking documentation.
    WslVmCreatorId   = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'
    # Mirrored networking needs Windows 11 22H2 (build 22621) or later.
    MinBuild         = 22621
    # [general] instanceIdleTimeout needs WSL 2.5.4 or later.
    MinWslVersion    = [version]'2.5.4'
    # Offline WSL package, github.com/microsoft/WSL release 3.0.3 (stable, 2026-10-09).
    # Deliberately one stable release behind the newest stable (3.0.5, 2026-11-03), so that
    # event E6 ("wsl --update" while the service runs) has a real update to install.
    # SHA-256 values are the GitHub release asset digests.
    WslVersion       = [version]'3.0.3.0'
    WslMsi           = @{
        AMD64 = @{
            Url    = 'https://github.com/microsoft/WSL/releases/download/3.0.3/wsl.3.0.3.0.x64.msi'
            Sha256 = 'ae977286974255bd26bf925f00f40f5692c6b2084155cbc0563c09aea091f211'
        }
        ARM64 = @{
            Url    = 'https://github.com/microsoft/WSL/releases/download/3.0.3/wsl.3.0.3.0.arm64.msi'
            Sha256 = '2937c7ce840bb35ec6e97f052189bdfff27f8c3463bfdd231df9a958212787a3'
        }
    }
    # Debian 13 (trixie) WSL image v1.26.0.0, built by the Debian WSL team on salsa.debian.org.
    # URL and SHA-256 come from Microsoft's WSL distribution manifest
    # (github.com/microsoft/WSL, distributions/DistributionInfo.json, commit fff9ea76).
    Rootfs           = @{
        AMD64 = @{
            Url    = 'https://salsa.debian.org/debian/WSL/-/jobs/9606244/artifacts/raw/Debian_WSL_AMD64_v1.26.0.0.wsl'
            Sha256 = '5ec7dc68216e75d1d4d4761474e99d8461a98d316537110314b137122a879e0f'
        }
        ARM64 = @{
            Url    = 'https://salsa.debian.org/debian/WSL/-/jobs/9606244/artifacts/raw/Debian_WSL_ARM64_v1.26.0.0.wsl'
            Sha256 = '09120df4fadc36fb2a0f7298e197785e6f599f12aaf95d43cba07a8ac7fb316b'
        }
    }
    DistroDiskSize   = '64GB'
    LinuxLib         = '/usr/local/lib/slateops-boottest'
    MinFreeDiskGB    = 15
}
$BootTest.Kit         = Join-Path $BootTest.Root 'kit'
$BootTest.Cache       = Join-Path $BootTest.Root 'cache'
$BootTest.Distro      = Join-Path $BootTest.Root 'distro'
$BootTest.State       = Join-Path $BootTest.Root 'state'
# logs: administrators only. svc-out: the only folder (with distro) that the service account
# can write; the administrator side only reads it, as data.
$BootTest.Logs        = Join-Path $BootTest.Root 'logs'
$BootTest.SvcOut      = Join-Path $BootTest.Root 'svc-out'
$BootTest.StateFile   = Join-Path $BootTest.State 'state.json'
$BootTest.RequestFile = Join-Path $BootTest.State 'request.txt'
$BootTest.ResultFile  = Join-Path $BootTest.SvcOut 'svc-exec-result.json'
$BootTest.StatusUrl   = 'http://127.0.0.1:{0}/' -f $BootTest.Port

# ---------------------------------------------------------------------------
# P1: installer plan slice S1 (real stack, measurements) and spikes F1 to F5, F10
# ---------------------------------------------------------------------------
# source: the repository source from the ZIP, as one tar file (read for the service account).
# spike:  the throwaway distribution of F3 and F5 (modify for slateops-svc and slateops-f3).
# f3-out: output of the F3 account (modify for slateops-f3 only).
# f4:     the copy of the F4 test installer that its RunOnce entry starts (administrators only).
$BootTest.Source = Join-Path $BootTest.Root 'source'
$BootTest.Spike  = Join-Path $BootTest.Root 'spike'
$BootTest.F3Out  = Join-Path $BootTest.Root 'f3-out'
$BootTest.F4Dir  = Join-Path $BootTest.Root 'f4'
$BootTest.P1 = @{
    SourceTar        = Join-Path $BootTest.Source 'slateops-src.tar'
    StateFile        = Join-Path $BootTest.State 'p1-state.json'
    ProbeResult      = Join-Path $BootTest.Logs 'p1-probe-result.json'
    ProbeSamples     = Join-Path $BootTest.Logs 'p1-probe-vmmem.csv'
    F4ResultFile     = Join-Path $BootTest.Logs 'f4-results.txt'
    ProbeTaskName    = 'P1Probe'
    F3TaskName       = 'F3'
    ResumeTaskName   = 'P1Resume'
    F3AccountName    = 'slateops-f3'
    SpikeDistroName  = 'SlateOpsSpike'
    LinuxS1          = '/usr/local/lib/slateops-boottest/s1/s1.sh'
    WindowsRules     = @{ 443 = 'SlateOpsP1-TCP-443'; 80 = 'SlateOpsP1-TCP-80' }
    HyperVRules      = @{ 443 = 'SlateOpsP1-HyperV-TCP-443'; 80 = 'SlateOpsP1-HyperV-TCP-80' }
    HyperVMdnsRule   = 'SlateOpsP1-HyperV-UDP-5353'
    HostsMarker      = '# SlateOps-P1 test kit'
    # The image builds and the provider images need room; C: had 26.6 GB free before the boot test.
    MinFreeGB        = 20
    WslMemoryGB      = 8
    # F4 test installer (Inno Setup, built from f4\p1-f4-test.iss). The SHA-256 is the exact
    # file that the parent attached to the draft GitHub release.
    F4ExeName        = 'SlateOpsP1F4Test.exe'
    F4Sha256         = '5532669ee11f6b7a276177fbd1dc719ec51d67f5989349ab44e7414f7c59fe48'
    F4UninstallKey   = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{5E0F1C2A-7B3D-4A61-9C8E-2F4D6B1A0C93}_is1'
    F4RunOnceName    = 'SlateOpsP1F4Resume'
    # F10: offline WSL packages by version (GitHub release asset digests, read 2026-11-16 from
    # api.github.com/repos/microsoft/WSL/releases). 3.0.5 (2026-11-03) is the newest stable.
    WslMsi           = @{
        '3.0.3.0' = @{
            AMD64 = @{ Url = 'https://github.com/microsoft/WSL/releases/download/3.0.3/wsl.3.0.3.0.x64.msi'; Sha256 = 'ae977286974255bd26bf925f00f40f5692c6b2084155cbc0563c09aea091f211' }
            ARM64 = @{ Url = 'https://github.com/microsoft/WSL/releases/download/3.0.3/wsl.3.0.3.0.arm64.msi'; Sha256 = '2937c7ce840bb35ec6e97f052189bdfff27f8c3463bfdd231df9a958212787a3' }
        }
        '3.0.5.0' = @{
            AMD64 = @{ Url = 'https://github.com/microsoft/WSL/releases/download/3.0.5/wsl.3.0.5.0.x64.msi'; Sha256 = '2313efc5873e3f8552f42e77f950fabd913c0289078fa89d2100f3421a525eaa' }
            ARM64 = @{ Url = 'https://github.com/microsoft/WSL/releases/download/3.0.5/wsl.3.0.5.0.arm64.msi'; Sha256 = '0596d4e3f4df1d7c78eed39ac83576863a9fd663c90fac35f76ba7d2c8d79157' }
        }
    }
    WslNewestStable  = [version]'3.0.5.0'
}

# Well-known SIDs (names are localized, SIDs are not).
$BootTest.SidAdministrators = 'S-1-5-32-544'
$BootTest.SidSystem         = 'S-1-5-18'
$BootTest.SidUsers          = 'S-1-5-32-545'

# Logon rights that setup gives to the service account, and that cleanup removes.
# "Log on as a batch job": Task Scheduler needs it.
$BootTest.BatchRight = 'SeBatchLogonRight'
# Deny rights (setup skips them with -NoDenyRights):
#   SeDenyInteractiveLogonRight        "Deny log on locally": no sign-in at the PC.
#   SeDenyRemoteInteractiveLogonRight  "Deny log on through Remote Desktop Services".
#   SeDenyNetworkLogonRight            "Deny access to this computer from the network".
$BootTest.DenyRights = @('SeDenyInteractiveLogonRight', 'SeDenyRemoteInteractiveLogonRight', 'SeDenyNetworkLogonRight')
$BootTest.AccountRights = @($BootTest.BatchRight) + $BootTest.DenyRights

# ---------------------------------------------------------------------------
# Logging and dry run
# ---------------------------------------------------------------------------

$script:BootTestLogFile = $null
$script:BootTestDryRun = $false

function Initialize-BootTestLog {
    # Starts the log. In dry-run mode the log goes to the screen only, so -WhatIf writes no file.
    # A log folder under C:\ProgramData\SlateOpsBootTest is created only through
    # Initialize-BootTestRoot (protected ACL from the first moment) and only after the folder
    # passes the quick safety check. If the check fails, the log goes to %TEMP% instead.
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [switch]$DryRun,
        [switch]$Append,
        [string]$Directory = $BootTest.Logs
    )
    $script:BootTestDryRun = [bool]$DryRun
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { $null = $_ }
    if ($DryRun) {
        $script:BootTestLogFile = $null
        return
    }
    $warning = $null
    if (Test-PathUnderRoot -Path $Directory) {
        if ($Directory -ieq $BootTest.Logs) { $null = Initialize-BootTestRoot }
        $problems = @(Get-BootTestTreeProblem -Quick -Directory $Directory)
        if ($problems.Count -gt 0) {
            $warning = ('{0} failed the safety check ({1}); this log goes to {2}.' -f $Directory, ($problems -join '; '), $env:TEMP)
            $Directory = $env:TEMP
        }
    }
    if (-not (Test-Path -LiteralPath $Directory)) {
        New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    }
    if ($Append) {
        $script:BootTestLogFile = Join-Path $Directory ('{0}.log' -f $Name)
    } else {
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
        $script:BootTestLogFile = Join-Path $Directory ('{0}-{1}.log' -f $Name, $stamp)
    }
    if ($warning) { Write-KitLog $warning 'WARN' }
}

# ---------------------------------------------------------------------------
# Kit folder C:\ProgramData\SlateOpsBootTest: creation, safety check, safe delete
# ---------------------------------------------------------------------------
# C:\ProgramData lets every user create folders. A folder that another user created first
# (or a junction planted inside it) could make setup run a swapped script or MSI with
# administrator rights. So: the root is created in one call with a protected
# Administrators/SYSTEM ACL; setup stops if the root or anything below it has an
# unexpected owner, ACL entry or reparse point; deletes never follow reparse points.

function Test-PathUnderRoot {
    param([Parameter(Mandatory = $true)][string]$Path)
    $root = $BootTest.Root.TrimEnd('\')
    return (($Path.TrimEnd('\') -ieq $root) -or $Path.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase))
}

function Get-ProtectedDirectorySecurity {
    # Administrators and SYSTEM: Full control, inherited by every child. No other entry,
    # and no entries inherited from C:\ProgramData.
    $security = New-Object System.Security.AccessControl.DirectorySecurity
    $security.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($BootTest.SidAdministrators, $BootTest.SidSystem)) {
        $identity = New-Object System.Security.Principal.SecurityIdentifier($sid)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
        $security.AddAccessRule($rule)
    }
    return $security
}

function Initialize-BootTestRoot {
    # Creates the root with the protected ACL in the same call (Directory.CreateDirectory with a
    # DirectorySecurity, .NET Framework), so there is no moment without it. Returns $true when it
    # created the root. If the root already exists it changes nothing: the caller must run
    # Get-BootTestTreeProblem (another user could create the root between the test and the call).
    if (Test-Path -LiteralPath $BootTest.Root) { return $false }
    [void][System.IO.Directory]::CreateDirectory($BootTest.Root, (Get-ProtectedDirectorySecurity))
    return $true
}

function Get-BootTestServiceSid {
    $account = Get-LocalUser -Name $BootTest.AccountName -ErrorAction SilentlyContinue
    if ($account) { return $account.SID.Value }
    return $null
}

function Get-BootTestF3Sid {
    $account = Get-LocalUser -Name $BootTest.P1.F3AccountName -ErrorAction SilentlyContinue
    if ($account) { return $account.SID.Value }
    return $null
}

function Test-PathInArea {
    param([Parameter(Mandatory = $true)][string]$Path, [string[]]$Areas = @())
    foreach ($area in $Areas) {
        if (($Path -ieq $area) -or $Path.StartsWith($area + '\', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function Get-BootTestTreeProblem {
    # Returns a list of problems (empty when the folder is safe):
    # - the root is not owned by Administrators, SYSTEM or the current administrator,
    # - the root ACL inherits entries or allows anyone other than Administrators, SYSTEM and
    #   (read, this folder only) the service account and the P1 F3 account,
    # - a top-level folder has an explicit allow entry other than the expected ones,
    # - an item below the root is a reparse point (junction or link) or has another owner.
    #   slateops-svc may own items in svc-out, distro and spike only; the P1 account
    #   slateops-f3 (spike F3) may own items in f3-out and spike only.
    # -Quick checks the root and -Directory only (used before writing a log).
    param([switch]$Quick, [string]$Directory)
    $problems = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $BootTest.Root)) { return $problems.ToArray() }
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $trusted = @($BootTest.SidAdministrators, $BootTest.SidSystem, $currentUser)
    $svcSid = Get-BootTestServiceSid
    $f3Sid = Get-BootTestF3Sid
    $accountSids = @($svcSid, $f3Sid | Where-Object { $_ })
    $sidType = [System.Security.Principal.SecurityIdentifier]
    # Folders where each account may hold an explicit access entry (read or modify), and where
    # it may own items (writable).
    $svcEntries = @($BootTest.Kit, $BootTest.Cache, $BootTest.State, $BootTest.Source, $BootTest.SvcOut, $BootTest.Distro, $BootTest.Spike)
    $f3Entries = @($BootTest.Kit, $BootTest.State, $BootTest.Spike, $BootTest.F3Out)
    $svcWritable = @($BootTest.SvcOut, $BootTest.Distro, $BootTest.Spike)
    $f3Writable = @($BootTest.F3Out, $BootTest.Spike)
    # Folders that the accounts may only read, at every depth: an allow entry (explicit or
    # inherited) with write, delete, change-permission or take-ownership rights is a problem.
    $readOnlyAreas = @($BootTest.Kit, $BootTest.Cache, $BootTest.State, $BootTest.Source)
    $writeMask = [int64](2 + 4 + 16 + 64 + 256 + 65536 + 262144 + 524288) -bor [int64]0x10000000 -bor [int64]0x40000000

    $rootItem = Get-Item -LiteralPath $BootTest.Root -Force
    if ($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { $problems.Add('the root is a reparse point'); return $problems.ToArray() }
    $rootAcl = Get-Acl -LiteralPath $BootTest.Root
    $rootOwner = $rootAcl.GetOwner($sidType).Value
    if ($trusted -notcontains $rootOwner) { $problems.Add(('the root is owned by {0}' -f $rootOwner)) }
    if (-not $rootAcl.AreAccessRulesProtected) { $problems.Add('the root inherits access entries from C:\ProgramData') }
    foreach ($rule in $rootAcl.GetAccessRules($true, $true, $sidType)) {
        if ($rule.AccessControlType -ne 'Allow') { continue }
        $sid = $rule.IdentityReference.Value
        if (($sid -eq $BootTest.SidAdministrators) -or ($sid -eq $BootTest.SidSystem)) { continue }
        $readOnly = (($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Write) -eq 0) -and
            (($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Delete) -eq 0) -and
            (($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::ChangePermissions) -eq 0) -and
            (($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::TakeOwnership) -eq 0)
        if (($accountSids -contains $sid) -and $readOnly -and ($rule.InheritanceFlags -eq 'None')) { continue }
        $problems.Add(('the root ACL allows {0} ({1})' -f $sid, $rule.FileSystemRights))
    }

    $topLevel = @($BootTest.Kit, $BootTest.Cache, $BootTest.State, $BootTest.Logs, $BootTest.SvcOut, $BootTest.Distro,
        $BootTest.Source, $BootTest.Spike, $BootTest.F3Out, $BootTest.F4Dir)
    $toCheck = @()
    if ($Quick) {
        if ($Directory -and (Test-Path -LiteralPath $Directory)) { $toCheck = @(Get-Item -LiteralPath $Directory -Force) }
    } else {
        $toCheck = @(Get-ChildItem -LiteralPath $BootTest.Root -Force)
    }
    foreach ($top in $toCheck) {
        if (($topLevel -contains $top.FullName) -and -not ($top.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            $acl = Get-Acl -LiteralPath $top.FullName
            foreach ($rule in $acl.GetAccessRules($true, $false, $sidType)) {
                if ($rule.AccessControlType -ne 'Allow') { continue }
                $sid = $rule.IdentityReference.Value
                if (($sid -eq $BootTest.SidAdministrators) -or ($sid -eq $BootTest.SidSystem)) { continue }
                if ($svcSid -and ($sid -eq $svcSid) -and ($svcEntries -contains $top.FullName)) { continue }
                if ($f3Sid -and ($sid -eq $f3Sid) -and ($f3Entries -contains $top.FullName)) { continue }
                $problems.Add(('{0} has an unexpected access entry for {1}' -f $top.FullName, $sid))
            }
        }
    }

    # Owners and reparse points, without following any reparse point.
    $stack = New-Object System.Collections.Generic.Stack[object]
    foreach ($item in $toCheck) { $stack.Push($item) }
    while ($stack.Count -gt 0) {
        $item = $stack.Pop()
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            $problems.Add(('{0} is a reparse point (junction or link)' -f $item.FullName))
            continue
        }
        try { $itemAcl = Get-Acl -LiteralPath $item.FullName; $owner = $itemAcl.GetOwner($sidType).Value }
        catch { $problems.Add(('{0}: owner cannot be read' -f $item.FullName)); continue }
        if ($accountSids.Count -and (Test-PathInArea -Path $item.FullName -Areas $readOnlyAreas)) {
            foreach ($rule in $itemAcl.GetAccessRules($true, $true, $sidType)) {
                if (($rule.AccessControlType -eq 'Allow') -and ($accountSids -contains $rule.IdentityReference.Value) -and
                    (([int64]$rule.FileSystemRights -band $writeMask) -ne 0)) {
                    $problems.Add(('{0} gives {1} write access ({2})' -f $item.FullName, $rule.IdentityReference.Value, $rule.FileSystemRights))
                }
            }
        }
        $allowed = ($trusted -contains $owner) -or
            ($svcSid -and ($owner -eq $svcSid) -and (Test-PathInArea -Path $item.FullName -Areas $svcWritable)) -or
            ($f3Sid -and ($owner -eq $f3Sid) -and (Test-PathInArea -Path $item.FullName -Areas $f3Writable))
        if (-not $allowed) { $problems.Add(('{0} is owned by {1}' -f $item.FullName, $owner)) }
        if ($item.PSIsContainer -and -not $Quick) {
            foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force)) { $stack.Push($child) }
        }
    }
    return $problems.ToArray()
}

function Remove-PathNoFollow {
    # Deletes a file or folder tree. A reparse point (junction or link) is deleted itself; its
    # target is never entered, so a planted junction cannot redirect the delete.
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([Parameter(Mandatory = $true)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $item) { return }
    if (-not $PSCmdlet.ShouldProcess($item.FullName, 'Delete without following links')) { return }
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        if ($item.PSIsContainer) { [System.IO.Directory]::Delete($item.FullName, $false) }
        else { [System.IO.File]::Delete($item.FullName) }
        return
    }
    if ($item.PSIsContainer) {
        foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force)) { Remove-PathNoFollow -Path $child.FullName }
        [System.IO.Directory]::Delete($item.FullName, $false)
    } else {
        if ($item.Attributes -band [System.IO.FileAttributes]::ReadOnly) { $item.Attributes = [System.IO.FileAttributes]::Normal }
        [System.IO.File]::Delete($item.FullName)
    }
}

function Remove-EmptiedFolder {
    # Administrator side, for folders that slateops-svc can change: a slateops-svc job empties the
    # folder first, then this deletes only the folder itself, never recursively. A reparse point or
    # a folder that still has items stays, with a warning.
    param([Parameter(Mandatory = $true)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $item) { return }
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { [System.IO.Directory]::Delete($item.FullName, $false); return }
    if (@(Get-ChildItem -LiteralPath $item.FullName -Force).Count -gt 0) {
        Write-KitLog ('{0} is not empty; it stays. Run 90-cleanup.ps1 after slateops-svc is removed.' -f $item.FullName) 'WARN'
        return
    }
    [System.IO.Directory]::Delete($item.FullName, $false)
}

function Get-BootTestLogFile { return $script:BootTestLogFile }

function Get-UtcStamp {
    param([datetime]$Time = (Get-Date))
    return $Time.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}

function Write-KitLog {
    param(
        [Parameter(Mandatory = $true, Position = 0)][AllowEmptyString()][string]$Message,
        [Parameter(Position = 1)][ValidateSet('INFO', 'STEP', 'WHATIF', 'PASS', 'WARN', 'FAIL', 'ERROR')][string]$Level = 'INFO'
    )
    $line = '{0} [{1}] {2}' -f (Get-UtcStamp), $Level, $Message
    $color = switch ($Level) {
        'PASS'   { 'Green' }
        'WARN'   { 'Yellow' }
        'FAIL'   { 'Red' }
        'ERROR'  { 'Red' }
        'STEP'   { 'Cyan' }
        'WHATIF' { 'Magenta' }
        default  { 'Gray' }
    }
    try { Write-Host $line -ForegroundColor $color } catch { }
    if ($script:BootTestLogFile) {
        Add-Content -LiteralPath $script:BootTestLogFile -Value $line -Encoding UTF8
    }
}

function Test-DryRun { return $script:BootTestDryRun }

function Invoke-Step {
    # Runs one change. In dry-run mode it only logs what it would do.
    # The action's output is returned to the caller.
    param(
        [Parameter(Mandatory = $true, Position = 0)][string]$Description,
        [Parameter(Mandatory = $true, Position = 1)][scriptblock]$Action
    )
    if ($script:BootTestDryRun) {
        Write-KitLog ('Would: {0}' -f $Description) 'WHATIF'
        return
    }
    Write-KitLog $Description 'STEP'
    & $Action
}

# ---------------------------------------------------------------------------
# Native commands
# ---------------------------------------------------------------------------

function Invoke-Native {
    # Runs a native program and returns ExitCode and Output (string array).
    # Windows PowerShell 5.1 turns native stderr into error records, and with
    # ErrorActionPreference=Stop those stop the script. So this function lowers the
    # preference for the call and checks the exit code instead.
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [int[]]$SuccessCodes = @(0),
        [switch]$NoThrow,
        [switch]$Quiet
    )
    $null = Get-Command -Name $FilePath -CommandType Application -ErrorAction Stop
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $raw = & $FilePath @ArgumentList 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    $lines = @()
    foreach ($item in @($raw)) {
        if ($null -eq $item) { continue }
        $text = ([string]$item) -replace "`0", ''
        $text = $text.TrimEnd()
        if ($text.Length -gt 0) { $lines += $text }
    }
    if (-not $Quiet) {
        Write-KitLog ('> {0} {1}' -f (Split-Path -Leaf $FilePath), ($ArgumentList -join ' '))
        foreach ($line in $lines) { Write-KitLog ('  {0}' -f $line) }
        Write-KitLog ('  exit code {0}' -f $code)
    }
    $result = New-Object -TypeName psobject -Property @{ ExitCode = $code; Output = $lines }
    if ((-not $NoThrow) -and ($SuccessCodes -notcontains $code)) {
        throw ('{0} failed with exit code {1}.' -f (Split-Path -Leaf $FilePath), $code)
    }
    return $result
}

function Get-WslExe { return (Join-Path $env:SystemRoot 'System32\wsl.exe') }

function Invoke-Wsl {
    # Runs wsl.exe with UTF-8 output (WSL_UTF8=1), so its output can be read.
    param(
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [int[]]$SuccessCodes = @(0),
        [switch]$NoThrow,
        [switch]$Quiet
    )
    $env:WSL_UTF8 = '1'
    return Invoke-Native -FilePath (Get-WslExe) -ArgumentList $ArgumentList -SuccessCodes $SuccessCodes -NoThrow:$NoThrow -Quiet:$Quiet
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-Administrator {
    if (-not (Test-Administrator)) {
        throw 'Run this script in Windows PowerShell opened with "Run as administrator".'
    }
}

function Get-Architecture {
    # Returns AMD64 or ARM64 (the native architecture, also from a 32-bit process).
    $arch = $env:PROCESSOR_ARCHITEW6432
    if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
    return $arch.ToUpperInvariant()
}

function Get-WindowsInfo {
    $cv = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $displayVersion = $null
    if ($cv.PSObject.Properties['DisplayVersion']) { $displayVersion = $cv.DisplayVersion }
    $ubr = $null
    if ($cv.PSObject.Properties['UBR']) { $ubr = $cv.UBR }
    return New-Object -TypeName psobject -Property @{
        Caption        = $os.Caption
        EditionId      = $cv.EditionID
        DisplayVersion = $displayVersion
        Build          = [int]$cv.CurrentBuild
        Ubr            = $ubr
        LastBoot       = $os.LastBootUpTime
    }
}

function Get-WslVersion {
    # Returns the installed WSL package version, or $null when the WSL package is not installed.
    # The inbox System32\wsl.exe is only a launcher; the package installs Program Files\WSL\wsl.exe.
    $exe = Join-Path $env:ProgramFiles 'WSL\wsl.exe'
    if (-not (Test-Path -LiteralPath $exe)) { return $null }
    $info = (Get-Item -LiteralPath $exe).VersionInfo
    return New-Object -TypeName System.Version -ArgumentList $info.FileMajorPart, $info.FileMinorPart, $info.FileBuildPart, $info.FilePrivatePart
}

function ConvertTo-NetworkCidr {
    # Returns the network in CIDR form, for example 192.168.1.0/24 for 192.168.1.23 and 24.
    param([Parameter(Mandatory = $true)][string]$Address, [Parameter(Mandatory = $true)][int]$PrefixLength)
    $bytes = ([System.Net.IPAddress]::Parse($Address)).GetAddressBytes()
    [Array]::Reverse($bytes)
    $ip = [uint64][BitConverter]::ToUInt32($bytes, 0)
    $all = [uint64]4294967295
    if ($PrefixLength -le 0) { $mask = [uint64]0 } else { $mask = ($all -shl (32 - $PrefixLength)) -band $all }
    $network = [uint32]($ip -band $mask)
    $netBytes = [BitConverter]::GetBytes($network)
    [Array]::Reverse($netBytes)
    return ('{0}/{1}' -f (New-Object System.Net.IPAddress -ArgumentList (, $netBytes)).ToString(), $PrefixLength)
}

function Get-LanInfo {
    # Returns the active LAN connection (the up adapter with an IPv4 default gateway), or $null.
    $configs = @(Get-NetIPConfiguration | Where-Object {
            $_.IPv4DefaultGateway -and $_.NetAdapter -and ($_.NetAdapter.Status -eq 'Up')
        })
    if ($configs.Count -eq 0) { return $null }
    $config = $configs[0]
    $ipv4 = @($config.IPv4Address)[0]
    $connection = Get-NetConnectionProfile -InterfaceIndex $config.InterfaceIndex -ErrorAction SilentlyContinue
    $category = $null
    $networkName = $null
    if ($connection) { $category = [string]$connection.NetworkCategory; $networkName = $connection.Name }
    return New-Object -TypeName psobject -Property @{
        InterfaceAlias  = $config.InterfaceAlias
        InterfaceIndex  = $config.InterfaceIndex
        Address         = $ipv4.IPAddress
        PrefixLength    = [int]$ipv4.PrefixLength
        Cidr            = (ConvertTo-NetworkCidr -Address $ipv4.IPAddress -PrefixLength ([int]$ipv4.PrefixLength))
        Category        = $category
        NetworkName     = $networkName
        AdapterCount    = $configs.Count
    }
}

function Test-PortListening {
    param([int]$Port = $BootTest.Port)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    return ($listeners.Count -gt 0)
}

function Get-OptionalFeatureState {
    param([string]$Name = 'VirtualMachinePlatform')
    $feature = Get-WindowsOptionalFeature -Online -FeatureName $Name
    return [string]$feature.State
}

# ---------------------------------------------------------------------------
# State file (flat key/value JSON under C:\ProgramData\SlateOpsBootTest\state)
# ---------------------------------------------------------------------------

function Read-BootTestState {
    $state = @{}
    if (Test-Path -LiteralPath $BootTest.StateFile) {
        $object = Get-Content -LiteralPath $BootTest.StateFile -Raw | ConvertFrom-Json
        foreach ($property in $object.PSObject.Properties) { $state[$property.Name] = $property.Value }
    }
    return $state
}

function Save-BootTestState {
    param([Parameter(Mandatory = $true)][hashtable]$State)
    if (Test-DryRun) { return }
    if (-not (Test-Path -LiteralPath $BootTest.State)) {
        New-Item -ItemType Directory -Path $BootTest.State -Force | Out-Null
    }
    $State['updated_at'] = Get-UtcStamp
    $json = New-Object -TypeName psobject -Property $State | ConvertTo-Json -Depth 3
    Set-Content -LiteralPath $BootTest.StateFile -Value $json -Encoding ASCII
}

# ---------------------------------------------------------------------------
# Service account helpers
# ---------------------------------------------------------------------------

function Get-ServiceAccount {
    return (Get-LocalUser -Name $BootTest.AccountName -ErrorAction SilentlyContinue)
}

function Get-ServiceAccountQualifiedName {
    return ('{0}\{1}' -f $env:COMPUTERNAME, $BootTest.AccountName)
}

function Initialize-LsaRightsType {
    # Local Security Authority calls for user rights ("Log on as a batch job" and the deny rights).
    # Windows has no built-in cmdlet for them. C# 5 syntax, so Windows PowerShell 5.1 can compile it.
    if ('SlateOpsBootTest.LsaRights' -as [type]) { return }
    $source = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Principal;

namespace SlateOpsBootTest
{
    public static class LsaRights
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct LSA_UNICODE_STRING
        {
            public ushort Length;
            public ushort MaximumLength;
            public IntPtr Buffer;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct LSA_OBJECT_ATTRIBUTES
        {
            public int Length;
            public IntPtr RootDirectory;
            public IntPtr ObjectName;
            public uint Attributes;
            public IntPtr SecurityDescriptor;
            public IntPtr SecurityQualityOfService;
        }

        private const uint POLICY_VIEW_LOCAL_INFORMATION = 0x00000001;
        private const uint POLICY_CREATE_ACCOUNT = 0x00000010;
        private const uint POLICY_LOOKUP_NAMES = 0x00000800;
        private const uint STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034;

        [DllImport("advapi32.dll")]
        private static extern uint LsaOpenPolicy(IntPtr systemName, ref LSA_OBJECT_ATTRIBUTES objectAttributes, uint desiredAccess, out IntPtr policyHandle);

        [DllImport("advapi32.dll")]
        private static extern uint LsaAddAccountRights(IntPtr policyHandle, byte[] accountSid, LSA_UNICODE_STRING[] userRights, uint countOfRights);

        [DllImport("advapi32.dll")]
        private static extern uint LsaRemoveAccountRights(IntPtr policyHandle, byte[] accountSid, [MarshalAs(UnmanagedType.U1)] bool allRights, LSA_UNICODE_STRING[] userRights, uint countOfRights);

        [DllImport("advapi32.dll")]
        private static extern uint LsaEnumerateAccountRights(IntPtr policyHandle, byte[] accountSid, out IntPtr userRights, out uint countOfRights);

        [DllImport("advapi32.dll")]
        private static extern uint LsaFreeMemory(IntPtr buffer);

        [DllImport("advapi32.dll")]
        private static extern uint LsaClose(IntPtr policyHandle);

        [DllImport("advapi32.dll")]
        private static extern int LsaNtStatusToWinError(uint status);

        private static IntPtr OpenPolicy()
        {
            LSA_OBJECT_ATTRIBUTES attributes = new LSA_OBJECT_ATTRIBUTES();
            attributes.Length = Marshal.SizeOf(typeof(LSA_OBJECT_ATTRIBUTES));
            IntPtr handle;
            uint status = LsaOpenPolicy(IntPtr.Zero, ref attributes, POLICY_VIEW_LOCAL_INFORMATION | POLICY_CREATE_ACCOUNT | POLICY_LOOKUP_NAMES, out handle);
            Check(status, "LsaOpenPolicy");
            return handle;
        }

        private static void Check(uint status, string call)
        {
            if (status != 0)
            {
                throw new System.ComponentModel.Win32Exception(LsaNtStatusToWinError(status), call + " failed");
            }
        }

        private static byte[] SidBytes(string sid)
        {
            SecurityIdentifier identifier = new SecurityIdentifier(sid);
            byte[] bytes = new byte[identifier.BinaryLength];
            identifier.GetBinaryForm(bytes, 0);
            return bytes;
        }

        private static LSA_UNICODE_STRING[] ToLsaStrings(string[] rights)
        {
            LSA_UNICODE_STRING[] result = new LSA_UNICODE_STRING[rights.Length];
            for (int i = 0; i < rights.Length; i++)
            {
                result[i].Buffer = Marshal.StringToHGlobalUni(rights[i]);
                result[i].Length = (ushort)(rights[i].Length * 2);
                result[i].MaximumLength = (ushort)(rights[i].Length * 2 + 2);
            }
            return result;
        }

        private static void FreeLsaStrings(LSA_UNICODE_STRING[] strings)
        {
            for (int i = 0; i < strings.Length; i++)
            {
                if (strings[i].Buffer != IntPtr.Zero) { Marshal.FreeHGlobal(strings[i].Buffer); }
            }
        }

        public static void Add(string sid, string[] rights)
        {
            IntPtr policy = OpenPolicy();
            LSA_UNICODE_STRING[] strings = ToLsaStrings(rights);
            try { Check(LsaAddAccountRights(policy, SidBytes(sid), strings, (uint)strings.Length), "LsaAddAccountRights"); }
            finally { FreeLsaStrings(strings); LsaClose(policy); }
        }

        public static void Remove(string sid, string[] rights)
        {
            IntPtr policy = OpenPolicy();
            LSA_UNICODE_STRING[] strings = ToLsaStrings(rights);
            try
            {
                uint status = LsaRemoveAccountRights(policy, SidBytes(sid), false, strings, (uint)strings.Length);
                if (status != STATUS_OBJECT_NAME_NOT_FOUND) { Check(status, "LsaRemoveAccountRights"); }
            }
            finally { FreeLsaStrings(strings); LsaClose(policy); }
        }

        public static string[] Get(string sid)
        {
            IntPtr policy = OpenPolicy();
            try
            {
                IntPtr buffer;
                uint count;
                uint status = LsaEnumerateAccountRights(policy, SidBytes(sid), out buffer, out count);
                if (status == STATUS_OBJECT_NAME_NOT_FOUND) { return new string[0]; }
                Check(status, "LsaEnumerateAccountRights");
                List<string> rights = new List<string>();
                int size = Marshal.SizeOf(typeof(LSA_UNICODE_STRING));
                for (int i = 0; i < count; i++)
                {
                    LSA_UNICODE_STRING item = (LSA_UNICODE_STRING)Marshal.PtrToStructure(new IntPtr(buffer.ToInt64() + (long)i * size), typeof(LSA_UNICODE_STRING));
                    rights.Add(Marshal.PtrToStringUni(item.Buffer, item.Length / 2));
                }
                LsaFreeMemory(buffer);
                return rights.ToArray();
            }
            finally { LsaClose(policy); }
        }
    }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp
}

# ---------------------------------------------------------------------------
# Running a job as the service account
# ---------------------------------------------------------------------------

# Jobs that lib\svc-exec.ps1 accepts. The account that runs each job is fixed here and checked
# again in svc-exec.ps1. P1 jobs read their parameters from state.json (administrators write it).
$BootTest.SvcJobs = @('prepare', 'status', 'unregister', 'restart-vm',
    's1-install', 's1-stop-test-stack', 's1-measure-idle', 's1-backup', 's1-restore-timing', 's1-report',
    's1-port80-start', 's1-port80-stop', 's1-avahi-start', 's1-avahi-stop', 's1-remove', 's1-abort', 's1-measure-idle-boot',
    'spike-import', 'f5-drvfs', 'f3-move', 'f3-unregister', 'spike-unregister', 'f4-pipe', 'spike-clean', 'f5-clean')
$BootTest.F3Jobs = @('f3-import-in-place', 'f3-cleanup')

function Invoke-SvcJob {
    # Runs one allow-listed job as the service account (or, for -Account f3, as the throwaway
    # P1 account slateops-f3).
    # How: the admin side writes the job name and a request ID to state\request.txt (only
    # administrators can write there), starts the on-demand task \SlateOpsBootTest\Exec (or F3),
    # which runs lib\svc-exec.ps1 as that account, then polls the account's result file until a
    # result with the same request ID appears or the time limit ends. The admin side only reads
    # the account's output folder, and parses the result as data. -OnPoll runs at each poll
    # (every 5 s), for example to sample memory while a long job runs. If it returns 'abort',
    # the task is stopped and the job throws.
    param(
        [Parameter(Mandatory = $true)][string]$Job,
        [int]$TimeoutMinutes = 10,
        [ValidateSet('svc', 'f3')][string]$Account = 'svc',
        [scriptblock]$OnPoll,
        [switch]$NoThrow
    )
    if ($Account -eq 'f3') {
        $allowed = $BootTest.F3Jobs; $taskName = $BootTest.P1.F3TaskName; $outDir = $BootTest.F3Out; $accountName = $BootTest.P1.F3AccountName
    } else {
        $allowed = $BootTest.SvcJobs; $taskName = $BootTest.ExecTaskName; $outDir = $BootTest.SvcOut; $accountName = $BootTest.AccountName
    }
    if ($allowed -notcontains $Job) { throw ('Job "{0}" is not allowed for {1}.' -f $Job, $accountName) }
    $resultFile = Join-Path $outDir 'svc-exec-result.json'
    $task = Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) { throw ('The task {0}{1} does not exist. Run 10-setup.ps1 first.' -f $BootTest.TaskPath, $taskName) }
    if ($task.State -eq 'Running') { throw ('The task {0} is already running another job. Wait and try again.' -f $taskName) }

    $requestId = [guid]::NewGuid().ToString()
    Set-Content -LiteralPath $BootTest.RequestFile -Value ('{0} {1}' -f $Job, $requestId) -Encoding ASCII
    $jobLog = Join-Path $outDir ('svc-exec-{0}.log' -f $Job)
    $logLinesBefore = 0
    if (Test-Path -LiteralPath $jobLog -PathType Leaf) { $logLinesBefore = @(Get-Content -LiteralPath $jobLog).Count }
    $started = Get-Date
    Start-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $taskName
    Write-KitLog ('Started job "{0}" as {1} (request {2}). Time limit {3} min.' -f $Job, $accountName, $requestId, $TimeoutMinutes)

    $deadline = $started.AddMinutes($TimeoutMinutes)
    $result = $null
    $lastNotice = $started
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        $signal = $null
        if ($OnPoll) { try { $signal = & $OnPoll } catch { $null = $_ } }
        if (@($signal) -contains 'abort') {
            Stop-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $taskName
            # Wait until the task has left Running, so the next job (for example s1-abort) can start.
            $stopDeadline = (Get-Date).AddSeconds(30)
            while (((Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $taskName).State -eq 'Running') -and ((Get-Date) -lt $stopDeadline)) { Start-Sleep -Seconds 2 }
            throw ('Job "{0}" was stopped by its poll check.' -f $Job)
        }
        if (Test-Path -LiteralPath $resultFile) {
            try { $candidate = Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json } catch { $candidate = $null }
            if ($candidate -and ([string]$candidate.request_id -eq $requestId)) { $result = $candidate; break }
        }
        $state = (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $taskName).State
        $elapsed = ((Get-Date) - $started).TotalSeconds
        if (($state -eq 'Ready') -and ($elapsed -gt 60)) {
            $info = Get-ScheduledTaskInfo -TaskPath $BootTest.TaskPath -TaskName $taskName
            throw ('The task {0} stopped without a result (last result 0x{1:X8}). Read {2}.' -f $taskName, $info.LastTaskResult, $jobLog)
        }
        if (((Get-Date) - $lastNotice).TotalSeconds -ge 60) {
            Write-KitLog ('Job "{0}" still running ({1:N0} s). Progress: {2}' -f $Job, $elapsed, $jobLog)
            $lastNotice = Get-Date
        }
    }
    if ((Test-Path -LiteralPath $jobLog -PathType Leaf) -and -not ((Get-Item -LiteralPath $jobLog -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        Write-KitLog ('--- {0} (this run) ---' -f $jobLog)
        foreach ($line in @(Get-Content -LiteralPath $jobLog | Select-Object -Skip $logLinesBefore | Select-Object -Last 200)) { Write-KitLog ('  | {0}' -f $line) }
        Write-KitLog '--- end ---'
    }
    if (-not $result) {
        if ($NoThrow) { Write-KitLog ('Job "{0}" gave no result in {1} min.' -f $Job, $TimeoutMinutes) 'WARN'; return $null }
        throw ('Job "{0}" gave no result in {1} min. Read {2}.' -f $Job, $TimeoutMinutes, $jobLog)
    }
    if ([int]$result.exit_code -ne 0) {
        if ($NoThrow) { Write-KitLog ('Job "{0}" failed (exit code {1}).' -f $Job, $result.exit_code) 'WARN'; return $result }
        throw ('Job "{0}" failed (exit code {1}). Read {2}.' -f $Job, $result.exit_code, $jobLog)
    }
    Write-KitLog ('Job "{0}" finished.' -f $Job) 'PASS'
    return $result
}

function Get-StatusJson {
    # Reads the test web service from this PC (mirrored mode forwards 127.0.0.1 to Linux).
    param([int]$TimeoutSec = 10)
    $response = Invoke-WebRequest -Uri $BootTest.StatusUrl -UseBasicParsing -TimeoutSec $TimeoutSec
    return ($response.Content | ConvertFrom-Json)
}

# ---------------------------------------------------------------------------
# PowerShell logging policy (the service account password must not reach a log)
# ---------------------------------------------------------------------------

# Register-ScheduledTask (module ScheduledTasks) is the only command that receives the
# password as plain text. New-LocalUser and Set-LocalUser receive a SecureString.
$BootTest.PasswordModules = @('ScheduledTasks')

function Get-PowerShellLoggingPolicy {
    # Reads the Windows PowerShell 5.1 logging policies from HKLM and HKCU. Module logging
    # records command parameters, so it would record the password; script block logging and
    # transcription record script text and screen output, which never hold the password.
    $result = New-Object -TypeName psobject -Property @{
        ModuleLogging      = $false
        ModuleNames        = @()
        ScriptBlockLogging = $false
        Transcription      = $false
    }
    foreach ($hive in @('HKLM:', 'HKCU:')) {
        $base = '{0}\SOFTWARE\Policies\Microsoft\Windows\PowerShell' -f $hive
        $module = Get-ItemProperty -LiteralPath (Join-Path $base 'ModuleLogging') -ErrorAction SilentlyContinue
        if ($module -and $module.PSObject.Properties['EnableModuleLogging'] -and ($module.EnableModuleLogging -eq 1)) {
            $result.ModuleLogging = $true
            $names = Get-Item -LiteralPath (Join-Path $base 'ModuleLogging\ModuleNames') -ErrorAction SilentlyContinue
            if ($names) {
                foreach ($valueName in $names.GetValueNames()) {
                    $data = [string]$names.GetValue($valueName)
                    if ($data) { $result.ModuleNames += $data } elseif ($valueName) { $result.ModuleNames += $valueName }
                }
            }
        }
        $block = Get-ItemProperty -LiteralPath (Join-Path $base 'ScriptBlockLogging') -ErrorAction SilentlyContinue
        if ($block -and $block.PSObject.Properties['EnableScriptBlockLogging'] -and ($block.EnableScriptBlockLogging -eq 1)) { $result.ScriptBlockLogging = $true }
        $transcript = Get-ItemProperty -LiteralPath (Join-Path $base 'Transcription') -ErrorAction SilentlyContinue
        if ($transcript -and $transcript.PSObject.Properties['EnableTranscripting'] -and ($transcript.EnableTranscripting -eq 1)) { $result.Transcription = $true }
    }
    return $result
}

function Get-PasswordModuleLogged {
    # Returns the password-receiving modules that the module logging policy covers (empty = safe).
    $policy = Get-PowerShellLoggingPolicy
    $covered = @()
    if (-not $policy.ModuleLogging) { return $covered }
    foreach ($module in $BootTest.PasswordModules) {
        foreach ($pattern in $policy.ModuleNames) {
            if ($module -like $pattern) { $covered += $module; break }
        }
    }
    return $covered
}

# ---------------------------------------------------------------------------
# Passwords for the kit accounts (slateops-svc and the P1 account slateops-f3)
# ---------------------------------------------------------------------------

function ConvertTo-KitSecureString {
    # Builds a SecureString one character at a time (no ConvertTo-SecureString -AsPlainText,
    # so the plain text never passes through a logged cmdlet parameter).
    param([Parameter(Mandatory = $true)][string]$Text)
    $secure = New-Object System.Security.SecureString
    foreach ($character in $Text.ToCharArray()) { $secure.AppendChar($character) }
    $secure.MakeReadOnly()
    return $secure
}

function Get-RandomPassword {
    # 32 characters from a cryptographic random source; meets Windows complexity rules.
    $lower = 'abcdefghijkmnopqrstuvwxyz'; $upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'; $digits = '23456789'; $symbols = '-_.:+=@%'
    $all = $lower + $upper + $digits + $symbols
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    try {
        $bytes = New-Object byte[] 64
        $rng.GetBytes($bytes)
        $chars = New-Object System.Collections.Generic.List[char]
        $chars.Add($lower[$bytes[0] % $lower.Length]); $chars.Add($upper[$bytes[1] % $upper.Length])
        $chars.Add($digits[$bytes[2] % $digits.Length]); $chars.Add($symbols[$bytes[3] % $symbols.Length])
        for ($i = 4; $i -lt 32; $i++) { $chars.Add($all[$bytes[$i] % $all.Length]) }
        return (-join $chars)
    } finally { $rng.Dispose() }
}

# ---------------------------------------------------------------------------
# P1 helpers (30-p1.ps1, lib\p1-probe.ps1, 90-cleanup.ps1)
# ---------------------------------------------------------------------------

function Get-VmmemMiB {
    # Working set of the WSL VM process (vmmemWSL on current WSL, vmmem on older), in MiB.
    $processes = @(Get-Process -Name 'vmmemWSL', 'vmmem' -ErrorAction SilentlyContinue)
    if ($processes.Count -eq 0) { return $null }
    return [math]::Round((($processes | Measure-Object -Property WorkingSet64 -Sum).Sum) / 1MB, 1)
}

function Get-SignedIn {
    # Who is signed in: the console user (Win32_ComputerSystem.UserName) and explorer.exe count.
    $console = (Get-CimInstance -ClassName Win32_ComputerSystem).UserName
    $explorer = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='explorer.exe'" -ErrorAction SilentlyContinue).Count
    return [ordered]@{ console_user_present = [bool]$console; explorer_processes = $explorer }
}

function Get-P1HostsPath { return (Join-Path $env:SystemRoot 'System32\drivers\etc\hosts') }

function Remove-P1HostsEntry {
    # Removes only the lines that carry the P1 marker. Returns the number of removed lines.
    $path = Get-P1HostsPath
    if (-not (Test-Path -LiteralPath $path)) { return 0 }
    $lines = @(Get-Content -LiteralPath $path)
    $keep = @($lines | Where-Object { $_ -notlike ('*' + $BootTest.P1.HostsMarker + '*') })
    $removed = $lines.Count - $keep.Count
    if ($removed -gt 0) { Set-Content -LiteralPath $path -Value $keep -Encoding ASCII }
    return $removed
}

function Get-P1RuleName {
    # Windows Defender Firewall and Hyper-V firewall rule names that P1 creates.
    return [ordered]@{
        Windows = @($BootTest.P1.WindowsRules.Values)
        HyperV  = @($BootTest.P1.HyperVRules.Values) + @($BootTest.P1.HyperVMdnsRule)
    }
}

function Remove-KitLocalAccount {
    # Disables and deletes a kit account, its profile (by SID), its sign-in screen entry and its
    # user rights. Safe when parts are already gone.
    param([Parameter(Mandatory = $true)][string]$Name, [string]$Sid)
    $account = Get-LocalUser -Name $Name -ErrorAction SilentlyContinue
    if ($account) { $Sid = $account.SID.Value; Disable-LocalUser -Name $Name }
    $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    if (Get-ItemProperty -LiteralPath $userList -Name $Name -ErrorAction SilentlyContinue) { Remove-ItemProperty -LiteralPath $userList -Name $Name }
    if ($Sid) {
        $deadline = (Get-Date).AddMinutes(2)
        while ((Get-Date) -lt $deadline) {
            $profileObject = Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $Sid) -ErrorAction SilentlyContinue
            if (-not $profileObject) { break }
            if (-not $profileObject.Loaded) { Remove-CimInstance -InputObject $profileObject; break }
            Start-Sleep -Seconds 5
        }
        if (Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $Sid) -ErrorAction SilentlyContinue) {
            Write-KitLog ('The profile of {0} is still loaded. Restart Windows and run cleanup again.' -f $Name) 'WARN'
        }
    }
    if ($account) { Remove-LocalUser -Name $Name }
    if ($Sid) {
        Initialize-LsaRightsType
        [SlateOpsBootTest.LsaRights]::Remove($Sid, [string[]]$BootTest.AccountRights)
    }
}
