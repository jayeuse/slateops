# Windows.ps1 - the administrator-side Windows steps of setup (plan 4.1 pages 3a and 4a, 6.2
# Windows-side steps, 10.3 F4a, 10.7; wizard spec 4.1, 4.5, C04, C08, C22, C29).
# Each step returns a safe code and a message key (New-StepResult). Changes are recorded in
# state\windows-changes.json with the old values, so uninstall (W9) can restore them.
# Windows PowerShell 5.1, ASCII only.

# ---------------------------------------------------------------------------
# State folder entry check (spec 4.1, W80-5) and the data folder (plan 4.3, W7-3)
# ---------------------------------------------------------------------------

function Test-StateFolder {
    # Before setup reads or writes C:\ProgramData\SlateOps: the folder must pass the safety
    # check. A folder that a non-administrator owns stops setup on S01.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [string]$ServiceSid = '')
    if (-not (Test-Path -LiteralPath $Layout.StateRoot)) { return New-StepResult -Code 'absent' -MessageKey 'setup.state.absent' }
    $problems = @(Get-TreeProblem -Tree $Layout.StateTree -ServiceSid $ServiceSid)
    if ($problems.Count -eq 0) { return New-StepResult -Code 'safe' -MessageKey 'setup.state.safe' }
    foreach ($problem in $problems) { Write-RunLog 'setup.state' 'FAIL' $problem }
    if (@($problems | Where-Object { $_ -like 'root_owner:*' }).Count -gt 0) {
        return New-StepResult -Code 'unsafe_owner' -MessageKey 'setup.state.unsafe_owner'
    }
    return New-StepResult -Code 'unsafe' -MessageKey 'setup.state.unsafe'
}

function Initialize-StateFolder {
    # Creates the state tree with its access lists in the creating call, before the first write.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [string]$ServiceSid = '')
    $problems = @(Initialize-ProtectedTree -Tree $Layout.StateTree -ServiceSid $ServiceSid)
    if ($problems.Count -gt 0) {
        foreach ($problem in $problems) { Write-RunLog 'setup.state' 'FAIL' $problem }
        return New-StepResult -Code 'unsafe' -MessageKey 'setup.state.unsafe'
    }
    return New-StepResult -Code 'ready' -MessageKey 'setup.state.ready'
}

function Get-VhdSizeGB {
    # .wslconfig defaultVhdSize from the free space of the data drive (plan 4.3): 90 percent of
    # the free space, at least 25 GB (the engine's data_vhd_max_gb minimum; parent decision 7,
    # TASK-0094) and at most 1024 GB (the WSL default is 1 TB). Proposed.
    param([Parameter(Mandatory = $true)][long]$FreeBytes)
    $size = [long][math]::Floor(([double]$FreeBytes * 0.9) / 1GB)
    if ($size -lt 25) { return 25 }
    if ($size -gt 1024) { return 1024 }
    return [int]$size
}

function Initialize-DataFolder {
    # Creates <data folder> with its access list (the service account: modify on distro, read on
    # payload) and writes state\install.json. Refuses a folder that fails the safety check or
    # holds anything (spec S07: empty, or kept data, which W9 handles).
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][string]$DataRoot,
        [string]$ServiceSid = ''
    )
    if (-not (Test-DataRootPath $DataRoot)) { return New-StepResult -Code 'path_invalid' -MessageKey 'setup.data.path_invalid' }
    # S91-2: every folder above the data folder must keep it in place (W8 writes the copy).
    $parents = @(Get-FolderParentProblem -Path $DataRoot)
    if ($parents.Count -gt 0) {
        foreach ($problem in $parents) { Write-RunLog 'setup.data' 'FAIL' $problem }
        return New-StepResult -Code 'data_folder_parent_unsafe' -MessageKey 'setup.data.data_folder_parent_unsafe' -Values @{ reason = ($parents[0] -split ':')[0] }
    }
    $drive = $DataRoot.Substring(0, 2)
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $drive)
    if ((-not $disk) -or ([int]$disk.DriveType -ne 3) -or ([string]$disk.FileSystem -ne 'NTFS')) { return New-StepResult -Code 'drive_not_fixed_ntfs' -MessageKey 'setup.data.drive_not_fixed_ntfs' }
    if ((Test-Path -LiteralPath $DataRoot) -and (@(Get-ChildItem -LiteralPath $DataRoot -Force).Count -gt 0)) {
        $owned = @(Get-ChildItem -LiteralPath $DataRoot -Force | Where-Object { @('distro', 'payload') -notcontains $_.Name })
        if ($owned.Count -gt 0) { return New-StepResult -Code 'not_empty' -MessageKey 'setup.data.not_empty' }
    }
    Set-LayoutDataRoot -Layout $Layout -DataRoot $DataRoot
    $problems = @(Initialize-ProtectedTree -Tree $Layout.DataTree -ServiceSid $ServiceSid)
    if ($problems.Count -gt 0) {
        foreach ($problem in $problems) { Write-RunLog 'setup.data' 'FAIL' $problem }
        return New-StepResult -Code 'unsafe' -MessageKey 'setup.data.unsafe'
    }
    $size = Get-VhdSizeGB -FreeBytes ([long]$disk.FreeSpace)
    Write-JsonFile -Path $Layout.StateFile -Value ([ordered]@{ schema_version = 1; data_root = $DataRoot; vhd_size_gb = $size })
    Write-RunLog 'setup.data' 'INFO' ('data folder {0}, disk limit {1} GB' -f $DataRoot, $size)
    return New-StepResult -Code 'ready' -MessageKey 'setup.data.ready' -Values @{ vhd_size_gb = $size }
}

function Install-ScriptsCopy {
    # Copies the scripts that the tasks run into the state tree (administrators write, the
    # service account reads), as the kit ran from its own protected folder: a custom program
    # folder can be writable by standard users.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$SourceDir)
    $problems = @(Get-TreeProblem -Tree $Layout.StateTree -ServiceSid '')
    if ($problems.Count -gt 0) { return New-StepResult -Code 'unsafe' -MessageKey 'setup.state.unsafe' }
    foreach ($child in @(Get-ChildItem -LiteralPath $Layout.Scripts -Force)) { Remove-PathNoFollow -Path $child.FullName }
    foreach ($name in @('exec.ps1', 'start.ps1', 'setup-helper.ps1', 'version.json')) {
        $source = Join-Path $SourceDir $name
        if (Test-Path -LiteralPath $source -PathType Leaf) { Copy-Item -LiteralPath $source -Destination (Join-Path $Layout.Scripts $name) }
    }
    $lib = Join-Path $Layout.Scripts 'lib'
    [void][System.IO.Directory]::CreateDirectory($lib)
    foreach ($file in @(Get-ChildItem -LiteralPath (Join-Path $SourceDir 'lib') -Filter '*.ps1' -File)) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $lib $file.Name)
    }
    Write-RunLog 'setup.scripts' 'INFO' ('scripts copied to {0}' -f $Layout.Scripts)
    return New-StepResult -Code 'copied' -MessageKey 'setup.scripts.copied'
}

