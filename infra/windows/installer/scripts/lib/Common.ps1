# Common.ps1 - names, paths, run IDs, logging and folder safety for the Slate Operations
# Windows side (plan 3.1, 4.3, 10.1). Promoted from the boot-test kit (infra/windows/boot-test,
# lib/common.ps1). Windows PowerShell 5.1. Keep this file ASCII only: Windows PowerShell 5.1
# reads a file without a byte order mark as ANSI.

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------------------
# Names and fixed values
# ---------------------------------------------------------------------------

$SlateOps = @{
    AccountName      = 'slateops-svc'
    DistroName       = 'SlateOps'
    TaskPath         = '\SlateOps\'
    TaskFolder       = 'SlateOps'
    StartTaskName    = 'Start'
    ExecTaskName     = 'Exec'
    EnginePath       = '/usr/local/bin/slateops-engine'
    KeepAlivePath    = '/bin/sleep'
    FirewallRuleName = 'SlateOps-TCP-443-80'
    HyperVRuleName   = 'SlateOps-HyperV-TCP-443-80'
    FirewallGroup    = 'Slate Operations'
    Ports            = @(443, 80)
    # The VM creator ID of WSL, from the WSL networking documentation (kit value).
    WslVmCreatorId   = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'
    # Mirrored networking needs Windows 11 22H2 (build 22621) or later.
    MinBuild         = 22621
    # [general] instanceIdleTimeout needs WSL 2.5.4 or later (kit value).
    MinWslVersion    = [version]'2.5.4'
    # .wslconfig memory (plan 10.2 planning value; the kit's value).
    WslMemoryGB      = 6
    HostsMarker      = '# Slate Operations'
    SidAdministrators = 'S-1-5-32-544'
    SidSystem         = 'S-1-5-18'
    SidUsers          = 'S-1-5-32-545'
    BatchRight        = 'SeBatchLogonRight'
    DenyRights        = @('SeDenyInteractiveLogonRight', 'SeDenyRemoteInteractiveLogonRight', 'SeDenyNetworkLogonRight')
    # Register-ScheduledTask (module ScheduledTasks) is the only command that receives the
    # service account password as plain text (kit finding).
    PasswordModules   = @('ScheduledTasks')
    # Run kinds of the engine (packaging/engine/core.py RUN_KINDS).
    RunKinds          = @('install', 'update', 'uninstall', 'maintenance', 'report', 'boot', 'backup', 'package-night', 'renewal')
    # Log folders per kind (plan 10.1 item 4). The service account writes only start and exec.
    LogKinds          = @('setup', 'uninstall', 'maintenance', 'start', 'exec')
    LogKeepRuns       = 20
    LogFolderBytes    = 50MB
    StreamCapBytes    = 1MB
}
$SlateOps.AccountRights = @($SlateOps.BatchRight) + $SlateOps.DenyRights
$SlateOps.SidTrustedInstaller = 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'
$SlateOps.SidCreatorOwner = 'S-1-3-0'

# Folder paths come from the Windows known-folder calls, not from environment values that the
# caller's process can change (S91-6).
$SlateOpsPaths = @{
    ProgramData  = [Environment]::GetFolderPath('CommonApplicationData')
    Windows      = [Environment]::GetFolderPath('Windows')
    System32     = [Environment]::SystemDirectory
    ProgramFiles = [Environment]::GetFolderPath('ProgramFiles')
}

# Run ID: <kind>-<UTC time>-<6 random characters> (plan 10.1 item 1; engine core.py RUN_ID).
$SlateOps.RunIdPattern = '^(install|update|uninstall|maintenance|report|boot|backup|package-night|renewal)-[0-9]{8}T[0-9]{6}Z-[a-z0-9]{6}$'
# Release version (engine core.py VERSION).
$SlateOps.VersionPattern = '^(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})(-rc\.[1-9][0-9]{0,3})?$'

# ---------------------------------------------------------------------------
# Layout: the state tree (C:\ProgramData\SlateOps) and the data tree (<data folder>\SlateOps)
# ---------------------------------------------------------------------------
# Access kinds for the service account: none, read (RX, inherited), modify (M, inherited).

