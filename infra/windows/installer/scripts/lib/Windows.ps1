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
    # the free space, at least 16 GB and at most 1024 GB (the WSL default is 1 TB). Proposed.
    param([Parameter(Mandatory = $true)][long]$FreeBytes)
    $size = [long][math]::Floor(([double]$FreeBytes * 0.9) / 1GB)
    if ($size -lt 16) { return 16 }
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
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$SourceDir, [Parameter(Mandatory = $true)][string[]]$Names)
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
    return ('"{0}" "{1}"' -f (Join-Path $env:SystemRoot 'explorer.exe'), $SetupPath)
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

function Get-SetupEntry {
    # Spec 4.1: the first screen from Windows-side records only. Installed versions are W8's
    # (M01, M05); this covers the saved progress.
    param([AllowNull()][System.Collections.IDictionary]$Progress)
    if ($null -eq $Progress) { return @{ screen = 'S01'; next = '' } }
    switch ([string](Get-DictValue $Progress 'stage')) {
        'check_restart'    { return @{ screen = 'S02'; next = ''; welcome_back = $true } }
        'feature_restart'  { return @{ screen = 'S06'; next = 'S07' } }
        'continue_later'   { return @{ screen = 'S06'; next = 'S08' } }
        'install_started'  {
            if ((Get-DictValue $Progress 'email_discarded') -eq $true) { return @{ screen = 'S06'; next = 'S09' } }
            return @{ screen = 'S06'; next = 'S12' }
        }
        'install_finished' { return @{ screen = 'S06'; next = 'S14'; new_recovery_key = $true } }
        'key_saved'        { return @{ screen = 'M01'; next = '' } }
    }
    return @{ screen = 'S01'; next = '' }
}