function Copy-PayloadPart {
    # Copies fixed-name parts into the data folder's payload folder. Their hashes are checked
    # where they are used: the Linux image by import-distro, the rest by the engine (receive).
    # The folders above the data folder and the data tree are checked again right before the
    # copy (S91-2).
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][string]$SourceDir,
        [Parameter(Mandatory = $true)][string[]]$Names,
        [string]$ServiceSid = ''
    )
    $problems = @(Get-FolderParentProblem -Path $Layout.DataRoot) + @(Get-TreeProblem -Tree $Layout.DataTree -ServiceSid $ServiceSid)
    if ($problems.Count -gt 0) {
        foreach ($problem in $problems) { Write-RunLog 'setup.payload' 'FAIL' $problem }
        return New-StepResult -Code 'data_folder_parent_unsafe' -MessageKey 'setup.data.data_folder_parent_unsafe' -Values @{ reason = ($problems[0] -split ':')[0] }
    }
    foreach ($name in $Names) {
        if ($name -notmatch '^[A-Za-z0-9._-]+$') { throw 'Not a payload part name.' }
        $source = Join-Path $SourceDir $name
        $target = Join-Path $Layout.Payload $name
        if (Test-Path -LiteralPath $target) { Remove-PathNoFollow -Path $target }
        Copy-Item -LiteralPath $source -Destination $target
        Write-RunLog 'setup.payload' 'INFO' ('{0}: {1} bytes' -f $name, (Get-Item -LiteralPath $target).Length)
    }
    return New-StepResult -Code 'copied' -MessageKey 'setup.payload.copied'
}

# ---------------------------------------------------------------------------
# Saved progress, the RunOnce entry and the desktop shortcut (plan F4a; spec 4.1, 4.5; N-1)
# ---------------------------------------------------------------------------

$SlateOpsResume = @{
    Stages       = @('check_restart', 'feature_restart', 'continue_later', 'install_started', 'install_finished', 'key_saved')
    RunOnceKey   = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
    RunOnceName  = 'SlateOpsSetup'
    ShortcutName = 'Continue Slate Operations setup.lnk'
}

function Test-SetupPath {
    # The original setup file: an absolute .exe path with no quotes.
    param([AllowNull()][string]$Path)
    if (-not $Path) { return $false }
    if ($Path -notmatch '^[A-Za-z]:\\[^"<>|?*\x00-\x1f]+\.exe$') { return $false }
    return $true
}

function Get-ResumeCommand {
    # The RunOnce command. Explorer opens the setup file as a double-click does, so Windows shows
    # the normal administrator prompt (W80-5); setup never starts elevated by itself. The setup
    # program picks its first screen from the saved progress, so it needs no switch.
    param([Parameter(Mandatory = $true)][string]$SetupPath)
    if (-not (Test-SetupPath $SetupPath)) { throw 'Not a setup file path.' }
    return ('"{0}" "{1}"' -f (Join-Path $SlateOpsPaths.Windows 'explorer.exe'), $SetupPath)
}

function Save-SetupProgress {
    # Saves the progress (no secret, no answer, no email address: N-3) in the state tree only.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][string]$RunId,
        [hashtable]$Marks = @{}
    )
    if ($SlateOpsResume.Stages -notcontains $Stage) { throw 'Unknown stage.' }
    if (-not (Test-RunId $RunId)) { throw 'Not a run ID.' }
    $record = [ordered]@{ schema_version = 1; stage = $Stage; run_id = $RunId; saved_at = (Get-UtcStamp) }
    foreach ($key in @($Marks.Keys | Sort-Object)) {
        if ($key -notmatch '^[a-z_]{1,32}$') { throw 'Not a mark name.' }
        if (-not ($Marks[$key] -is [bool])) { throw 'A mark is true or false.' }
        $record[$key] = $Marks[$key]
    }
    Write-JsonFile -Path $Layout.ProgressFile -Value $record
    Write-RunLog 'setup.progress' 'INFO' ('saved stage {0}' -f $Stage)
}

function Read-SetupProgress {
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    if (-not (Test-Path -LiteralPath $Layout.ProgressFile)) { return $null }
    $value = Read-JsonFile -Path $Layout.ProgressFile
    if ((-not ($value -is [System.Collections.IDictionary])) -or ($SlateOpsResume.Stages -notcontains [string](Get-DictValue $value 'stage'))) { return $null }
    return $value
}

function Compare-ReleaseVersion {
    # SemVer precedence of two release versions (plan page 1): X.Y.Z-rc.N is older than
    # X.Y.Z-rc.N+1, and both are older than X.Y.Z. Returns -1, 0 or 1.
    param([Parameter(Mandatory = $true)][string]$Left, [Parameter(Mandatory = $true)][string]$Right)
    $parts = foreach ($value in @($Left, $Right)) {
        if (-not (Test-ReleaseVersion $value)) { throw 'Not a release version.' }
        $core, $rc = $value -split '-rc\.'
        $numbers = @($core -split '\.' | ForEach-Object { [int]$_ })
        # A release without -rc sorts after every rc of the same X.Y.Z.
        , ($numbers + @($(if ($rc) { [int]$rc } else { [int]::MaxValue })))
    }
    for ($i = 0; $i -lt 4; $i++) {
        if ($parts[0][$i] -lt $parts[1][$i]) { return -1 }
        if ($parts[0][$i] -gt $parts[1][$i]) { return 1 }
    }
    return 0
}

function Get-InstalledVersion {
    # The installed program's version (its version.json in the folder that this setup's
    # uninstall key names), or '' when none is installed (spec 4.1).
    if (-not (Test-InstalledProgram)) { return '' }
    $key = Get-ItemProperty -LiteralPath $SlateOpsCheck.UninstallKey -ErrorAction SilentlyContinue
    try { return (Read-SetupVersion -Path (Join-Path ([string]$key.InstallLocation) 'version.json')).version } catch { return '' }
}

function Get-SetupEntry {
    # Spec 4.1: the first screen from Windows-side records only: the saved progress, then the
    # installed version (W8): this setup newer gives M05 (W13b), the same or older gives M01.
    param([AllowNull()][System.Collections.IDictionary]$Progress, [string]$Installed = '', [string]$SetupVersion = '')
    if ($Installed -and $SetupVersion -and (($null -eq $Progress) -or ([string](Get-DictValue $Progress 'stage') -eq 'key_saved'))) {
        if ((Compare-ReleaseVersion -Left $SetupVersion -Right $Installed) -gt 0) { return @{ screen = 'M05'; next = ''; installed = $Installed } }
        return @{ screen = 'M01'; next = ''; installed = $Installed }
    }
    if ($null -eq $Progress) { return @{ screen = 'S01'; next = '' } }
    switch ([string](Get-DictValue $Progress 'stage')) {
        'check_restart'    { return @{ screen = 'S02'; next = ''; welcome_back = $true } }
        'feature_restart'  { return @{ screen = 'S06'; next = 'S07' } }
        # W8 correction 4: the background preparation runs again on resume unless it finished.
        'continue_later'   { return @{ screen = 'S06'; next = 'S08'; background_done = ((Get-DictValue $Progress 'background_done') -eq $true) } }
        'install_started'  {
            if ((Get-DictValue $Progress 'email_discarded') -eq $true) { return @{ screen = 'S06'; next = 'S09' } }
            return @{ screen = 'S06'; next = 'S12' }
        }
        'install_finished' { return @{ screen = 'S06'; next = 'S14'; new_recovery_key = $true } }
        'key_saved'        { return @{ screen = 'M01'; next = '' } }
    }
    return @{ screen = 'S01'; next = '' }
}

