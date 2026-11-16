<#
00-precheck.ps1 - checks whether this PC can run the Slate Operations WSL2 boot test.

It changes nothing on the PC. It writes only its own log, to %TEMP% (so it creates nothing
under C:\ProgramData; with -WhatIf it writes no log either).
It reports: Windows edition and build (FAIL below build 22621 = Windows 11 22H2, which
mirrored networking needs), virtualization and SLAT, RAM, free disk, WSL state and version,
existing WSL distributions, Docker Desktop, the LAN IPv4 address and its network category,
power and Fast Startup settings, and whether TCP port 8443 is free.

Run in Windows PowerShell opened with "Run as administrator":
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\00-precheck.ps1
Exit code: 0 when nothing FAILs, 1 when a check FAILs.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    # The memory that setup will give the WSL VM; used for the RAM check.
    [ValidateRange(2, 64)][int]$WslMemoryGB = 6
)

. (Join-Path $PSScriptRoot 'lib\common.ps1')

$script:failures = 0
$script:warnings = 0
function Report {
    param([string]$Level, [string]$Message)
    if ($Level -eq 'FAIL') { $script:failures++ }
    if ($Level -eq 'WARN') { $script:warnings++ }
    Write-KitLog $Message $Level
}

try {
    Assert-Administrator
    Initialize-BootTestLog -Name 'slateops-boottest-00-precheck' -DryRun:([bool]$WhatIfPreference) -Directory $env:TEMP
    Write-KitLog 'Slate Operations WSL2 boot test: precheck (changes nothing).' 'STEP'

    # Windows edition and build
    $win = Get-WindowsInfo
    $text = '{0}, edition {1}, version {2}, build {3}.{4}' -f $win.Caption, $win.EditionId, $win.DisplayVersion, $win.Build, $win.Ubr
    if ($win.Build -lt $BootTest.MinBuild) {
        Report 'FAIL' ('Windows: {0}. Build {1} or later (Windows 11 22H2) is needed for mirrored networking.' -f $text, $BootTest.MinBuild)
    } elseif ($win.EditionId -notmatch '^(Professional|Enterprise|Education)') {
        Report 'WARN' ('Windows: {0}. The kit is tested for Windows 11 Pro only; this edition is untested.' -f $text)
    } else {
        Report 'PASS' ('Windows: {0}.' -f $text)
    }
    Write-KitLog ('Last Windows boot (UTC): {0}' -f (Get-UtcStamp -Time $win.LastBoot))

    # Architecture
    $arch = Get-Architecture
    if ($BootTest.WslMsi.ContainsKey($arch)) { Report 'PASS' ('Processor architecture: {0}.' -f $arch) }
    else { Report 'FAIL' ('Processor architecture {0} is not supported (AMD64 or ARM64 only).' -f $arch) }

    # Virtualization and SLAT
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $cpu = @(Get-CimInstance -ClassName Win32_Processor)[0]
    if ($cs.HypervisorPresent) {
        Report 'PASS' 'Virtualization: a hypervisor already runs, so virtualization and SLAT are on.'
    } elseif ($cpu.VirtualizationFirmwareEnabled -and $cpu.SecondLevelAddressTranslationExtensions) {
        Report 'PASS' 'Virtualization: on in firmware; SLAT: supported.'
    } else {
        Report 'FAIL' ('Virtualization in firmware: {0}; SLAT: {1}. Turn on virtualization (Intel VT-x or AMD-V/SVM) in the UEFI/BIOS settings.' -f $cpu.VirtualizationFirmwareEnabled, $cpu.SecondLevelAddressTranslationExtensions)
    }

    # Memory
    $ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    if ($ramGB -lt ($WslMemoryGB + 2)) {
        Report 'FAIL' ('RAM: {0} GB. Setup gives the WSL VM {1} GB; that leaves too little for Windows. Use -WslMemoryGB with a smaller value.' -f $ramGB, $WslMemoryGB)
    } elseif ($ramGB -lt ($WslMemoryGB + 4)) {
        Report 'WARN' ('RAM: {0} GB. The WSL VM gets {1} GB; Windows keeps less than 4 GB.' -f $ramGB, $WslMemoryGB)
    } else {
        Report 'PASS' ('RAM: {0} GB (the WSL VM gets {1} GB).' -f $ramGB, $WslMemoryGB)
    }

    # Disk
    $systemDrive = $env:SystemDrive
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $systemDrive)
    $freeGB = [math]::Round($disk.FreeSpace / 1GB, 1)
    if ($freeGB -lt $BootTest.MinFreeDiskGB) { Report 'FAIL' ('Free disk on {0}: {1} GB. Need at least {2} GB.' -f $systemDrive, $freeGB, $BootTest.MinFreeDiskGB) }
    else { Report 'PASS' ('Free disk on {0}: {1} GB.' -f $systemDrive, $freeGB) }

    # Windows features and WSL
    $vmp = Get-OptionalFeatureState -Name 'VirtualMachinePlatform'
    Write-KitLog ('Windows feature VirtualMachinePlatform: {0} (setup enables it when it is off).' -f $vmp)
    $wslFeature = Get-OptionalFeatureState -Name 'Microsoft-Windows-Subsystem-Linux'
    Write-KitLog ('Windows feature Microsoft-Windows-Subsystem-Linux (WSL 1 only, not needed): {0}' -f $wslFeature)
    $wslVersion = Get-WslVersion
    if ($null -eq $wslVersion) {
        Report 'INFO' ('WSL package: not installed. Setup installs WSL {0} from the offline MSI.' -f $BootTest.WslVersion)
    } else {
        if ($wslVersion -lt $BootTest.WslVersion) {
            Report 'INFO' ('WSL package: {0}. Setup upgrades it to the pinned {1}.' -f $wslVersion, $BootTest.WslVersion)
        } elseif ($wslVersion -gt $BootTest.WslVersion) {
            Report 'WARN' ('WSL package: {0}, newer than the pinned {1}. Setup keeps it. Event E6 (wsl --update) then has an update only if a newer stable WSL exists.' -f $wslVersion, $BootTest.WslVersion)
        } else {
            Report 'PASS' ('WSL package: {0} (the pinned version).' -f $wslVersion)
        }
        Invoke-Wsl -ArgumentList @('--version') -NoThrow | Out-Null
        Write-KitLog 'WSL distributions of this account (wsl --list --verbose):'
        Invoke-Wsl -ArgumentList @('--list', '--verbose') -NoThrow | Out-Null
    }
    $lxss = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
    if (Test-Path -LiteralPath $lxss) {
        $names = @(Get-ChildItem -LiteralPath $lxss | ForEach-Object { (Get-ItemProperty -LiteralPath $_.PSPath).DistributionName })
        Write-KitLog ('Registered distributions of this account: {0}' -f ($(if ($names.Count) { $names -join ', ' } else { 'none' })))
    } else {
        Write-KitLog 'Registered distributions of this account: none.'
    }
    $userWslConfig = Join-Path $env:USERPROFILE '.wslconfig'
    Write-KitLog ('Your own {0}: {1} (the kit never changes it).' -f $userWslConfig, $(if (Test-Path -LiteralPath $userWslConfig) { 'exists' } else { 'absent' }))

    # Docker Desktop
    $dockerDesktop = (Test-Path -LiteralPath (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')) -or [bool](Get-Service -Name 'com.docker.service' -ErrorAction SilentlyContinue)
    if ($dockerDesktop) { Report 'WARN' 'Docker Desktop: installed. The test uses Docker Engine inside its own distribution; quit Docker Desktop during the test so it does not use port 8443 or memory.' }
    else { Report 'PASS' 'Docker Desktop: not installed.' }

    # Network
    $lan = Get-LanInfo
    if ($null -eq $lan) {
        Report 'FAIL' 'LAN: no connected network adapter with an IPv4 default gateway.'
    } else {
        $lanText = '{0} on "{1}", network {2}, network name "{3}"' -f $lan.Address, $lan.InterfaceAlias, $lan.Cidr, $lan.NetworkName
        if ($lan.Category -eq 'Private') {
            Report 'PASS' ('LAN: {0}, category {1}.' -f $lanText, $lan.Category)
        } elseif ($lan.Category -eq 'DomainAuthenticated') {
            Report 'FAIL' ('LAN: {0}, category DomainAuthenticated (a company domain network). The kit opens its port on Private networks only and is not tested on domain networks.' -f $lanText)
        } else {
            Report 'FAIL' ('LAN: {0}, category {1}. The firewall rules apply to Private networks only. Set this network to Private: Settings > Network & internet > (your network) > Network profile type > Private network.' -f $lanText, $lan.Category)
        }
        if ($lan.AdapterCount -gt 1) { Report 'WARN' ('{0} adapters have a default gateway; the kit uses "{1}".' -f $lan.AdapterCount, $lan.InterfaceAlias) }
        Write-KitLog ('Status URL for another LAN device after setup: http://{0}:{1}/' -f $lan.Address, $BootTest.Port)
    }

    # Port
    if (Test-PortListening) {
        $ours = [bool](Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.StartTaskName -ErrorAction SilentlyContinue)
        if ($ours) { Report 'INFO' ('TCP port {0}: in use, and the kit is already set up (expected).' -f $BootTest.Port) }
        else { Report 'FAIL' ('TCP port {0}: another program listens on it.' -f $BootTest.Port) }
    } else {
        Report 'PASS' ('TCP port {0}: free.' -f $BootTest.Port)
    }

    # Power
    $battery = @(Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue)
    if ($battery.Count -gt 0) { Report 'WARN' 'This PC has a battery. Keep it on mains power for the whole test; a power cut (E3) does not stop a laptop.' }
    $sleep = Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/query', 'SCHEME_CURRENT', 'SUB_SLEEP', 'STANDBYIDLE') -NoThrow -Quiet
    $hex = @($sleep.Output | ForEach-Object { if ($_ -match '0x([0-9a-fA-F]{8})\s*$') { $Matches[1] } })
    if ($hex.Count -ge 2) {
        $acSeconds = [Convert]::ToInt64($hex[$hex.Count - 2], 16)
        Write-KitLog ('Sleep after (on mains power): {0}. Setup sets it to never and cleanup restores it.' -f $(if ($acSeconds -eq 0) { 'never' } else { '{0} min' -f [math]::Round($acSeconds / 60) }))
    }
    $standby = Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/a') -NoThrow -Quiet
    if (@($standby.Output | Where-Object { $_ -match 'S0' }).Count -gt 0) { Write-KitLog 'This PC reports Modern Standby (S0) in "powercfg /a" output; see the README note on sleep.' }
    $power = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -ErrorAction SilentlyContinue
    $hiberboot = $null
    if ($power -and $power.PSObject.Properties['HiberbootEnabled']) { $hiberboot = $power.HiberbootEnabled }
    Write-KitLog ('Fast Startup (HiberbootEnabled): {0}. Event E5 needs it on; the kit does not change it.' -f $(if ($hiberboot -eq 1) { 'on' } elseif ($hiberboot -eq 0) { 'off' } else { 'unknown' }))
    if (Test-Path -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') {
        Report 'WARN' 'Windows has a restart pending. Restart before setup.'
    }

    # PowerShell logging policy: module logging records command parameters (the password).
    $policy = Get-PowerShellLoggingPolicy
    $covered = @(Get-PasswordModuleLogged)
    if ($covered.Count -gt 0) {
        Report 'FAIL' ('PowerShell module logging is on for {0} (policy module names: {1}). It would record the service account password. Setup stops while this policy is on.' -f ($covered -join ', '), ($policy.ModuleNames -join ', '))
    } elseif ($policy.ModuleLogging) {
        Report 'PASS' ('PowerShell module logging is on for: {0}. It does not cover the module that receives the password.' -f ($policy.ModuleNames -join ', '))
    } else {
        Report 'PASS' 'PowerShell module logging: off.'
    }
    Write-KitLog ('PowerShell script block logging: {0}; transcription: {1} (neither records the password).' -f $(if ($policy.ScriptBlockLogging) { 'on' } else { 'off' }), $(if ($policy.Transcription) { 'on' } else { 'off' }))

    # Earlier kit runs
    if (Test-Path -LiteralPath $BootTest.Root) {
        $problems = @(Get-BootTestTreeProblem)
        if ($problems.Count -gt 0) { Report 'FAIL' ('{0} exists and fails the safety check: {1}. Delete the folder, then run setup.' -f $BootTest.Root, ($problems -join '; ')) }
        else { Write-KitLog ('{0} exists (from an earlier setup) and passes the safety check.' -f $BootTest.Root) }
    }
    if (Get-ServiceAccount) { Write-KitLog ('Account {0}: exists (from an earlier setup).' -f $BootTest.AccountName) }
    if (Get-ScheduledTask -TaskPath $BootTest.TaskPath -ErrorAction SilentlyContinue) { Write-KitLog ('Scheduled tasks under {0}: exist (from an earlier setup).' -f $BootTest.TaskPath) }

    Write-KitLog ('Result: {0} FAIL, {1} WARN.' -f $script:failures, $script:warnings) $(if ($script:failures) { 'FAIL' } else { 'PASS' })
    if ($script:failures) { exit 1 }
    exit 0
} catch {
    Write-KitLog ('Precheck stopped: {0}' -f $_.Exception.Message) 'ERROR'
    Write-KitLog ($_.InvocationInfo.PositionMessage) 'ERROR'
    exit 1
}