function New-SlateOpsLayout {
    param(
        [string]$StateRoot = (Join-Path $SlateOpsPaths.ProgramData 'SlateOps'),
        [string]$DataRoot = ''
    )
    $state = $StateRoot.TrimEnd('\')
    $layout = @{
        StateRoot   = $state
        Scripts     = Join-Path $state 'scripts'
        State       = Join-Path $state 'state'
        Requests    = Join-Path $state 'requests'
        SvcOut      = Join-Path $state 'svc-out'
        Logs        = Join-Path $state 'logs'
        DataRoot    = ''
        Distro      = ''
        Payload     = ''
    }
    $layout.StateFile    = Join-Path $layout.State 'install.json'
    $layout.ProgressFile = Join-Path $layout.State 'progress.json'
    $layout.RequestFile  = Join-Path $layout.Requests 'request.json'
    $layout.InputFile    = Join-Path $layout.Requests 'input.json'
    $layout.ResultFile   = Join-Path $layout.SvcOut 'exec-result.json'
    $layout.StateTree = @{
        Root    = $state
        Entries = [ordered]@{
            'scripts'          = 'read'
            'state'            = 'read'
            'requests'         = 'read'
            'svc-out'          = 'modify'
            'logs'             = 'none'
            'logs\setup'       = 'none'
            'logs\uninstall'   = 'none'
            'logs\maintenance' = 'none'
            'logs\start'       = 'modify'
            'logs\exec'        = 'modify'
        }
    }
    if ($DataRoot) { Set-LayoutDataRoot -Layout $layout -DataRoot $DataRoot }
    return $layout
}

function Set-LayoutDataRoot {
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$DataRoot)
    $root = $DataRoot.TrimEnd('\')
    $Layout.DataRoot = $root
    $Layout.Distro = Join-Path $root 'distro'
    $Layout.Payload = Join-Path $root 'payload'
    $Layout.DataTree = @{
        Root    = $root
        Entries = [ordered]@{
            'distro'  = 'modify'
            'payload' = 'read'
        }
    }
}

# ---------------------------------------------------------------------------
# Run ID
# ---------------------------------------------------------------------------

function New-RunId {
    param(
        [Parameter(Mandatory = $true)][string]$Kind,
        [datetime]$Time = (Get-Date)
    )
    if ($SlateOps.RunKinds -notcontains $Kind) { throw ('Unknown run kind {0}.' -f $Kind) }
    $alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789'
    $bytes = New-Object byte[] 6
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $suffix = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
    return ('{0}-{1}-{2}' -f $Kind, (Format-UtcTime -Time $Time -Format 'yyyyMMddTHHmmssZ'), $suffix)
}

function Test-RunId {
    param([AllowNull()][object]$Value)
    return (($Value -is [string]) -and ($Value -cmatch $SlateOps.RunIdPattern))
}

function Test-ReleaseVersion {
    param([AllowNull()][object]$Value)
    return (($Value -is [string]) -and ($Value -cmatch $SlateOps.VersionPattern))
}

function Format-UtcTime {
    # UTC time in a fixed format with the invariant culture (P2-1): the current culture can use
    # another calendar (th-TH: year 2569) or another time separator.
    param([datetime]$Time = (Get-Date), [Parameter(Mandatory = $true)][string]$Format)
    return $Time.ToUniversalTime().ToString($Format, [System.Globalization.CultureInfo]::InvariantCulture)
}

function Get-UtcStamp {
    param([datetime]$Time = (Get-Date))
    return (Format-UtcTime -Time $Time -Format 'yyyy-MM-ddTHH:mm:ssZ')
}

# ---------------------------------------------------------------------------
# Secret masking (plan 3.2 check 3, 10.1 item 3 and 7, 10.6 item 3)
# ---------------------------------------------------------------------------

$script:LogSecrets = New-Object System.Collections.Generic.List[string]

function Register-LogSecret {
    # Adds a value that no log line may hold. Values shorter than 4 characters are refused:
    # masking them would hide ordinary text and still not protect them.
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    if ($Value.Length -lt 4) { throw 'A registered secret must have at least 4 characters.' }
    if (-not $script:LogSecrets.Contains($Value)) { $script:LogSecrets.Add($Value) }
}

function Clear-LogSecret { $script:LogSecrets.Clear() }

function Protect-LogText {
    # Replaces every registered secret value, then the secret patterns of plan 10.6 item 3.
    param([AllowNull()][AllowEmptyString()][string]$Text)
    if ($null -eq $Text -or $Text.Length -eq 0) { return $Text }
    $out = $Text
    # Longest first, so a secret that contains another is replaced whole.
    foreach ($secret in @($script:LogSecrets | Sort-Object -Property Length -Descending)) {
        $out = $out.Replace($secret, '[secret]')
    }
    $out = [regex]::Replace($out, '-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z0-9 ]*PRIVATE KEY-----|$)', '[private key]')
    # Every pattern starts at a fixed left boundary and bounds its name parts, so a long line
    # (a base64 blob) costs linear time: an unanchored "[a-z]*" before "://" re-scans the rest
    # of the line from each position.
    # A connection string with a password: scheme://user:password@host
    # IgnoreCase with CultureInvariant (P3-9): a culture such as tr-TR folds "i" differently.
    $options = [System.Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
    $out = [regex]::Replace($out, '(?<![a-z0-9+.-])([a-z][a-z0-9+.-]{0,31}://[^\s:/@]{1,256}:)[^\s@/]{1,256}@', '$1[secret]@', $options)
    # KEY=value or "key": "value" lines of secret names (W8: PASS, as in the engine's SMTP_PASS).
    $out = [regex]::Replace($out, '(?<![A-Z0-9_])([A-Z0-9_]{0,64}(PASSWORD|PASSWD|PASS|SECRET|TOKEN|PRIVATE_KEY|API_KEY|_KEY)[A-Z0-9_]{0,64})(\s*[=:]\s*)("[^"]*"|''[^'']*''|\S+)', '$1$3[secret]', $options)
    $out = [regex]::Replace($out, '("[a-z0-9_]{0,64}(password|passwd|pass|secret|token|key)[a-z0-9_]{0,64}"\s*:\s*)"[^"]*"', '$1"[secret]"', $options)
    # Bearer tokens.
    $out = [regex]::Replace($out, '\b(bearer\s+)[a-z0-9._~+/=-]{8,}', '$1[secret]', $options)
    # BitLocker recovery password: eight groups of six digits.
    $out = [regex]::Replace($out, '\b[0-9]{6}(-[0-9]{6}){7}\b', '[recovery password]')
    return $out
}

# ---------------------------------------------------------------------------
# Logging (plan 10.1): <UTC time> <run ID> <step ID> <LEVEL> <message>
# ---------------------------------------------------------------------------

$script:Log = @{ File = $null; RunId = ''; Kind = ''; Console = $true; StepDir = $null }

function Start-RunLog {
    # Starts the log of one run. Directory must exist; Open-LogDirectory creates it safely.
    param(
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$Directory,
        [switch]$Append,
        [string]$Name = '',
        [switch]$NoConsole
    )
    if (-not (Test-RunId $RunId)) { throw 'The run ID does not match the run ID format.' }
    if (-not $Name) { $Name = $RunId }
    $script:Log.RunId = $RunId
    $script:Log.File = Join-Path $Directory ('{0}.log' -f $Name)
    $script:Log.StepDir = Join-Path $Directory $Name
    $script:Log.Console = -not [bool]$NoConsole
    if ((-not $Append) -and (Test-Path -LiteralPath $script:Log.File)) { throw ('The log file {0} exists already.' -f $script:Log.File) }
}

function Get-RunLogFile { return $script:Log.File }

function Format-LogLine {
    param(
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$Step,
        [Parameter(Mandatory = $true)][string]$Level,
        [AllowEmptyString()][string]$Message,
        [datetime]$Time = (Get-Date)
    )
    $clean = (Protect-LogText $Message) -replace "[`r`n]+", ' | '
    return ('{0} {1} {2} {3} {4}' -f (Get-UtcStamp -Time $Time), $RunId, $Step, $Level, $clean)
}

function Write-RunLog {
    param(
        [Parameter(Mandatory = $true, Position = 0)][string]$Step,
        [Parameter(Mandatory = $true, Position = 1)][ValidateSet('INFO', 'WARN', 'ERROR', 'PASS', 'FAIL')][string]$Level,
        [Parameter(Position = 2)][AllowEmptyString()][string]$Message = ''
    )
    $runId = $script:Log.RunId
    if (-not $runId) { $runId = '-' }
    $line = Format-LogLine -RunId $runId -Step $Step -Level $Level -Message $Message
    if ($script:Log.Console) { try { [Console]::Error.WriteLine($line) } catch { $null = $_ } }
    if ($script:Log.File) { [System.IO.File]::AppendAllText($script:Log.File, $line + "`r`n", (New-Object System.Text.UTF8Encoding($false))) }
}

function Write-CappedFile {
    # Writes text (masked) to a file, cut to the cap. Returns the number of bytes kept.
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [AllowEmptyString()][string]$Text,
        [long]$CapBytes = $SlateOps.StreamCapBytes
    )
    $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes((Protect-LogText $Text))
    $count = [long][math]::Min([long]$bytes.Length, $CapBytes)
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try { $stream.Write($bytes, 0, [int]$count) } finally { $stream.Dispose() }
    return $count
}

function Invoke-Logged {
    # Runs a native program, logs its arguments (masked), exit code and duration, and saves its
    # output to one file per step, capped at 1 MB (plan 10.1 item 3). Returns ExitCode and Output.
    # Windows PowerShell 5.1 turns native stderr into error records; the preference is lowered
    # for the call and the exit code decides (kit Invoke-Native).
    param(
        [Parameter(Mandatory = $true)][string]$Step,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [int[]]$SuccessCodes = @(0),
        [switch]$NoThrow
    )
    $null = Get-Command -Name $FilePath -CommandType Application -ErrorAction Stop
    $leaf = Split-Path -Leaf $FilePath
    Write-RunLog $Step 'INFO' ('> {0} {1}' -f $leaf, ($ArgumentList -join ' '))
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $raw = & $FilePath @ArgumentList 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
        $watch.Stop()
    }
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($item in @($raw)) {
        if ($null -eq $item) { continue }
        $text = (([string]$item) -replace "`0", '').TrimEnd()
        if ($text.Length -gt 0) { $lines.Add($text) }
    }
    Write-RunLog $Step 'INFO' ('  exit code {0}, {1} ms, {2} output lines' -f $code, $watch.ElapsedMilliseconds, $lines.Count)
    Save-StepOutput -Step $Step -Text ($lines -join "`r`n")
    $result = New-Object -TypeName psobject -Property @{ ExitCode = $code; Output = $lines.ToArray(); DurationMs = $watch.ElapsedMilliseconds }
    if ((-not $NoThrow) -and ($SuccessCodes -notcontains $code)) {
        throw ('{0} failed with exit code {1}.' -f $leaf, $code)
    }
    return $result
}