function Get-SessionUserName {
    # The user who is signed in to this session: the owner of explorer.exe in the session of
    # this process (DOMAIN\user). Empty when it cannot be read.
    try {
        $session = (Get-Process -Id $PID).SessionId
        foreach ($process in @(Get-CimInstance -ClassName Win32_Process -Filter ("Name='explorer.exe' AND SessionId={0}" -f [int]$session))) {
            $owner = Invoke-CimMethod -InputObject $process -MethodName GetOwner
            if ($owner.ReturnValue -eq 0) { return ('{0}\{1}' -f $owner.Domain, $owner.User) }
        }
    } catch { $null = $_ }
    return ''
}

function Test-ResumeUser {
    # S91-7: the RunOnce entry and the shortcut go into the profile of the user who runs setup.
    # When an administrator elevated setup for another signed-in user, that profile is not the
    # signed-in user's, so no entry is written (W8 tells the person to open setup again).
    param([AllowEmptyString()][string]$ElevatedUser, [AllowEmptyString()][string]$SessionUser)
    if ((-not $ElevatedUser) -or (-not $SessionUser)) { return $false }
    return ($ElevatedUser -ieq $SessionUser)
}

function Test-ResumePath {
    # S91-6: the desktop folder and the shortcut path are not reparse points.
    param([Parameter(Mandatory = $true)][string]$Shortcut)
    foreach ($path in @((Split-Path -Parent $Shortcut), $Shortcut)) {
        $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { return $false }
    }
    return $true
}

function Register-SetupResume {
    # The RunOnce entry and the desktop shortcut, both starting the original setup file (N-1).
    param([Parameter(Mandatory = $true)][string]$SetupPath, [string]$SessionUser = (Get-SessionUserName))
    $command = Get-ResumeCommand -SetupPath $SetupPath
    $elevated = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if (-not (Test-ResumeUser -ElevatedUser $elevated -SessionUser $SessionUser)) {
        Write-RunLog 'setup.resume' 'WARN' ('setup runs as {0}, the signed-in user is {1}: no resume entries' -f $elevated, $SessionUser)
        return New-StepResult -Code 'resume_other_user' -MessageKey 'setup.resume.resume_other_user'
    }
    $shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) $SlateOpsResume.ShortcutName
    if (-not (Test-ResumePath -Shortcut $shortcut)) { return New-StepResult -Code 'resume_path_unsafe' -MessageKey 'setup.resume.resume_path_unsafe' }
    if (-not (Test-Path -LiteralPath $SlateOpsResume.RunOnceKey)) { New-Item -Path $SlateOpsResume.RunOnceKey -Force | Out-Null }
    New-ItemProperty -LiteralPath $SlateOpsResume.RunOnceKey -Name $SlateOpsResume.RunOnceName -PropertyType String -Value $command -Force | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($shortcut)
    $link.TargetPath = $SetupPath
    $link.WorkingDirectory = Split-Path -Parent $SetupPath
    $link.Save()
    Write-RunLog 'setup.resume' 'INFO' ('RunOnce {0} and shortcut {1} start {2}' -f $SlateOpsResume.RunOnceName, $shortcut, $SetupPath)
    return New-StepResult -Code 'registered' -MessageKey 'setup.resume.registered'
}

function Clear-SetupResume {
    # Removes the RunOnce entry, the shortcut and (with -Progress) the saved progress (spec 4.5
    # Cancel; S07 removes the shortcut when it opens, plan F4a). A shortcut path that is a
    # reparse point is removed itself, never followed.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [switch]$Progress)
    Remove-ItemProperty -LiteralPath $SlateOpsResume.RunOnceKey -Name $SlateOpsResume.RunOnceName -ErrorAction SilentlyContinue
    $shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) $SlateOpsResume.ShortcutName
    if (Test-Path -LiteralPath $shortcut) { Remove-PathNoFollow -Path $shortcut }
    if ($Progress -and (Test-Path -LiteralPath $Layout.ProgressFile)) { Remove-PathNoFollow -Path $Layout.ProgressFile }
    Write-RunLog 'setup.resume' 'INFO' 'resume entries removed'
    return New-StepResult -Code 'cleared' -MessageKey 'setup.resume.cleared'
}

function Invoke-PcRestart {
    # "Restart now" (C08, S05) or "Restart to startup settings" (C04, UEFI only). Never a delay
    # above 0: /t above 0 implies /f, which closes programs without a warning.
    param([switch]$Firmware)
    $arguments = @('/r', '/t', '0')
    if ($Firmware) {
        Initialize-NativeInfoType
        if ([SlateOpsSetup.NativeInfo]::FirmwareType() -ne 2) { return New-StepResult -Code 'not_uefi' -MessageKey 'setup.restart.not_uefi' }
        $arguments = @('/r', '/fw', '/t', '0')
    }
    $run = Invoke-Logged -Step 'setup.restart' -FilePath 'shutdown.exe' -ArgumentList $arguments -NoThrow
    if ($run.ExitCode -ne 0) { return New-StepResult -Code 'failed' -MessageKey 'setup.restart.failed' -Values @{ exit_code = $run.ExitCode } }
    return New-StepResult -Code 'restarting' -MessageKey 'setup.restart.restarting'
}

# ---------------------------------------------------------------------------
# Prepare this PC: VirtualMachinePlatform and the pinned WSL MSI (plan 3a, 7.4; spec S05)
# ---------------------------------------------------------------------------

function Get-MsiOutcome {
    # Plan 10.7: 0 installed; 3010 restart needed; 1618 another install runs (wait, try again,
    # three times); anything else failed.
    param([Parameter(Mandatory = $true)][int]$ExitCode)
    switch ($ExitCode) {
        0 { return 'installed' }
        3010 { return 'restart_needed' }
        1641 { return 'restart_started' }
        1618 { return 'busy' }
    }
    return 'failed'
}

function Enable-VirtualMachinePlatform {
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $state = [string](Get-WindowsOptionalFeature -Online -FeatureName 'VirtualMachinePlatform').State
    Write-RunLog 'prepare.feature' 'INFO' ('VirtualMachinePlatform: {0}' -f $state)
    if ($state -eq 'Enabled') { return New-StepResult -Code 'enabled' -MessageKey 'prepare.feature.enabled' -Values @{ restart_needed = $false } }
    if ($state -eq 'EnablePending') { return New-StepResult -Code 'pending' -MessageKey 'prepare.feature.pending' -Values @{ restart_needed = $true } }
    $record = Read-WindowsChanges -Layout $Layout
    $record['vmp_enabled_by_setup'] = $true
    Save-WindowsChanges -Layout $Layout -Record $record
    $result = Enable-WindowsOptionalFeature -Online -FeatureName 'VirtualMachinePlatform' -All -NoRestart
    Write-RunLog 'prepare.feature' 'INFO' ('enabled; restart needed: {0}' -f [bool]$result.RestartNeeded)
    return New-StepResult -Code 'enabled_now' -MessageKey 'prepare.feature.enabled_now' -Values @{ restart_needed = $true }
}