function Register-SetupResume {
    # The RunOnce entry and the desktop shortcut, both starting the original setup file (N-1).
    param([Parameter(Mandatory = $true)][string]$SetupPath)
    $command = Get-ResumeCommand -SetupPath $SetupPath
    if (-not (Test-Path -LiteralPath $SlateOpsResume.RunOnceKey)) { New-Item -Path $SlateOpsResume.RunOnceKey -Force | Out-Null }
    New-ItemProperty -LiteralPath $SlateOpsResume.RunOnceKey -Name $SlateOpsResume.RunOnceName -PropertyType String -Value $command -Force | Out-Null
    $shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) $SlateOpsResume.ShortcutName
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
    # Cancel; S07 removes the shortcut when it opens, plan F4a).
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
    $msiLog = Join-Path (Join-Path $Layout.Logs 'setup') ('wsl-msi-{0}.log' -f (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))
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
    if ($Cidr -notmatch '^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$') { throw 'Not an IPv4 network.' }
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
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$HostName)
    $path = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
    $existing = ''
    if (Test-Path -LiteralPath $path) { $existing = [System.IO.File]::ReadAllText($path) }
    $content = Get-HostsContent -Existing $existing -HostName $HostName
    if ($content -ne $existing) { [System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::ASCII) }
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
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
    $store.Open('ReadWrite')
    try { $store.Add($certificate) } finally { $store.Close() }
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
        if ($null -eq $record[$setting.key]) { continue }
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
    $kit = $SlateOpsCheck.Kit
    $tree = @{ Root = $kit.Root; Entries = [ordered]@{ 'kit' = 'read'; 'cache' = 'read'; 'state' = 'read'; 'logs' = 'none'; 'svc-out' = 'modify'; 'distro' = 'modify' } }
    $account = Get-LocalUser -Name $kit.AccountName -ErrorAction SilentlyContinue
    $sid = $(if ($account) { $account.SID.Value } else { '' })
    $problems = @(Get-TreeProblem -Tree $tree -ServiceSid $sid)
    if ($problems.Count -gt 0) { Write-RunLog 'check.c29' 'WARN' ('the kit folder fails the safety check: {0}' -f ($problems -join '; ')); return $false }
    $task = Get-ScheduledTask -TaskPath $kit.TaskPath -TaskName 'Exec' -ErrorAction SilentlyContinue
    if ((-not $task) -or (-not $account)) { return $false }
    $requestId = [guid]::NewGuid().ToString()
    [System.IO.File]::WriteAllText((Join-Path $kit.Root 'state\request.txt'), ('unregister {0}' -f $requestId), [System.Text.Encoding]::ASCII)
    Start-ScheduledTask -TaskPath $kit.TaskPath -TaskName 'Exec'
    $resultFile = Join-Path $kit.Root 'svc-out\svc-exec-result.json'
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
    # sign-in entry, profile, account; rights by SID; the kit folder without its logs. The kit's
    # power settings are restored only from a kit state file that passes the safety check.
    $kit = $SlateOpsCheck.Kit
    $step = 'check.c29.remove'
    $account = Get-LocalUser -Name $kit.AccountName -ErrorAction SilentlyContinue
    $sid = $(if ($account) { $account.SID.Value } else { '' })
    $tasks = @(Get-ScheduledTask -TaskPath $kit.TaskPath -ErrorAction SilentlyContinue)
    if ($tasks | Where-Object { $_.TaskName -eq 'Start' }) {
        Disable-ScheduledTask -TaskPath $kit.TaskPath -TaskName 'Start' | Out-Null
        Stop-ScheduledTask -TaskPath $kit.TaskPath -TaskName 'Start'
        Write-RunLog $step 'INFO' 'kit boot task disabled and stopped'
    }
    $vhdx = Join-Path $kit.Root 'distro\vhd\ext4.vhdx'
    $gone = Invoke-KitUnregister
    if ((-not $gone) -and (Test-Path -LiteralPath $vhdx)) {
        Write-RunLog $step 'WARN' 'the kit distribution is still registered; stopping the WSL service for a moment'
        Stop-Service -Name 'WSLService' -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
    }
    if ($account) { Disable-LocalUser -Name $kit.AccountName; Write-RunLog $step 'INFO' 'account disabled' }
    foreach ($task in $tasks) { Unregister-ScheduledTask -TaskPath $kit.TaskPath -TaskName $task.TaskName -Confirm:$false }
    if ($tasks.Count -gt 0) {
        $scheduler = New-Object -ComObject 'Schedule.Service'
        $scheduler.Connect()
        try { $scheduler.GetFolder('\').DeleteFolder('SlateOpsBootTest', 0) } catch { $null = $_ }
        Write-RunLog $step 'INFO' 'kit tasks removed'
    }
    Get-NetFirewallRule -Name $kit.RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Get-NetFirewallHyperVRule -Name $kit.HyperVRule -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule
    $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    Remove-ItemProperty -LiteralPath $userList -Name $kit.AccountName -ErrorAction SilentlyContinue
    if ($sid) {
        $userProfile = Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid) -ErrorAction SilentlyContinue
        if ($userProfile -and -not $userProfile.Loaded) { Remove-CimInstance -InputObject $userProfile }
    }
    if ($account) { Remove-LocalUser -Name $kit.AccountName; Write-RunLog $step 'INFO' 'account removed' }
    if ($sid) {
        Initialize-LsaRightsType
        [SlateOpsSetup.LsaRights]::Remove($sid, [string[]]$SlateOps.AccountRights)
    }
    if (Test-Path -LiteralPath $kit.Root) {
        foreach ($child in @(Get-ChildItem -LiteralPath $kit.Root -Force)) {
            if ($child.Name -ieq 'logs') { continue }
            Remove-PathNoFollow -Path $child.FullName
        }
        if ($sid) { $null = Invoke-Logged -Step $step -FilePath 'icacls.exe' -ArgumentList @($kit.Root, '/remove:g', ('*{0}' -f $sid)) -NoThrow }
        Write-RunLog $step 'INFO' 'kit folder removed; its logs stay'
    }
    $left = Get-LeftoverFact
    $remaining = @(@('account', 'kit_distro', 'kit_tasks', 'kit_rules') | Where-Object { $left[$_] })
    if ($remaining.Count -gt 0) { return New-StepResult -Code 'incomplete' -MessageKey 'check.c29.incomplete' -Values @{ remaining = $remaining } }
    return New-StepResult -Code 'removed' -MessageKey 'check.c29.removed'
}