function Save-StepOutput {
    param([Parameter(Mandatory = $true)][string]$Step, [AllowEmptyString()][string]$Text)
    if ((-not $script:Log.StepDir) -or (-not $Text)) { return }
    if (-not (Test-Path -LiteralPath $script:Log.StepDir)) { New-Item -ItemType Directory -Path $script:Log.StepDir | Out-Null }
    $safe = $Step -replace '[^A-Za-z0-9._-]', '_'
    $index = 1
    do {
        $path = Join-Path $script:Log.StepDir ('{0}.{1}.out.txt' -f $safe, $index)
        $index++
    } while (Test-Path -LiteralPath $path)
    $null = Write-CappedFile -Path $path -Text $Text
}

function Get-LogRunNames {
    # The runs in one log folder: each run is <name>.log plus an optional <name> step folder.
    param([Parameter(Mandatory = $true)][string]$Directory)
    $names = @{}
    foreach ($item in @(Get-ChildItem -LiteralPath $Directory -Force -ErrorAction SilentlyContinue)) {
        $name = $item.Name
        if (-not $item.PSIsContainer) { $name = [System.IO.Path]::GetFileNameWithoutExtension($item.Name) }
        $names[$name] = $true
    }
    return @($names.Keys)
}

function Invoke-LogRotation {
    # Keeps the newest 20 runs and at most 50 MB in one log folder (plan 10.1 item 5). Runs of
    # the kind "install" are never removed: the install log stays. Names start with the run ID,
    # whose UTC time sorts the runs. Deletes never follow a link.
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [int]$KeepRuns = $SlateOps.LogKeepRuns,
        [long]$MaxBytes = $SlateOps.LogFolderBytes
    )
    if (-not (Test-Path -LiteralPath $Directory)) { return @() }
    $runs = @(Get-LogRunNames -Directory $Directory | Sort-Object { [regex]::Match($_, '[0-9]{8}T[0-9]{6}Z').Value } -Descending)
    $removed = New-Object System.Collections.Generic.List[string]
    $kept = 0
    $bytes = [long]0
    foreach ($name in $runs) {
        $items = @(Get-ChildItem -LiteralPath $Directory -Force | Where-Object { ($_.Name -eq $name) -or ($_.Name -like ($name + '.*')) })
        $size = [long]0
        foreach ($item in $items) {
            if ($item.PSIsContainer) {
                foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Recurse -Force -File -ErrorAction SilentlyContinue)) { $size += $child.Length }
            } else { $size += $item.Length }
        }
        $protected = $name.StartsWith('install-')
        if ($protected -or (($kept -lt $KeepRuns) -and (($bytes + $size) -le $MaxBytes))) {
            $kept++
            $bytes += $size
            continue
        }
        foreach ($item in $items) { Remove-PathNoFollow -Path $item.FullName }
        $removed.Add($name)
    }
    return $removed.ToArray()
}