function Install-WslPackage {
    # Installs the pinned WSL MSI. The SHA-256 is checked right before msiexec; the MSI log is
    # verbose. A newer installed WSL is kept (plan 7.4 rule 3).
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][string]$MsiPath,
        [Parameter(Mandatory = $true)][string]$Sha256,
        [Parameter(Mandatory = $true)][version]$PinnedVersion,
        [int]$BusyWaitSeconds = 60
    )
    $installed = Get-WslPackageVersion
    if (($null -ne $installed) -and ($installed -ge $PinnedVersion)) {
        Write-RunLog 'prepare.wsl' 'INFO' ('WSL {0} is installed (pinned {1}); not changed' -f $installed, $PinnedVersion)
        return New-StepResult -Code 'present' -MessageKey 'prepare.wsl.present' -Values @{ restart_needed = $false }
    }
    $record = Read-WindowsChanges -Layout $Layout
    if (-not $record.Contains('wsl_version_before_setup')) {
        $record['wsl_version_before_setup'] = $(if ($null -eq $installed) { 'none' } else { $installed.ToString() })
        Save-WindowsChanges -Layout $Layout -Record $record
    }
    $msiLog = Join-Path (Join-Path $Layout.Logs 'setup') ('wsl-msi-{0}.log' -f (Format-UtcTime -Format 'yyyyMMddTHHmmssZ'))
    for ($attempt = 1; $attempt -le 4; $attempt++) {
        $hash = Get-FileSha256 -Path $MsiPath
        if ($hash -ne $Sha256) {
            Write-RunLog 'prepare.wsl' 'FAIL' ('SHA-256 {0} does not match the pinned value' -f $hash)
            return New-StepResult -Code 'hash_mismatch' -MessageKey 'prepare.wsl.hash_mismatch'
        }
        Write-RunLog 'prepare.wsl' 'INFO' ('SHA-256 {0} checked right before msiexec' -f $hash)
        # msiexec is a GUI program: Start-Process -Wait waits for it (kit 10-setup.ps1).
        $arguments = @('/i', ('"{0}"' -f $MsiPath), '/qn', '/norestart', '/l*v', ('"{0}"' -f $msiLog))
        Write-RunLog 'prepare.wsl' 'INFO' ('> msiexec.exe {0}' -f ($arguments -join ' '))
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList $arguments -Wait -PassThru
        $watch.Stop()
        $run = @{ ExitCode = $process.ExitCode }
        Write-RunLog 'prepare.wsl' 'INFO' ('  exit code {0}, {1} ms' -f $run.ExitCode, $watch.ElapsedMilliseconds)
        $outcome = Get-MsiOutcome -ExitCode $run.ExitCode
        if (($outcome -ne 'busy') -or ($attempt -eq 4)) { break }
        Write-RunLog 'prepare.wsl' 'WARN' ('another installation runs (1618); try {0} of 3 again in {1} s' -f $attempt, $BusyWaitSeconds)
        Start-Sleep -Seconds $BusyWaitSeconds
    }
    switch ($outcome) {
        'installed' { return New-StepResult -Code 'installed' -MessageKey 'prepare.wsl.installed' -Values @{ restart_needed = $false } }
        'restart_needed' { return New-StepResult -Code 'installed' -MessageKey 'prepare.wsl.installed' -Values @{ restart_needed = $true } }
        'busy' { return New-StepResult -Code 'busy' -MessageKey 'prepare.wsl.busy' -Values @{ exit_code = $run.ExitCode } }
    }
    return New-StepResult -Code 'failed' -MessageKey 'prepare.wsl.failed' -Values @{ exit_code = $run.ExitCode }
}

# ---------------------------------------------------------------------------
# Windows-side install steps (plan 6.2): firewall, hosts, CA, sleep and the lid
# ---------------------------------------------------------------------------

function Get-FirewallRuleDefinition {
    # Kit rules for TCP 443 and 80: Windows Defender Firewall (Private, LocalSubnet) and the
    # Hyper-V firewall for the WSL VM (Private, the LAN network; the documentation does not say
    # whether Hyper-V rules accept LocalSubnet, kit design notes).
    param([Parameter(Mandatory = $true)][string]$Cidr)
    # /0 would open the rule to every address (S91-11).
    if ($Cidr -notmatch '^([0-9]{1,3}\.){3}[0-9]{1,3}/([1-9]|[12][0-9]|3[0-2])$') { throw 'Not an IPv4 network.' }
    return @{
        Windows = @{
            Name = $SlateOps.FirewallRuleName; DisplayName = 'Slate Operations (TCP 443 and 80)'; Group = $SlateOps.FirewallGroup
            Direction = 'Inbound'; Action = 'Allow'; Protocol = 'TCP'; LocalPort = @('443', '80'); Profile = 'Private'; RemoteAddress = 'LocalSubnet'
        }
        HyperV = @{
            Name = $SlateOps.HyperVRuleName; DisplayName = 'Slate Operations (TCP 443 and 80)'
            Direction = 'Inbound'; VMCreatorId = $SlateOps.WslVmCreatorId; Protocol = 'TCP'; LocalPorts = @('443', '80'); RemoteAddresses = $Cidr
            Profiles = 'Private'; Action = 'Allow'
        }
    }
}

function ConvertTo-NetworkCidr {
    # Kit function: 192.168.1.23 and 24 -> 192.168.1.0/24.
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

function Set-FirewallRules {
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$Cidr)
    $definition = Get-FirewallRuleDefinition -Cidr $Cidr
    try {
        Get-NetFirewallRule -Name $definition.Windows.Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        $windows = $definition.Windows
        New-NetFirewallRule @windows | Out-Null
        Write-RunLog 'install.windows.firewall' 'INFO' ('rule {0}: inbound TCP 443, 80, Private, LocalSubnet' -f $windows.Name)
        Get-NetFirewallHyperVRule -Name $definition.HyperV.Name -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule
        $hyperV = $definition.HyperV
        New-NetFirewallHyperVRule @hyperV | Out-Null
        Write-RunLog 'install.windows.firewall' 'INFO' ('Hyper-V rule {0}: inbound TCP 443, 80, Private, {1}' -f $hyperV.Name, $Cidr)
    } catch {
        Write-RunLog 'install.windows.firewall' 'ERROR' $_.Exception.Message
        return New-StepResult -Code 'failed' -MessageKey 'install.windows.firewall_failed'
    }
    $record = Read-WindowsChanges -Layout $Layout
    $record['firewall_rules'] = @($definition.Windows.Name)
    $record['hyperv_rules'] = @($definition.HyperV.Name)
    $record['hyperv_cidr'] = $Cidr
    Save-WindowsChanges -Layout $Layout -Record $record
    return New-StepResult -Code 'added' -MessageKey 'install.windows.firewall_added'
}

function Get-HostsContent {
    # Returns the hosts text with exactly one Slate Operations line "127.0.0.1 <name> # Slate
    # Operations" (plan 6.2: the server PC cannot open its own LAN address in mirrored mode,
    # REQ-0022). Other lines stay as they are.
    param([AllowEmptyString()][string]$Existing, [Parameter(Mandatory = $true)][string]$HostName)
    if ($HostName -notmatch '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.local$') { throw 'Not a .local name.' }
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($line in ($Existing -split "`r?`n")) {
        if ($line.EndsWith($SlateOps.HostsMarker)) { continue }
        $lines.Add($line)
    }
    while (($lines.Count -gt 0) -and ($lines[$lines.Count - 1] -eq '')) { $lines.RemoveAt($lines.Count - 1) }
    $lines.Add(('127.0.0.1 {0} {1}' -f $HostName, $SlateOps.HostsMarker))
    return (($lines -join "`r`n") + "`r`n")
}

function Set-HostsEntry {
    # Writes the hosts file back in the encoding it was read with (P3-5): a byte order mark
    # stays, a file without one gets none, and other lines keep their characters.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][string]$HostName,
        [string]$Path = (Join-Path $SlateOpsPaths.System32 'drivers\etc\hosts')
    )
    $existing = ''
    $encoding = [System.Text.Encoding]::Default
    if (Test-Path -LiteralPath $Path) {
        $reader = New-Object System.IO.StreamReader($Path, [System.Text.Encoding]::Default, $true)
        try { $existing = $reader.ReadToEnd(); $encoding = $reader.CurrentEncoding } finally { $reader.Dispose() }
    }
    $content = Get-HostsContent -Existing $existing -HostName $HostName
    if ($content -ne $existing) { [System.IO.File]::WriteAllText($Path, $content, $encoding) }
    $record = Read-WindowsChanges -Layout $Layout
    $record['hosts_name'] = $HostName
    Save-WindowsChanges -Layout $Layout -Record $record
    Write-RunLog 'install.windows.hosts' 'INFO' ('hosts: 127.0.0.1 {0}' -f $HostName)
    return New-StepResult -Code 'added' -MessageKey 'install.windows.hosts_added'
}

function ConvertFrom-PemCertificate {
    param([Parameter(Mandatory = $true)][string]$Pem)
    $match = [regex]::Match($Pem, '-----BEGIN CERTIFICATE-----([A-Za-z0-9+/=\s]+)-----END CERTIFICATE-----')
    if (-not $match.Success) { throw 'certificate_invalid' }
    $der = [Convert]::FromBase64String(($match.Groups[1].Value -replace '\s', ''))
    return New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(, $der)
}