# ---------------------------------------------------------------------------
# Folder creation and the safety check (kit lib/common.ps1, plan W7-5, spec 4.1, W80-5)
# ---------------------------------------------------------------------------
# C:\ProgramData lets every user create folders, and a data drive can too. A folder that another
# user created first, or a junction planted inside it, could make setup run a swapped script or
# write through a link with administrator rights. So each root is created in one call with a
# protected Administrators and SYSTEM access list, and setup refuses a tree with an unexpected
# owner, access entry or reparse point. Deletes never follow reparse points.

function Get-ProtectedDirectorySecurity {
    $security = New-Object System.Security.AccessControl.DirectorySecurity
    $security.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($SlateOps.SidAdministrators, $SlateOps.SidSystem)) {
        $identity = New-Object System.Security.Principal.SecurityIdentifier($sid)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
        $security.AddAccessRule($rule)
    }
    return $security
}

function Get-ServiceAccessRule {
    param([Parameter(Mandatory = $true)][string]$Sid, [Parameter(Mandatory = $true)][ValidateSet('read', 'modify', 'root')][string]$Access)
    $identity = New-Object System.Security.Principal.SecurityIdentifier($Sid)
    switch ($Access) {
        'read'   { return New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'ReadAndExecute', 'ContainerInherit, ObjectInherit', 'None', 'Allow') }
        'modify' { return New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'Modify', 'ContainerInherit, ObjectInherit', 'None', 'Allow') }
        'root'   { return New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'ReadAndExecute', 'None', 'None', 'Allow') }
    }
}

function Initialize-ProtectedTree {
    # Creates the root (protected ACL set in the creating call) and every missing entry folder,
    # then runs the full safety check. Returns the problems (empty = safe). Creates nothing in a
    # tree that fails the check. An existing folder's access list is never changed here (S91-5):
    # with -ServiceSid, a folder that this call creates gets the service account's entry in the
    # same creating call; folders that exist before the account get it once, from
    # Grant-ServiceAccess in the step that created the account.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Tree,
        [string]$ServiceSid = ''
    )
    if (Test-Path -LiteralPath $Tree.Root) {
        $problems = @(Get-TreeProblem -Tree $Tree -ServiceSid $ServiceSid)
        if ($problems.Count -gt 0) { return $problems }
    } else {
        $parent = Split-Path -Parent $Tree.Root
        if (-not (Test-Path -LiteralPath $parent)) { throw ('The parent folder {0} does not exist.' -f $parent) }
        $security = Get-ProtectedDirectorySecurity
        if ($ServiceSid) { $security.AddAccessRule((Get-ServiceAccessRule -Sid $ServiceSid -Access 'root')) }
        [void][System.IO.Directory]::CreateDirectory($Tree.Root, $security)
        # Checked again after the create: another user could have created the root between the
        # test and the call; then CreateDirectory keeps that folder unchanged.
        $problems = @(Get-TreeProblem -Tree $Tree -ServiceSid $ServiceSid)
        if ($problems.Count -gt 0) { return $problems }
    }
    foreach ($entry in $Tree.Entries.Keys) {
        $path = Join-Path $Tree.Root $entry
        if (Test-Path -LiteralPath $path) { continue }
        $access = $Tree.Entries[$entry]
        # Created plainly, so it inherits Administrators and SYSTEM from the protected root; a
        # given service account gets its entry in this same, creating call.
        [void][System.IO.Directory]::CreateDirectory($path)
        if ($ServiceSid -and ($access -ne 'none')) {
            $acl = Get-Acl -LiteralPath $path
            $acl.AddAccessRule((Get-ServiceAccessRule -Sid $ServiceSid -Access $access))
            Set-Acl -LiteralPath $path -AclObject $acl
        }
    }
    return @(Get-TreeProblem -Tree $Tree -ServiceSid $ServiceSid)
}

function Grant-ServiceAccess {
    # Gives the service account its entries in a tree, once: the step that creates the account
    # calls it right after the creation (S91-5). A folder that already has an entry for the SID
    # is left as it is. The tree must pass the full check first.
    param([Parameter(Mandatory = $true)][hashtable]$Tree, [Parameter(Mandatory = $true)][string]$ServiceSid)
    $problems = @(Get-TreeProblem -Tree $Tree -ServiceSid $ServiceSid)
    if ($problems.Count -gt 0) { return $problems }
    $sidType = [System.Security.Principal.SecurityIdentifier]
    $targets = @(@{ path = $Tree.Root; access = 'root' })
    foreach ($entry in $Tree.Entries.Keys) {
        if ($Tree.Entries[$entry] -ne 'none') { $targets += @{ path = (Join-Path $Tree.Root $entry); access = $Tree.Entries[$entry] } }
    }
    foreach ($target in $targets) {
        if (-not (Test-Path -LiteralPath $target.path)) { continue }
        $acl = Get-Acl -LiteralPath $target.path
        $has = @($acl.GetAccessRules($true, $false, $sidType) | Where-Object { $_.IdentityReference.Value -eq $ServiceSid }).Count -gt 0
        if ($has) { continue }
        $acl.AddAccessRule((Get-ServiceAccessRule -Sid $ServiceSid -Access $target.access))
        Set-Acl -LiteralPath $target.path -AclObject $acl
    }
    return @(Get-TreeProblem -Tree $Tree -ServiceSid $ServiceSid)
}