function Get-CaSecurityCode {
    # The security code (spec S15, M01): SHA-256 of the root certificate, uppercase pairs joined
    # by ":" (engine trust.py format_fingerprint), computed on Windows from the certificate.
    param([Parameter(Mandatory = $true)][System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)
    $sha = New-Object System.Security.Cryptography.SHA256Managed
    try { $hash = $sha.ComputeHash($Certificate.RawData) } finally { $sha.Dispose() }
    return (($hash | ForEach-Object { $_.ToString('X2') }) -join ':')
}

function Initialize-CertPropertyType {
    # Certificate context properties (crypt32). .NET Framework has no managed call to set the
    # enhanced key usage property of a certificate in a store.
    if ('SlateOpsSetup.CertProperty' -as [type]) { return }
    $source = @'
using System;
using System.Runtime.InteropServices;
using System.Security.Cryptography.X509Certificates;
namespace SlateOpsSetup
{
    public static class CertProperty
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct CRYPT_DATA_BLOB { public int cbData; public IntPtr pbData; }

        [DllImport("crypt32.dll", SetLastError = true)]
        private static extern bool CertSetCertificateContextProperty(IntPtr context, int propId, int flags, ref CRYPT_DATA_BLOB data);

        [DllImport("crypt32.dll", SetLastError = true)]
        private static extern bool CertGetCertificateContextProperty(IntPtr context, int propId, byte[] data, ref int size);

        private const int CERT_ENHKEY_USAGE_PROP_ID = 9;

        public static void SetEnhancedKeyUsage(X509Certificate2 certificate, byte[] encoded)
        {
            IntPtr memory = Marshal.AllocHGlobal(encoded.Length);
            try
            {
                Marshal.Copy(encoded, 0, memory, encoded.Length);
                CRYPT_DATA_BLOB blob = new CRYPT_DATA_BLOB();
                blob.cbData = encoded.Length;
                blob.pbData = memory;
                if (!CertSetCertificateContextProperty(certificate.Handle, CERT_ENHKEY_USAGE_PROP_ID, 0, ref blob))
                {
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                }
            }
            finally { Marshal.FreeHGlobal(memory); }
        }

        public static byte[] GetEnhancedKeyUsage(X509Certificate2 certificate)
        {
            int size = 0;
            if (!CertGetCertificateContextProperty(certificate.Handle, CERT_ENHKEY_USAGE_PROP_ID, null, ref size)) { return null; }
            byte[] data = new byte[size];
            if (!CertGetCertificateContextProperty(certificate.Handle, CERT_ENHKEY_USAGE_PROP_ID, data, ref size)) { return null; }
            return data;
        }
    }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp
}

function Test-CaSelfSignature {
    # S91-9: the certificate verifies with its own key: a chain of one element whose only status
    # is "untrusted root" (no revocation check; the certificate is not trusted yet).
    param([Parameter(Mandatory = $true)][System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)
    $chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
    try {
        $chain.ChainPolicy.RevocationMode = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
        [void]$chain.Build($Certificate)
        if ($chain.ChainElements.Count -ne 1) { return $false }
        $allowed = [System.Security.Cryptography.X509Certificates.X509ChainStatusFlags]::UntrustedRoot
        foreach ($status in $chain.ChainElements[0].ChainElementStatus) {
            if (($status.Status -band (-bnot $allowed)) -ne 0) { return $false }
        }
        return $true
    } finally { $chain.Reset() }
}

function Get-StoreEnhancedKeyUsage {
    # The enhanced key usage OIDs set as a property on a certificate in a store; empty when none.
    param([Parameter(Mandatory = $true)][System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)
    Initialize-CertPropertyType
    $bytes = [SlateOpsSetup.CertProperty]::GetEnhancedKeyUsage($Certificate)
    if ($null -eq $bytes) { return , @() }
    $data = New-Object System.Security.Cryptography.AsnEncodedData('2.5.29.37', $bytes)
    $extension = New-Object System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension($data, $false)
    return , @($extension.EnhancedKeyUsages | ForEach-Object { $_.Value })
}

function Test-CaCertificate {
    # A self-signed CA certificate (basic constraints CA=true). Anything else is refused.
    param([Parameter(Mandatory = $true)][System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)
    if ($Certificate.Subject -ne $Certificate.Issuer) { return $false }
    foreach ($extension in $Certificate.Extensions) {
        if ($extension -is [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]) { return [bool]$extension.CertificateAuthority }
    }
    return $false
}

function Install-TrustedCa {
    # Adds the installation's root CA (public; the engine's install result ca_certificate_pem)
    # to LocalMachine Root (plan 6.2). Records the thumbprint for uninstall.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$Pem)
    try { $certificate = ConvertFrom-PemCertificate -Pem $Pem } catch { return New-StepResult -Code 'certificate_invalid' -MessageKey 'install.windows.ca_invalid' }
    if (-not (Test-CaCertificate -Certificate $certificate)) { return New-StepResult -Code 'certificate_invalid' -MessageKey 'install.windows.ca_invalid' }
    if (-not (Test-CaSelfSignature -Certificate $certificate)) { return New-StepResult -Code 'certificate_invalid' -MessageKey 'install.windows.ca_invalid' }
    # S91-9: the root is trusted for Server Authentication only (enhanced key usage property on
    # the store entry; the certificate itself is unchanged).
    $oids = New-Object System.Security.Cryptography.OidCollection
    [void]$oids.Add((New-Object System.Security.Cryptography.Oid('1.3.6.1.5.5.7.3.1')))
    $usage = New-Object System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension($oids, $false)
    Initialize-CertPropertyType
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
    $store.Open('ReadWrite')
    try {
        $store.Add($certificate)
        $stored = @($store.Certificates.Find([System.Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint, $certificate.Thumbprint, $false))
        if ($stored.Count -ne 1) { return New-StepResult -Code 'failed' -MessageKey 'install.windows.ca_failed' }
        [SlateOpsSetup.CertProperty]::SetEnhancedKeyUsage($stored[0], $usage.RawData)
    } finally { $store.Close() }
    $code = Get-CaSecurityCode -Certificate $certificate
    $record = Read-WindowsChanges -Layout $Layout
    $record['ca_thumbprint'] = $certificate.Thumbprint
    Save-WindowsChanges -Layout $Layout -Record $record
    Write-RunLog 'install.windows.ca' 'INFO' ('root CA {0} added to LocalMachine Root; security code {1}' -f $certificate.Thumbprint, $code)
    return New-StepResult -Code 'added' -MessageKey 'install.windows.ca_added' -Values @{ security_code = $code }
}

function Get-ActivePowerScheme {
    $active = Invoke-Logged -Step 'install.windows.power' -FilePath 'powercfg.exe' -ArgumentList @('/getactivescheme')
    $match = [regex]::Match(($active.Output -join ' '), '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
    if (-not $match.Success) { throw 'The active power plan cannot be read.' }
    return $match.Value
}

function Set-KeepAwake {
    # Kit: Sleep and Hibernate on mains power to Never; with -Lid (the person's C22 choice) the
    # lid action on mains power to "Do nothing" (LIDACTION, SUB_BUTTONS). The old values are
    # recorded once, so uninstall restores them (plan 9.1).
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [switch]$Lid)
    $scheme = Get-ActivePowerScheme
    $record = Read-WindowsChanges -Layout $Layout
    $settings = @(@{ group = 'SUB_SLEEP'; name = 'STANDBYIDLE'; key = 'power_standby_ac' }, @{ group = 'SUB_SLEEP'; name = 'HIBERNATEIDLE'; key = 'power_hibernate_ac' })
    if ($Lid) { $settings += @{ group = 'SUB_BUTTONS'; name = 'LIDACTION'; key = 'power_lid_ac' } }
    if (-not $record.Contains('power_scheme')) { $record['power_scheme'] = $scheme }
    foreach ($setting in $settings) {
        if (-not $record.Contains($setting.key)) {
            $old = Get-PowerIndex -Scheme $scheme -SubGroup $setting.group -Setting $setting.name
            $record[$setting.key] = $(if ($old) { $old.ac } else { $null })
        }
    }
    Save-WindowsChanges -Layout $Layout -Record $record
    foreach ($setting in $settings) {
        if ($null -eq $record[$setting.key]) {
            Write-RunLog 'install.windows.power' 'WARN' ('{0} {1} on mains power cannot be read; it is not changed' -f $setting.group, $setting.name)
            continue
        }
        $null = Invoke-Logged -Step 'install.windows.power' -FilePath 'powercfg.exe' -ArgumentList @('/setacvalueindex', $scheme, $setting.group, $setting.name, '0')
    }
    $null = Invoke-Logged -Step 'install.windows.power' -FilePath 'powercfg.exe' -ArgumentList @('/setactive', $scheme)
    return New-StepResult -Code 'set' -MessageKey 'install.windows.power_set'
}

# ---------------------------------------------------------------------------
# C29: remove the boot-test kit's parts, as the kit's 90-cleanup.ps1 does (after Continue)
# ---------------------------------------------------------------------------

function Invoke-KitUnregister {
    # Runs the kit's own "unregister" job as the kit's account through the kit's Exec task, in
    # the kit's request format, when the kit folder passes the kit's safety check. Returns $true
    # when the job reported exit code 0.
    param([Parameter(Mandatory = $true)][hashtable]$Kit)
    $problems = @(Get-KitTreeProblem -Kit $Kit)
    if ($problems.Count -gt 0) { Write-RunLog 'check.c29' 'WARN' ('the kit folder fails the safety check: {0}' -f ($problems -join '; ')); return $false }
    $account = Get-LocalUser -Name $Kit.AccountName -ErrorAction SilentlyContinue
    $task = Get-ScheduledTask -TaskPath $Kit.TaskPath -TaskName 'Exec' -ErrorAction SilentlyContinue
    if ((-not $task) -or (-not $account)) { return $false }
    $requestId = [guid]::NewGuid().ToString()
    [System.IO.File]::WriteAllText((Join-Path $Kit.Root 'state\request.txt'), ('unregister {0}' -f $requestId), [System.Text.Encoding]::ASCII)
    Start-ScheduledTask -TaskPath $Kit.TaskPath -TaskName 'Exec'
    $resultFile = Join-Path $Kit.Root 'svc-out\svc-exec-result.json'
    $deadline = (Get-Date).AddMinutes(10)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        if (Test-Path -LiteralPath $resultFile -PathType Leaf) {
            try { $result = Read-JsonFile -Path $resultFile } catch { $result = $null }
            if ($result -and ([string](Get-DictValue $result 'request_id') -eq $requestId)) { return ([int](Get-DictValue $result 'exit_code') -eq 0) }
        }
    }
    return $false
}

function Remove-KitLeftovers {
    # The kit's cleanup order, with no prompt (the C29 form's Continue is the confirmation):
    # boot task off; distribution unregistered as the kit's account, else the WSL service stops
    # for a moment (the C29 form names this); account disabled; tasks and task folder; rules;
    # sign-in entry, profile, account; rights by SID; the kit folder without its logs.
    # S91-1: nothing is removed when the kit folder fails the kit's safety check (a planted
    # folder or a junction at C:\ProgramData\SlateOpsBootTest), and the account is never touched
    # when it belongs to an installed Slate Operations (the installed program's version.json or
    # \SlateOps\ tasks exist).
    param([hashtable]$Kit = $SlateOpsCheck.Kit)
    $step = 'check.c29.remove'
    $problems = @(Get-KitTreeProblem -Kit $Kit)
    if ($problems.Count -gt 0) {
        foreach ($problem in $problems) { Write-RunLog $step 'FAIL' $problem }
        return New-StepResult -Code 'kit_folder_unsafe' -MessageKey 'check.c29.unknown_parts'
    }
    $productAccount = (Test-InstalledProgram) -or [bool](Get-ScheduledTask -TaskPath $SlateOps.TaskPath -ErrorAction SilentlyContinue)
    $account = $null
    if ($productAccount) { Write-RunLog $step 'WARN' 'Slate Operations is installed: the account and the WSL service are not touched' }
    else { $account = Get-LocalUser -Name $Kit.AccountName -ErrorAction SilentlyContinue }
    $sid = $(if ($account) { $account.SID.Value } else { '' })
    $tasks = @(Get-ScheduledTask -TaskPath $Kit.TaskPath -ErrorAction SilentlyContinue)
    if ($tasks | Where-Object { $_.TaskName -eq 'Start' }) {
        Disable-ScheduledTask -TaskPath $Kit.TaskPath -TaskName 'Start' | Out-Null
        Stop-ScheduledTask -TaskPath $Kit.TaskPath -TaskName 'Start'
        Write-RunLog $step 'INFO' 'kit boot task disabled and stopped'
    }
    if (-not $productAccount) {
        $vhdx = Join-Path $Kit.Root 'distro\vhd\ext4.vhdx'
        $gone = Invoke-KitUnregister -Kit $Kit
        if ((-not $gone) -and (Test-Path -LiteralPath $vhdx)) {
            Write-RunLog $step 'WARN' 'the kit distribution is still registered; stopping the WSL service for a moment'
            Stop-Service -Name 'WSLService' -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 5
        }
    }
    if ($account) { Disable-LocalUser -Name $Kit.AccountName; Write-RunLog $step 'INFO' 'account disabled' }
    foreach ($task in $tasks) { Unregister-ScheduledTask -TaskPath $Kit.TaskPath -TaskName $task.TaskName -Confirm:$false }
    if ($tasks.Count -gt 0) {
        $scheduler = New-Object -ComObject 'Schedule.Service'
        $scheduler.Connect()
        try { $scheduler.GetFolder('\').DeleteFolder($Kit.TaskPath.Trim('\'), 0) } catch { $null = $_ }
        Write-RunLog $step 'INFO' 'kit tasks removed'
    }
    Get-NetFirewallRule -Name $Kit.RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Get-NetFirewallHyperVRule -Name $Kit.HyperVRule -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule
    if ($account) {
        $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
        Remove-ItemProperty -LiteralPath $userList -Name $Kit.AccountName -ErrorAction SilentlyContinue
        $userProfile = Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid) -ErrorAction SilentlyContinue
        if ($userProfile -and -not $userProfile.Loaded) { Remove-CimInstance -InputObject $userProfile }
        Remove-LocalUser -Name $Kit.AccountName
        Write-RunLog $step 'INFO' 'account removed'
        Initialize-LsaRightsType
        [SlateOpsSetup.LsaRights]::Remove($sid, [string[]]$SlateOps.AccountRights)
    }
    if (Test-Path -LiteralPath $Kit.Root) {
        # Checked again right before the delete: the folder may have changed since the start.
        $again = @(Get-KitTreeProblem -Kit $Kit -AccountSid $sid)
        if ($again.Count -gt 0) {
            foreach ($problem in $again) { Write-RunLog $step 'FAIL' $problem }
            return New-StepResult -Code 'kit_folder_unsafe' -MessageKey 'check.c29.unknown_parts'
        }
        foreach ($child in @(Get-ChildItem -LiteralPath $Kit.Root -Force)) {
            if ($child.Name -ieq 'logs') { continue }
            Remove-PathNoFollow -Path $child.FullName
        }
        if ($sid) { $null = Invoke-Logged -Step $step -FilePath (Join-Path $SlateOpsPaths.System32 'icacls.exe') -ArgumentList @($Kit.Root, '/remove:g', ('*{0}' -f $sid)) -NoThrow }
        Write-RunLog $step 'INFO' 'kit folder removed; its logs stay'
    }
    $left = Get-LeftoverFact -Kit $Kit
    $check = @('kit_distro', 'kit_tasks', 'kit_rules')
    if (-not $productAccount) { $check += 'account' }
    $remaining = @($check | Where-Object { $left[$_] })
    if ($remaining.Count -gt 0) { return New-StepResult -Code 'incomplete' -MessageKey 'check.c29.incomplete' -Values @{ remaining = $remaining } }
    return New-StepResult -Code 'removed' -MessageKey 'check.c29.removed'
}

# ---------------------------------------------------------------------------
# W8: wizard page support (spec S07, S09, S10, S14, S15; plan 3.2, 10.3 F2)
# ---------------------------------------------------------------------------

$SlateOpsWizard = @{
    BackupFolder   = 'SlateOps-backups'
    # Proposed planning value: the free space a backup drive needs on S10 (spec "E: has 2 GB
    # free. Choose a drive with more space."); the first backup at install proves the real need.
    BackupMinBytes = [long]5 * 1GB
    # Spec S09 and section 12 item 7 (W80-7): the MX answer only selects a provider, by the mail
    # host. Google's hosts are a fixed list; Microsoft 365 gives every tenant its own host under
    # one fixed suffix.
    GoogleMxHosts  = @('smtp.google.com', 'aspmx.l.google.com', 'alt1.aspmx.l.google.com', 'alt2.aspmx.l.google.com',
        'alt3.aspmx.l.google.com', 'alt4.aspmx.l.google.com', 'aspmx2.googlemail.com', 'aspmx3.googlemail.com',
        'aspmx4.googlemail.com', 'aspmx5.googlemail.com')
    MicrosoftMxSuffix = '.mail.protection.outlook.com'
    # W80-3: printers that write a file instead of paper.
    FilePorts      = @('FILE:', 'PORTPROMPT:', 'NUL:')
    FileDrivers    = '(?i)(PDF|XPS|OneNote|Fax)'
}

function Get-PasswordPolicyState {
    # R7 again right before each password use (spec 5.2, W80-8): clear, policy or unreadable.
    try { $covered = @(Get-PasswordModuleLogged) } catch { return New-StepResult -Code 'unreadable' -MessageKey 'check.c18.unreadable' }
    if ($covered.Count -gt 0) { return New-StepResult -Code 'policy' -MessageKey 'check.c18.policy' }
    return New-StepResult -Code 'clear' -MessageKey 'check.c18.clear'
}

function Get-MailProvider {
    # gmail, m365 or none, from the MX records of the domain. The answer fills no field and sets
    # no server name (W80-7); Windows side only.
    param([Parameter(Mandatory = $true)][string]$Domain)
    try { $records = @(Resolve-DnsName -Name $Domain -Type MX -DnsOnly -QuickTimeout -ErrorAction Stop | Where-Object { $_.Type -eq 'MX' }) }
    catch { return New-StepResult -Code 'none' -MessageKey 'setup.email.provider_none' }
    foreach ($record in $records) {
        $mailHost = ([string]$record.NameExchange).TrimEnd('.').ToLowerInvariant()
        if ($SlateOpsWizard.GoogleMxHosts -contains $mailHost) { return New-StepResult -Code 'gmail' -MessageKey 'setup.email.provider_gmail' }
        if ($mailHost.EndsWith($SlateOpsWizard.MicrosoftMxSuffix) -and ($mailHost.Length -gt $SlateOpsWizard.MicrosoftMxSuffix.Length)) { return New-StepResult -Code 'm365' -MessageKey 'setup.email.provider_m365' }
    }
    return New-StepResult -Code 'none' -MessageKey 'setup.email.provider_none'
}

function Test-BackupTarget {
    # The engine's backup target rule (parent decision, TASK-0093): a drive letter, then 1 to 8
    # folder names of [A-Za-z0-9 ._-], no "." or "..", no name ending in a dot or a space, no
    # device name, at most 200 characters. Never a drive root.
    param([AllowNull()][string]$Target)
    if ((-not $Target) -or ($Target.Length -gt 200) -or ($Target -cnotmatch '^[A-Z]:\\(.+)$')) { return $false }
    $names = $Matches[1] -split '\\'
    if ($names.Count -gt 8) { return $false }
    $devices = @('CON', 'PRN', 'AUX', 'NUL') + @(0..9 | ForEach-Object { 'COM{0}' -f $_; 'LPT{0}' -f $_ })
    foreach ($name in $names) {
        if ($name -cnotmatch '^[A-Za-z0-9 ._-]{1,200}$') { return $false }
        if (($name -eq '.') -or ($name -eq '..') -or $name.EndsWith('.') -or $name.EndsWith(' ')) { return $false }
        if ($devices -contains ($name.Split('.')[0].TrimEnd(' ').ToUpperInvariant())) { return $false }
    }
    return $true
}

function Get-BackupTargetProblem {
    # SC-9: the backup target is never the data folder, a folder that contains it, or a folder
    # inside it. Returns '' or the code.
    param([Parameter(Mandatory = $true)][string]$Target, [string]$DataRoot = '')
    if (-not (Test-BackupTarget $Target)) { return 'backup_target_invalid' }
    if ($DataRoot) {
        $t = $Target.TrimEnd('\') + '\'
        $d = $DataRoot.TrimEnd('\') + '\'
        if ($t.StartsWith($d, [System.StringComparison]::OrdinalIgnoreCase) -or $d.StartsWith($t, [System.StringComparison]::OrdinalIgnoreCase)) { return 'backup_target_overlaps_data' }
    }
    return ''
}

function Test-BackupDrive {
    # S10 Next and M03: the drive is there, writable and has the free space, without a backup
    # (a backup stops Slate Operations for everyone). A file is made and removed at the drive
    # root; nothing else changes.
    param([Parameter(Mandatory = $true)][string]$Drive)
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $Drive) -ErrorAction SilentlyContinue
    if (-not $disk) { return New-StepResult -Code 'drive_missing' -MessageKey 'setup.backup.drive_missing' -Values @{ drive = $Drive } }
    $free = [long]$disk.FreeSpace
    $values = @{ drive = $Drive; free_gb = [int][math]::Floor([double]$free / 1GB) }
    $probe = '{0}\.slateops-check-{1}' -f $Drive, ([guid]::NewGuid().ToString('N').Substring(0, 8))
    try {
        $file = [System.IO.File]::Open($probe, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
        $file.Dispose()
        [System.IO.File]::Delete($probe)
    } catch {
        Write-RunLog 'setup.backup' 'WARN' ('{0} is not writable: {1}' -f $Drive, $_.Exception.Message)
        return New-StepResult -Code 'not_writable' -MessageKey 'setup.backup.not_writable' -Values $values
    }
    if ($free -lt $SlateOpsWizard.BackupMinBytes) { return New-StepResult -Code 'too_small' -MessageKey 'setup.backup.too_small' -Values $values }
    return New-StepResult -Code 'ready' -MessageKey 'setup.backup.ready' -Values $values
}

function Initialize-BackupFolder {
    # Plan 3.2 rule 4: <drive>:\SlateOps-backups, which the service account can write. A new
    # folder on NTFS gets its access list in the creating call (Administrators, SYSTEM, the
    # account); an existing folder that is not a link gets the account's entry once. Other file
    # systems (a FAT USB drive) have no access lists; the engine mounts them with the account's
    # rights (plan 8.2). Runs before the install answers are sent.
    param([Parameter(Mandatory = $true)][string]$Drive, [Parameter(Mandatory = $true)][string]$DataRoot, [string]$ServiceSid = '')
    $target = '{0}\{1}' -f $Drive, $SlateOpsWizard.BackupFolder
    $problem = Get-BackupTargetProblem -Target $target -DataRoot $DataRoot
    if ($problem) { return New-StepResult -Code $problem -MessageKey ('setup.backup.{0}' -f $problem) }
    if (-not $ServiceSid) { return New-StepResult -Code 'account_missing' -MessageKey 'setup.account.missing' }
    $check = Test-BackupDrive -Drive $Drive
    if ($check.code -ne 'ready') { return $check }
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $Drive)
    $ntfs = ([string]$disk.FileSystem -eq 'NTFS')
    $item = Get-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
    if ($item -and (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or -not $item.PSIsContainer)) {
        return New-StepResult -Code 'backup_target_unsafe' -MessageKey 'setup.backup.backup_target_unsafe'
    }
    $sid = New-Object System.Security.Principal.SecurityIdentifier($ServiceSid)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'Modify, Synchronize', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
    if (-not $item) {
        if ($ntfs) {
            $security = Get-ProtectedDirectorySecurity
            $security.AddAccessRule($rule)
            [void][System.IO.Directory]::CreateDirectory($target, $security)
        } else { [void][System.IO.Directory]::CreateDirectory($target) }
        Write-RunLog 'setup.backup' 'INFO' ('backup folder {0} created ({1})' -f $target, [string]$disk.FileSystem)
    } elseif ($ntfs) {
        $acl = Get-Acl -LiteralPath $target
        $has = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]) | Where-Object { $_.IdentityReference.Value -eq $ServiceSid }).Count -gt 0
        if (-not $has) { $acl.AddAccessRule($rule); Set-Acl -LiteralPath $target -AclObject $acl }
        Write-RunLog 'setup.backup' 'INFO' ('backup folder {0} kept; the account entry is present' -f $target)
    }
    return New-StepResult -Code 'ready' -MessageKey 'setup.backup.ready' -Values @{ target = $target }
}

function Get-PrinterFact {
    # Printers for "Print the key" (spec S14). A printer that writes a file is marked, so the
    # wizard refuses it (W80-3). The key itself never reaches this script.
    $out = @()
    foreach ($printer in @(Get-CimInstance -ClassName Win32_Printer -ErrorAction SilentlyContinue)) {
        $port = [string]$printer.PortName
        $driver = [string]$printer.DriverName
        $file = ($SlateOpsWizard.FilePorts -contains $port.ToUpperInvariant()) -or ($port -match '\.[A-Za-z]{2,4}$') -or ($driver -match $SlateOpsWizard.FileDrivers)
        $out += [ordered]@{ name = [string]$printer.Name; default = [bool]$printer.Default; writes_file = [bool]$file }
    }
    return $out
}

function Test-HttpsFromWindows {
    # Plan 10.3 F2 and W8-3: the product's Private firewall rule exists, then
    # https://<name>.local/api/health opens from Windows with the normal certificate checks
    # (through the hosts entry). The name is this PC's DNS host name, never an input.
    $rule = Get-NetFirewallRule -Name $SlateOps.FirewallRuleName -ErrorAction SilentlyContinue
    if ((-not $rule) -or ([string]$rule.Profile -notmatch 'Private')) { return New-StepResult -Code 'firewall_missing' -MessageKey 'install.f2.firewall_missing' }
    $hostName = ([string](Get-CimInstance -ClassName Win32_ComputerSystem).DNSHostName).ToLowerInvariant()
    $url = 'https://{0}.local/api/health' -f $hostName
    $last = ''
    for ($try = 1; $try -le 3; $try++) {
        try {
            $request = [System.Net.HttpWebRequest]::Create($url)
            $request.Timeout = 20000
            $request.AllowAutoRedirect = $false
            $response = $request.GetResponse()
            $status = [int]$response.StatusCode
            $response.Dispose()
            Write-RunLog 'install.f2' 'INFO' ('{0}: HTTP {1}' -f $url, $status)
            if ($status -eq 200) { return New-StepResult -Code 'ok' -MessageKey 'install.f2.ok' -Values @{ url = $url } }
            $last = 'http_{0}' -f $status
        } catch [System.Net.WebException] {
            $last = 'connection'
            if (@('TrustFailure', 'SecureChannelFailure') -contains [string]$_.Exception.Status) { $last = 'certificate' }
            Write-RunLog 'install.f2' 'WARN' ('{0}: try {1}, {2} ({3})' -f $url, $try, $last, $_.Exception.Message)
        }
        if ($try -lt 3) { Start-Sleep -Seconds 10 }
    }
    return New-StepResult -Code 'https_failed' -MessageKey 'install.f2.https_failed' -Values @{ reason = $last }
}