function Remove-ServiceAccess {
    # Removes every explicit entry of a deleted or replaced account from a tree (P2-3), so the
    # next check of the tree does not see an unknown SID.
    param([Parameter(Mandatory = $true)][hashtable]$Tree, [Parameter(Mandatory = $true)][string]$Sid)
    if (-not (Test-Path -LiteralPath $Tree.Root)) { return }
    $identity = New-Object System.Security.Principal.SecurityIdentifier($Sid)
    $paths = @($Tree.Root) + @($Tree.Entries.Keys | ForEach-Object { Join-Path $Tree.Root $_ })
    foreach ($path in $paths) {
        $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        if ((-not $item) -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { continue }
        $acl = Get-Acl -LiteralPath $path
        $acl.PurgeAccessRules($identity)
        Set-Acl -LiteralPath $path -AclObject $acl
    }
}

function Test-TreeRootTrusted {
    # The root alone: it exists, is not a reparse point, is protected and has a trusted owner.
    # Setup reads nothing from a state folder that fails this (spec 4.1).
    param([Parameter(Mandatory = $true)][hashtable]$Tree)
    $item = Get-Item -LiteralPath $Tree.Root -Force -ErrorAction SilentlyContinue
    if ((-not $item) -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { return $false }
    $acl = Get-Acl -LiteralPath $Tree.Root
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
    return (($SlateOps.SidAdministrators, $SlateOps.SidSystem, $currentUser) -contains $owner) -and $acl.AreAccessRulesProtected
}

function Get-RecordedServiceSid {
    # The service account SID from the administrator-only record state\windows-changes.json
    # (P2-3): it stays known after a partial service step or after the account is removed.
    # Read only when the state root itself is trusted.
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    if (-not (Test-TreeRootTrusted -Tree $Layout.StateTree)) { return '' }
    $path = Join-Path $Layout.State 'windows-changes.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return '' }
    try { $value = Read-JsonFile -Path $path } catch { return '' }
    $sid = [string](Get-DictValue $value 'account_sid')
    if ($sid -cmatch '^S-1-5-21-[0-9]{1,10}-[0-9]{1,10}-[0-9]{1,10}-[0-9]{1,10}$') { return $sid }
    return ''
}

function Assert-TreeWritable {
    # Quick check of one folder right before an action writes into it (S91-4).
    param([Parameter(Mandatory = $true)][hashtable]$Tree, [Parameter(Mandatory = $true)][string]$Directory, [string]$ServiceSid = '')
    $problems = @(Get-TreeProblem -Tree $Tree -ServiceSid $ServiceSid -Quick -Directory $Directory)
    if (-not (Test-Path -LiteralPath $Directory)) { $problems += 'missing' }
    if ($problems.Count -gt 0) {
        foreach ($problem in $problems) { Write-RunLog 'setup.write_check' 'FAIL' $problem }
        throw 'state_unsafe'
    }
}

function Get-FolderParentProblem {
    # S91-2: every folder above Path must keep it in place. A folder above is refused when it is
    # a reparse point, when its owner is not Administrators, SYSTEM or TrustedInstaller, or when
    # another principal has Delete, DeleteSubdirectoriesAndFiles, ChangePermissions or
    # TakeOwnership on it (an entry that applies to the folder itself; inherit-only entries do
    # not). A drive root cannot be deleted or renamed, so its Delete right does not count.
    # Returns problems "<reason>:<path>[:<sid>]"; empty when the folders above are safe.
    param([Parameter(Mandatory = $true)][string]$Path)
    $problems = New-Object System.Collections.Generic.List[string]
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $root = [System.IO.Path]::GetPathRoot($full)
    $trusted = @($SlateOps.SidAdministrators, $SlateOps.SidSystem, $SlateOps.SidTrustedInstaller)
    $ancestors = @($root)
    $current = $root.TrimEnd('\')
    $parts = @($full.Substring($root.Length).Split('\') | Where-Object { $_ })
    for ($i = 0; $i -lt ($parts.Count - 1); $i++) {
        $current = '{0}\{1}' -f $current, $parts[$i]
        $ancestors += $current
    }
    $rights = [System.Security.AccessControl.FileSystemRights]
    $sidType = [System.Security.Principal.SecurityIdentifier]
    foreach ($ancestor in $ancestors) {
        $item = Get-Item -LiteralPath $ancestor -Force -ErrorAction SilentlyContinue
        if (-not $item) { $problems.Add(('missing:{0}' -f $ancestor)); continue }
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { $problems.Add(('reparse_point:{0}' -f $ancestor)); continue }
        try { $acl = Get-Acl -LiteralPath $ancestor } catch { $problems.Add(('acl_unreadable:{0}' -f $ancestor)); continue }
        $owner = $acl.GetOwner($sidType).Value
        if ($trusted -notcontains $owner) { $problems.Add(('owner:{0}:{1}' -f $ancestor, $owner)) }
        $dangerous = [long]$rights::DeleteSubdirectoriesAndFiles -bor [long]$rights::ChangePermissions -bor [long]$rights::TakeOwnership -bor [long]0x10000000
        if ($ancestor -ne $root) { $dangerous = $dangerous -bor [long]$rights::Delete }
        foreach ($rule in $acl.GetAccessRules($true, $true, $sidType)) {
            if ($rule.AccessControlType -ne 'Allow') { continue }
            if (($rule.PropagationFlags -band [System.Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) { continue }
            $sid = $rule.IdentityReference.Value
            if (($trusted -contains $sid) -or ($sid -eq $SlateOps.SidCreatorOwner)) { continue }
            if (([long]$rule.FileSystemRights -band $dangerous) -ne 0) { $problems.Add(('rights:{0}:{1}' -f $ancestor, $sid)) }
        }
    }
    return $problems.ToArray()
}

function Test-ServiceWritablePath {
    param([Parameter(Mandatory = $true)][hashtable]$Tree, [Parameter(Mandatory = $true)][string]$Path)
    foreach ($entry in $Tree.Entries.Keys) {
        if ($Tree.Entries[$entry] -ne 'modify') { continue }
        $area = Join-Path $Tree.Root $entry
        if (($Path -ieq $area) -or $Path.StartsWith($area + '\', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function Test-RuleReadOnly {
    param([Parameter(Mandatory = $true)]$Rule)
    $rights = [System.Security.AccessControl.FileSystemRights]
    return ((($Rule.FileSystemRights -band $rights::Write) -eq 0) -and
        (($Rule.FileSystemRights -band $rights::Delete) -eq 0) -and
        (($Rule.FileSystemRights -band $rights::DeleteSubdirectoriesAndFiles) -eq 0) -and
        (($Rule.FileSystemRights -band $rights::ChangePermissions) -eq 0) -and
        (($Rule.FileSystemRights -band $rights::TakeOwnership) -eq 0))
}

function Get-TreeProblem {
    # Returns the problems of a tree (empty when safe). Kit rules, per tree:
    # - the root is a reparse point, or is owned by someone other than Administrators, SYSTEM or
    #   the current administrator (spec 4.1: refuse a folder that a non-administrator owns);
    # - the root inherits entries, or allows anyone other than Administrators, SYSTEM and the
    #   service account (read, this folder only);
    # - an entry folder has an explicit allow entry other than the expected ones;
    # - an item below the root is a reparse point or has another owner (the service account may
    #   own items only in its modify entries).
    # -Quick checks the root and -Directory only (before a log write).
    param(
        [Parameter(Mandatory = $true)][hashtable]$Tree,
        [string]$ServiceSid = '',
        [switch]$Quick,
        [string]$Directory = ''
    )
    $problems = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $Tree.Root)) { return $problems.ToArray() }
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $trusted = @($SlateOps.SidAdministrators, $SlateOps.SidSystem, $currentUser)
    $sidType = [System.Security.Principal.SecurityIdentifier]

    $rootItem = Get-Item -LiteralPath $Tree.Root -Force
    if ($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { $problems.Add('root_reparse_point'); return $problems.ToArray() }
    $rootAcl = Get-Acl -LiteralPath $Tree.Root
    $rootOwner = $rootAcl.GetOwner($sidType).Value
    if ($trusted -notcontains $rootOwner) { $problems.Add(('root_owner:{0}' -f $rootOwner)) }
    if (-not $rootAcl.AreAccessRulesProtected) { $problems.Add('root_inherits') }
    foreach ($rule in $rootAcl.GetAccessRules($true, $true, $sidType)) {
        if ($rule.AccessControlType -ne 'Allow') { continue }
        $sid = $rule.IdentityReference.Value
        if (($sid -eq $SlateOps.SidAdministrators) -or ($sid -eq $SlateOps.SidSystem)) { continue }
        if ($ServiceSid -and ($sid -eq $ServiceSid) -and (Test-RuleReadOnly $rule) -and ($rule.InheritanceFlags -eq 'None')) { continue }
        $problems.Add(('root_access:{0}' -f $sid))
    }

    $toCheck = @()
    if ($Quick) {
        if ($Directory -and (Test-Path -LiteralPath $Directory)) { $toCheck = @(Get-Item -LiteralPath $Directory -Force) }
    } else {
        $toCheck = @(Get-ChildItem -LiteralPath $Tree.Root -Force)
    }
    $expected = @{}
    foreach ($entry in $Tree.Entries.Keys) { $expected[(Join-Path $Tree.Root $entry).ToLowerInvariant()] = $Tree.Entries[$entry] }

    $stack = New-Object System.Collections.Generic.Stack[object]
    foreach ($item in $toCheck) { $stack.Push($item) }
    while ($stack.Count -gt 0) {
        $item = $stack.Pop()
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            $problems.Add(('reparse_point:{0}' -f $item.FullName))
            continue
        }
        try { $acl = Get-Acl -LiteralPath $item.FullName } catch { $problems.Add(('owner_unreadable:{0}' -f $item.FullName)); continue }
        $owner = $acl.GetOwner($sidType).Value
        $allowed = ($trusted -contains $owner) -or ($ServiceSid -and ($owner -eq $ServiceSid) -and (Test-ServiceWritablePath -Tree $Tree -Path $item.FullName))
        if (-not $allowed) { $problems.Add(('owner:{0}:{1}' -f $item.FullName, $owner)) }
        $key = $item.FullName.ToLowerInvariant()
        if ($expected.ContainsKey($key)) {
            foreach ($rule in $acl.GetAccessRules($true, $false, $sidType)) {
                if ($rule.AccessControlType -ne 'Allow') { continue }
                $sid = $rule.IdentityReference.Value
                if (($sid -eq $SlateOps.SidAdministrators) -or ($sid -eq $SlateOps.SidSystem)) { continue }
                if ($ServiceSid -and ($sid -eq $ServiceSid)) {
                    $kind = $expected[$key]
                    if (($kind -eq 'read') -and (Test-RuleReadOnly $rule)) { continue }
                    if ($kind -eq 'modify') { continue }
                }
                $problems.Add(('access:{0}:{1}' -f $item.FullName, $sid))
            }
        }
        if ($item.PSIsContainer -and -not $Quick) {
            foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force)) { $stack.Push($child) }
        }
    }
    return $problems.ToArray()
}

# ---------------------------------------------------------------------------
# W14-D5: the helper's progress lines (spec 7.6 helper keys)
# ---------------------------------------------------------------------------

$script:SlateOpsHelperProgress = ''

function Set-HelperProgressFile {
    # The helper writes its progress lines beside its result file (<OutFile>.progress), so the
    # setup program shows the step that runs. An empty path writes nothing.
    param([AllowEmptyString()][string]$Path)
    $script:SlateOpsHelperProgress = $Path
    if ($Path -and (Test-Path -LiteralPath $Path)) { [System.IO.File]::Delete($Path) }
}

function Write-HelperProgress {
    # One line when a step starts, in the engine's format: "progress <job> <n>/<total> <key>
    # start" (ASCII, no value, no path). A failed write never fails the step.
    param(
        [Parameter(Mandatory = $true)][string]$Job,
        [Parameter(Mandatory = $true)][int]$Number,
        [Parameter(Mandatory = $true)][int]$Total,
        [Parameter(Mandatory = $true)][string]$Key
    )
    if (-not $script:SlateOpsHelperProgress) { return }
    $line = 'progress {0} {1}/{2} {3} start' -f $Job, $Number, $Total, $Key
    try {
        $stream = [System.IO.File]::Open($script:SlateOpsHelperProgress, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
        try {
            $bytes = [System.Text.Encoding]::ASCII.GetBytes($line + "`n")
            $stream.Write($bytes, 0, $bytes.Length)
        } finally { $stream.Dispose() }
    } catch { $null = $_ }
}

function Remove-PathNoFollow {
    # Deletes a file or folder tree. A reparse point is deleted itself; its target is never entered.
    param([Parameter(Mandatory = $true)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $item) { return }
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

function Open-LogDirectory {
    # Returns the log folder of a kind under the state tree, or $null when the tree fails the
    # quick safety check (the caller then logs to its own temporary folder).
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$Kind, [string]$ServiceSid = '')
    if ($SlateOps.LogKinds -notcontains $Kind) { throw ('Unknown log kind {0}.' -f $Kind) }
    $directory = Join-Path $Layout.Logs $Kind
    if (-not (Test-Path -LiteralPath $directory)) { return $null }
    $problems = @(Get-TreeProblem -Tree $Layout.StateTree -ServiceSid $ServiceSid -Quick -Directory $directory)
    if ($problems.Count -gt 0) { return $null }
    return $directory
}

# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

function ConvertFrom-JsonUnlimited {
    # Windows PowerShell 5.1 ConvertFrom-Json refuses input above about 2 MB (JavaScriptSerializer
    # MaxJsonLength). The log-bundle result can be 45 MiB (TASK-0083 carry), so this parser has
    # no length limit. Returns dictionaries and arrays.
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    Add-Type -AssemblyName System.Web.Extensions
    $serializer = New-Object System.Web.Script.Serialization.JavaScriptSerializer
    $serializer.MaxJsonLength = [int]::MaxValue
    $serializer.RecursionLimit = 32
    return $serializer.DeserializeObject($Text)
}

function Get-DictValue {
    # Reads one key of a parsed JSON object (a generic Dictionary) or a hashtable; $null when the
    # key is absent. Windows PowerShell 5.1 cannot call the generic Dictionary's explicit
    # IDictionary.Contains, so every reader of parsed JSON uses this.
    param([AllowNull()]$Dictionary, [Parameter(Mandatory = $true)][string]$Key)
    if ($null -eq $Dictionary) { return $null }
    if ($Dictionary -is [System.Collections.Generic.IDictionary[string, object]]) {
        if ($Dictionary.ContainsKey($Key)) { return , $Dictionary[$Key] }
        return $null
    }
    if ($Dictionary -is [System.Collections.IDictionary]) {
        if ($Dictionary.Contains($Key)) { return , $Dictionary[$Key] }
    }
    return $null
}

function Get-OrdinalSorted {
    # Sorts strings by their code points. Sort-Object in Windows PowerShell 5.1 sorts by culture,
    # which ignores hyphens ("wsl-facts" after "wslconfig"); key checks need a fixed order.
    param([AllowNull()][AllowEmptyCollection()][object[]]$Items)
    $list = New-Object System.Collections.Generic.List[string]
    foreach ($item in @($Items)) { if ($null -ne $item) { $list.Add([string]$item) } }
    $array = $list.ToArray()
    [Array]::Sort($array, [StringComparer]::Ordinal)
    return , $array
}

function ConvertTo-PlainValue {
    # Turns a value into what JavaScriptSerializer can write without walking PowerShell's
    # wrappers: strings, booleans, numbers, dictionaries with string keys, and arrays. In Windows
    # PowerShell 5.1 every value that a command or function returns can arrive wrapped in a
    # PSObject, and the serializer then walks the wrapper and stops on a circular reference. So
    # each value is unwrapped, and each child is unwrapped again where it is stored (a function's
    # return value is wrapped once more on its way back). A PSCustomObject becomes a dictionary
    # of its note properties, a CIM instance a dictionary of its properties, a date a UTC stamp,
    # a version, GUID, time span or enum value its text. Anything else is refused
    # (json_unsupported_type), so no object graph reaches a result file.
    param([AllowNull()]$Value, [int]$Depth = 0)
    if ($Depth -gt 16) { throw 'json_too_deep' }
    if ($null -eq $Value) { return $null }
    $base = $Value.PSObject.BaseObject
    if (($base -is [string]) -or ($base -is [bool])) { return $base }
    if ($base -is [char]) { return [string]$base }
    foreach ($type in @([int], [long], [double], [decimal], [single], [byte], [sbyte], [int16], [uint16], [uint32], [uint64])) {
        if ($base -is $type) { return $base }
    }
    if ($base -is [datetime]) { return (Get-UtcStamp -Time $base) }
    if (($base -is [version]) -or ($base -is [guid]) -or ($base -is [timespan]) -or ($base -is [System.Enum])) { return $base.ToString() }
    # Each child comes back through a function return, which wraps it in a PSObject again; it is
    # unwrapped here, in the scope that stores it (.PSObject.BaseObject is a property read, not
    # a function return, so it stays unwrapped).
    $children = New-Object System.Collections.Generic.List[object]
    $names = New-Object System.Collections.Generic.List[string]
    if ($base -is [System.Collections.IDictionary]) {
        foreach ($key in @($base.Keys)) { $names.Add([string]$key); $children.Add($base[$key]) }
    } elseif ($base -is [System.Management.Automation.PSCustomObject]) {
        foreach ($property in @($Value.PSObject.Properties | Where-Object { $_.MemberType -eq 'NoteProperty' })) { $names.Add([string]$property.Name); $children.Add($property.Value) }
    } elseif ($base.GetType().FullName -eq 'Microsoft.Management.Infrastructure.CimInstance') {
        foreach ($property in @($base.CimInstanceProperties)) { $names.Add([string]$property.Name); $children.Add($property.Value) }
    } elseif ($base -is [System.Collections.IEnumerable]) {
        $list = New-Object System.Collections.Generic.List[object]
        foreach ($item in $base) {
            $child = ConvertTo-PlainValue -Value $item -Depth ($Depth + 1)
            if ($null -ne $child) { $child = $child.PSObject.BaseObject }
            $list.Add($child)
        }
        return , $list.ToArray()
    } else {
        throw 'json_unsupported_type'
    }
    $out = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    for ($i = 0; $i -lt $names.Count; $i++) {
        $child = ConvertTo-PlainValue -Value $children[$i] -Depth ($Depth + 1)
        if ($null -ne $child) { $child = $child.PSObject.BaseObject }
        $out[$names[$i]] = $child
    }
    return , $out
}

function ConvertTo-JsonText {
    param([Parameter(Mandatory = $true)][AllowNull()]$Value)
    Add-Type -AssemblyName System.Web.Extensions
    $serializer = New-Object System.Web.Script.Serialization.JavaScriptSerializer
    $serializer.MaxJsonLength = [int]::MaxValue
    $plain = ConvertTo-PlainValue -Value $Value
    if ($null -ne $plain) { $plain = $plain.PSObject.BaseObject }
    return $serializer.Serialize($plain)
}

function Write-JsonFile {
    # Writes UTF-8 without a byte order mark through a temporary file and a rename, so a reader
    # never sees half a file.
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)]$Value)
    $temp = $Path + '.tmp'
    if (Test-Path -LiteralPath $temp) { Remove-PathNoFollow -Path $temp }
    [System.IO.File]::WriteAllText($temp, (ConvertTo-JsonText $Value), (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $Path) { Remove-PathNoFollow -Path $Path }
    [System.IO.File]::Move($temp, $Path)
}

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw ('{0} is a reparse point.' -f $Path) }
    return ConvertFrom-JsonUnlimited ([System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8))
}

function New-StepResult {
    # The safe result of a check or step: a code and a message key that the wizard (W8) maps to
    # the spec's copy, plus safe values for the message.
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$MessageKey,
        [hashtable]$Values = @{}
    )
    return [ordered]@{ code = $Code; message_key = $MessageKey; values = $Values }
}

# ---------------------------------------------------------------------------
# Small Windows helpers
# ---------------------------------------------------------------------------

function ConvertTo-HelperResultText {
    # The helper result as JSON with "code" and "message_key" first (P2-2): the setup program's
    # ReadResultCode reads the first "code" in the file, so no other key may come before it.
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Result, [string]$Action = '', [string]$RunId = '')
    $ordered = [ordered]@{ code = [string]$Result['code']; message_key = [string]$Result['message_key'] }
    foreach ($key in @($Result.Keys)) {
        if (@('code', 'message_key') -contains [string]$key) { continue }
        $ordered[[string]$key] = $Result[$key]
    }
    if ($Action) { $ordered['action'] = $Action }
    if ($RunId) { $ordered['run_id'] = $RunId }
    return (ConvertTo-JsonText $ordered)
}

function Test-Administrator {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WslExe { return (Join-Path $SlateOpsPaths.System32 'wsl.exe') }

function Get-UserProfilePath { return [Environment]::GetFolderPath('UserProfile') }

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-PasswordModuleLogged {
    # Kit check (R7, C18): the password-receiving modules that PowerShell module logging covers.
    # Throws when the policy cannot be read; the caller treats that as a Fix item (W80-8).
    param([hashtable]$Policy = (Get-PowerShellLoggingPolicy))
    $covered = @()
    if (-not $Policy.ModuleLogging) { return $covered }
    foreach ($module in $SlateOps.PasswordModules) {
        foreach ($pattern in $Policy.ModuleNames) {
            if ($module -like $pattern) { $covered += $module; break }
        }
    }
    return $covered
}

function Get-PowerShellLoggingPolicy {
    # Kit function: reads the Windows PowerShell logging policies from HKLM and HKCU.
    $result = @{ ModuleLogging = $false; ModuleNames = @(); ScriptBlockLogging = $false; Transcription = $false }
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
