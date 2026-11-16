<#
10-setup.ps1 - sets up the Slate Operations WSL2 boot test on this PC.

Part 1 (as the owner, administrator):
  - checks the PC (build, virtualization, LAN category Private, disk, RAM, port 8443),
  - stops if PowerShell module logging would record the service account password,
  - makes C:\ProgramData\SlateOpsBootTest with an administrators-only ACL in one call (or, if it
    exists, stops unless the folder and everything in it passes the safety check), and copies
    the kit there,
  - downloads the pinned WSL MSI and Debian image and checks their SHA-256,
  - turns on the Windows feature VirtualMachinePlatform and installs WSL from the offline MSI.
  If Windows needs a restart, setup registers a one-time task that opens setup again at
  your next sign-in, tells you to restart, and stops.
Part 2:
  - sets "Sleep" on mains power to Never (cleanup restores the old value),
  - turns on the Task Scheduler event log (cleanup restores the old state),
  - creates the standard local account slateops-svc with a random password that is never
    written or shown, gives it "Log on as a batch job", denies interactive, Remote Desktop
    and network sign-in (not with -NoDenyRights), and hides it from the sign-in screen,
  - registers the on-demand task \SlateOpsBootTest\Exec and runs the "prepare" job as
    slateops-svc: .wslconfig, Debian import, systemd, Docker Engine, test stack,
  - registers the boot task \SlateOpsBootTest\Start (At startup, as slateops-svc),
  - adds the two firewall rules for TCP 8443 (Windows Defender Firewall and Hyper-V firewall),
  - starts the boot task and waits until http://127.0.0.1:8443/ answers. If this PC cannot
    reach it, setup warns and tells you to check from another device; it does not fail.
Run it again at any time: every step checks what exists. A new run gives the account a new
password and registers the tasks again.

Run in Windows PowerShell opened with "Run as administrator":
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\10-setup.ps1
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\10-setup.ps1 -WhatIf
-WhatIf shows each change and makes none (and writes no log file).
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    # Memory for the WSL VM of slateops-svc (.wslconfig memory=).
    [ValidateRange(2, 64)][int]$WslMemoryGB = 6,
    # bridge: Docker publishes port 8443 (the product's shape). host: the web container uses
    # the host network, the workaround that WSL documents for a known Docker issue with
    # published ports in mirrored mode. Use host only if bridge fails the LAN check.
    [ValidateSet('bridge', 'host')][string]$WebNetwork = 'bridge',
    # Do not give the deny sign-in rights. Use it only if the tasks fail with a logon error
    # (for example 0x80070569) and record that as a finding.
    [switch]$NoDenyRights
)

. (Join-Path $PSScriptRoot 'lib\common.ps1')

$dryRun = [bool]$WhatIfPreference
$powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

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

function Register-ResumeTask {
    $owner = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    # -Command "& '<script>'" (not -File): the script ends with "exit", which would close a -File
    # host even with -NoExit. With -Command the window stays open, so you can read the result.
    $argument = ('-NoProfile -ExecutionPolicy Bypass -NoExit -Command "& ''{0}'' -WslMemoryGB {1} -WebNetwork {2}{3}"' -f (Join-Path $BootTest.Kit '10-setup.ps1'), $WslMemoryGB, $WebNetwork, $(if ($NoDenyRights) { ' -NoDenyRights' } else { '' }))
    Invoke-Step ('Register a one-time task: open setup again at the next sign-in of {0}' -f $owner) {
        $action = New-ScheduledTaskAction -Execute $powershellExe -Argument $argument
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $owner
        $principal = New-ScheduledTaskPrincipal -UserId $owner -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
        Register-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.ResumeTaskName -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings -Force -Description 'Slate Operations boot test: continue setup after the restart. Setup deletes this task.' | Out-Null
    }
}

function Get-PowerIndex {
    param([string]$Scheme, [string]$Setting)
    $query = Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/query', $Scheme, 'SUB_SLEEP', $Setting) -NoThrow -Quiet
    if ($query.ExitCode -ne 0) { return $null }
    $hex = @($query.Output | ForEach-Object { if ($_ -match '0x([0-9a-fA-F]{8})\s*$') { $Matches[1] } })
    if ($hex.Count -lt 2) { return $null }
    return [Convert]::ToInt64($hex[$hex.Count - 2], 16)
}

function Get-ActivePowerScheme {
    $active = Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/getactivescheme') -Quiet
    $match = [regex]::Match(($active.Output -join ' '), '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
    if (-not $match.Success) { throw 'Could not read the active power plan.' }
    return $match.Value
}

try {
    Assert-Administrator
    Initialize-BootTestLog -Name '10-setup' -DryRun:$dryRun
    Write-KitLog ('Slate Operations WSL2 boot test: setup (WSL memory {0} GB, web network {1}, deny rights {2}).' -f $WslMemoryGB, $WebNetwork, $(if ($NoDenyRights) { 'off' } else { 'on' })) 'STEP'
    if ($dryRun) { Write-KitLog 'Dry run (-WhatIf): nothing changes.' 'WHATIF' }

    # PowerShell module logging records cmdlet parameters; Register-ScheduledTask receives the
    # service account password as a parameter. Stop before anything changes.
    $logged = @(Get-PasswordModuleLogged)
    if ($logged.Count -gt 0) {
        throw ('PowerShell module logging is on for {0} (group policy "Turn on Module Logging"). It would record the service account password in the event log. Turn the policy off or remove {0} from its module names, then run setup again.' -f ($logged -join ', '))
    }

    # ---------------- Part 1: checks ----------------
    $win = Get-WindowsInfo
    if ($win.Build -lt $BootTest.MinBuild) { throw ('Windows build {0} is below {1} (Windows 11 22H2).' -f $win.Build, $BootTest.MinBuild) }
    Write-KitLog ('Windows {0} build {1}.{2} ({3}).' -f $win.DisplayVersion, $win.Build, $win.Ubr, $win.EditionId)
    $arch = Get-Architecture
    if (-not $BootTest.WslMsi.ContainsKey($arch)) { throw ('Architecture {0} is not supported.' -f $arch) }
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $cpu = @(Get-CimInstance -ClassName Win32_Processor)[0]
    if (-not ($cs.HypervisorPresent -or ($cpu.VirtualizationFirmwareEnabled -and $cpu.SecondLevelAddressTranslationExtensions))) {
        throw 'Virtualization or SLAT is off. Turn on virtualization in the UEFI/BIOS settings, then run setup again.'
    }
    if (($cs.TotalPhysicalMemory / 1GB) -lt ($WslMemoryGB + 2)) { throw ('Too little RAM for a {0} GB WSL VM. Use -WslMemoryGB with a smaller value.' -f $WslMemoryGB) }
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $env:SystemDrive)
    if (($disk.FreeSpace / 1GB) -lt $BootTest.MinFreeDiskGB) { throw ('Less than {0} GB free on {1}.' -f $BootTest.MinFreeDiskGB, $env:SystemDrive) }
    $lan = Get-LanInfo
    if ($null -eq $lan) { throw 'No connected LAN adapter with an IPv4 default gateway.' }
    if ($lan.Category -eq 'DomainAuthenticated') {
        throw ('The network "{0}" is a company domain network. The kit opens its port on Private networks only and is not tested on domain networks.' -f $lan.NetworkName)
    }
    if ($lan.Category -ne 'Private') {
        throw ('The network "{0}" is {1}. Set it to Private (Settings > Network & internet > your network > Private network), then run setup again. The kit does not change it for you.' -f $lan.NetworkName, $lan.Category)
    }
    Write-KitLog ('LAN: {0} on "{1}" ({2}, {3}).' -f $lan.Address, $lan.InterfaceAlias, $lan.Cidr, $lan.Category)
    $startTaskExists = [bool](Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.StartTaskName -ErrorAction SilentlyContinue)
    if ((Test-PortListening) -and (-not $startTaskExists)) { throw ('Another program listens on TCP port {0}.' -f $BootTest.Port) }

    # ---------------- Part 1: folder, ACL, kit copy ----------------
    # The resume task runs kit\10-setup.ps1 with highest privileges, and the MSI and state file
    # live here, so no other user may own or plant anything in this folder.
    if (Test-Path -LiteralPath $BootTest.Root) {
        $problems = @(Get-BootTestTreeProblem)
        if ($problems.Count -gt 0) {
            throw ('{0} fails the safety check: {1}. Run 90-cleanup.ps1, or delete the folder, then run setup again.' -f $BootTest.Root, ($problems -join '; '))
        }
        Write-KitLog ('{0} exists and passes the safety check.' -f $BootTest.Root) 'PASS'
    }
    Invoke-Step ('Create {0} with access for Administrators and SYSTEM only (set in the same call that creates it)' -f $BootTest.Root) {
        $null = Initialize-BootTestRoot
        # Checked again after the create: another user could have created the root between the
        # test above and the create call; then CreateDirectory keeps that folder unchanged.
        $problems = @(Get-BootTestTreeProblem)
        if ($problems.Count -gt 0) { throw ('{0} fails the safety check: {1}.' -f $BootTest.Root, ($problems -join '; ')) }
        foreach ($dir in @($BootTest.Kit, $BootTest.Cache, $BootTest.Distro, $BootTest.State, $BootTest.Logs, $BootTest.SvcOut)) {
            if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
        }
    }
    if (-not ($PSScriptRoot.TrimEnd('\') -ieq $BootTest.Kit.TrimEnd('\'))) {
        Invoke-Step ('Copy the kit from {0} to {1}' -f $PSScriptRoot, $BootTest.Kit) {
            foreach ($child in @(Get-ChildItem -LiteralPath $BootTest.Kit -Force)) { Remove-PathNoFollow -Path $child.FullName }
            Copy-Item -Path (Join-Path $PSScriptRoot '*') -Destination $BootTest.Kit -Recurse -Force
        }
    }
    if (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.ResumeTaskName -ErrorAction SilentlyContinue) {
        Invoke-Step 'Remove the one-time resume task' { Unregister-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.ResumeTaskName -Confirm:$false }
    }

    $state = Read-BootTestState
    if (-not $state.ContainsKey('created_at')) { $state['created_at'] = Get-UtcStamp }
    $state['owner'] = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $state['wsl_memory_gb'] = $WslMemoryGB
    $state['web_network'] = $WebNetwork
    $state['lan_address'] = $lan.Address
    $state['lan_cidr'] = $lan.Cidr
    Save-BootTestState -State $state

    # ---------------- Part 1: downloads ----------------
    $downloads = @(
        @{ Name = 'WSL MSI'; Url = $BootTest.WslMsi[$arch].Url; Sha256 = $BootTest.WslMsi[$arch].Sha256; File = (Join-Path $BootTest.Cache ('wsl.{0}.{1}.msi' -f $BootTest.WslVersion, $arch.ToLowerInvariant())) },
        @{ Name = 'Debian image'; Url = $BootTest.Rootfs[$arch].Url; Sha256 = $BootTest.Rootfs[$arch].Sha256; File = (Join-Path $BootTest.Cache ('debian-{0}.wsl' -f $arch.ToLowerInvariant())) }
    )
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    foreach ($download in $downloads) {
        $haveGood = $false
        if (Test-Path -LiteralPath $download.File) {
            $haveGood = ((Get-FileHash -LiteralPath $download.File -Algorithm SHA256).Hash.ToLowerInvariant() -eq $download.Sha256)
        }
        if ($haveGood) { Write-KitLog ('{0}: cached file {1} has the pinned SHA-256.' -f $download.Name, $download.File); continue }
        Invoke-Step ('Download {0} from {1}' -f $download.Name, $download.Url) {
            Invoke-WebRequest -Uri $download.Url -OutFile $download.File -UseBasicParsing
            $hash = (Get-FileHash -LiteralPath $download.File -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($hash -ne $download.Sha256) {
                Remove-Item -LiteralPath $download.File -Force
                throw ('SHA-256 mismatch for {0}: got {1}, expected {2}. The file was deleted.' -f $download.Name, $hash, $download.Sha256)
            }
            Write-KitLog ('  SHA-256 {0} matches the pinned value.' -f $hash) 'PASS'
        }
    }

    # ---------------- Part 1: Windows feature and WSL ----------------
    $restartNeeded = $false
    $vmp = Get-OptionalFeatureState -Name 'VirtualMachinePlatform'
    Write-KitLog ('VirtualMachinePlatform: {0}.' -f $vmp)
    if ($vmp -eq 'Disabled') {
        $state['vmp_enabled_by_setup'] = $true
        Save-BootTestState -State $state
        Invoke-Step 'Enable the Windows feature VirtualMachinePlatform' {
            $result = Enable-WindowsOptionalFeature -Online -FeatureName 'VirtualMachinePlatform' -All -NoRestart
            if ($result.RestartNeeded) { Write-KitLog '  Windows needs a restart for this feature.' }
        } | Out-Null
        $restartNeeded = $true
    } elseif ($vmp -eq 'EnablePending') {
        $restartNeeded = $true
    } elseif ($vmp -ne 'Enabled') {
        throw ('VirtualMachinePlatform has the unexpected state {0}.' -f $vmp)
    }

    $wslVersion = Get-WslVersion
    if (($null -eq $wslVersion) -or ($wslVersion -lt $BootTest.WslVersion)) {
        if (-not $state.ContainsKey('wsl_version_before_setup')) {
            $state['wsl_version_before_setup'] = $(if ($null -eq $wslVersion) { 'none' } else { $wslVersion.ToString() })
            Save-BootTestState -State $state
        }
        $msiLog = Join-Path $BootTest.Logs 'wsl-msi-install.log'
        $msiCode = Invoke-Step ('Install WSL {0} from the offline MSI (log {1})' -f $BootTest.WslVersion, $msiLog) {
            # Check the hash again right before the install. The file is in cache, which only
            # administrators and SYSTEM can write.
            $hash = (Get-FileHash -LiteralPath $downloads[0].File -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($hash -ne $downloads[0].Sha256) { throw ('SHA-256 mismatch for {0} right before the install: {1}.' -f $downloads[0].File, $hash) }
            Write-KitLog ('  SHA-256 {0} checked again right before msiexec.' -f $hash) 'PASS'
            $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', ('"{0}"' -f $downloads[0].File), '/qn', '/norestart', '/l*v', ('"{0}"' -f $msiLog)) -Wait -PassThru
            $process.ExitCode
        }
        if (-not $dryRun) {
            if ($msiCode -eq 3010) { $restartNeeded = $true; Write-KitLog '  The MSI asks for a restart (exit code 3010).' }
            elseif ($msiCode -ne 0) { throw ('The WSL MSI failed with exit code {0}. Read {1}.' -f $msiCode, $msiLog) }
        }
    } else {
        Write-KitLog ('WSL {0} is installed (pinned {1} or later); MSI skipped.' -f $wslVersion, $BootTest.WslVersion)
    }

    if ($restartNeeded) {
        Register-ResumeTask
        Write-KitLog 'Part 1 is done. Windows must restart before part 2.' 'WARN'
        Write-KitLog 'Do this now: 1) Save your work. 2) Restart the PC (Start > Power > Restart). 3) Sign in. Setup opens again in a new window.' 'WARN'
        if (-not $dryRun) { exit 0 }
        Write-KitLog 'Dry run: the steps after the restart follow.' 'WHATIF'
    }

    # ---------------- Part 2 ----------------
    if (-not $dryRun) {
        if ((Get-OptionalFeatureState -Name 'VirtualMachinePlatform') -ne 'Enabled') { throw 'VirtualMachinePlatform is not enabled yet. Restart Windows and run setup again.' }
        $wslVersion = Get-WslVersion
        if (($null -eq $wslVersion) -or ($wslVersion -lt $BootTest.MinWslVersion)) { throw ('WSL {0} or later is needed; found {1}.' -f $BootTest.MinWslVersion, $wslVersion) }
        Invoke-Wsl -ArgumentList @('--version') -NoThrow | Out-Null
    }

    # Power: keep the PC awake on mains power. A sleeping PC cannot serve the LAN.
    $scheme = Get-ActivePowerScheme
    if (-not $state.ContainsKey('power_scheme')) {
        $state['power_scheme'] = $scheme
        $state['power_standby_ac_seconds'] = Get-PowerIndex -Scheme $scheme -Setting 'STANDBYIDLE'
        $state['power_hibernate_ac_seconds'] = Get-PowerIndex -Scheme $scheme -Setting 'HIBERNATEIDLE'
        Save-BootTestState -State $state
    }
    Write-KitLog ('Power plan {0}: sleep on mains power was {1} s, hibernate {2} s (0 = never).' -f $state['power_scheme'], $state['power_standby_ac_seconds'], $state['power_hibernate_ac_seconds'])
    Invoke-Step 'Set Sleep and Hibernate on mains power to Never (cleanup restores the old values)' {
        Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/setacvalueindex', $scheme, 'SUB_SLEEP', 'STANDBYIDLE', '0') | Out-Null
        if ($null -ne $state['power_hibernate_ac_seconds']) {
            Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/setacvalueindex', $scheme, 'SUB_SLEEP', 'HIBERNATEIDLE', '0') | Out-Null
        }
        Invoke-Native -FilePath 'powercfg.exe' -ArgumentList @('/setactive', $scheme) | Out-Null
    }

    # Task Scheduler event log: 20-status.ps1 reads it to show when the boot task started.
    $taskLog = Get-WinEvent -ListLog 'Microsoft-Windows-TaskScheduler/Operational'
    if (-not $state.ContainsKey('taskscheduler_log_enabled_before')) {
        $state['taskscheduler_log_enabled_before'] = [bool]$taskLog.IsEnabled
        Save-BootTestState -State $state
    }
    if (-not $taskLog.IsEnabled) {
        Invoke-Step 'Turn on the Task Scheduler event log (cleanup restores it)' { $taskLog.IsEnabled = $true; $taskLog.SaveChanges() }
    }

    # Service account
    $accountName = $BootTest.AccountName
    $qualifiedName = Get-ServiceAccountQualifiedName
    $password = $null
    if (-not $dryRun) { $password = Get-RandomPassword }
    $account = Get-ServiceAccount
    if ($account) {
        Invoke-Step ('Give {0} a new random password (the tasks are registered again with it)' -f $accountName) {
            $secure = ConvertTo-KitSecureString -Text $password
            Set-LocalUser -Name $accountName -Password $secure -PasswordNeverExpires $true -AccountNeverExpires
        }
    } else {
        Invoke-Step ('Create the standard local account {0} with a random password (not stored, not shown)' -f $accountName) {
            $secure = ConvertTo-KitSecureString -Text $password
            New-LocalUser -Name $accountName -Password $secure -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires `
                -FullName 'SlateOps boot test service' -Description 'SlateOps WSL2 boot test. Remove with 90-cleanup.' | Out-Null
        }
    }
    $sid = 'S-1-5-21-(new account)'
    if (-not $dryRun) {
        $account = Get-ServiceAccount
        $sid = $account.SID.Value
        $state['account_sid'] = $sid
        Save-BootTestState -State $state
        $usersGroup = Get-LocalGroup -SID $BootTest.SidUsers
        # Get-LocalGroupMember can fail on orphaned SIDs, so add and accept "already a member".
        Invoke-Step ('Make {0} a member of the local group {1} (standard user, not an administrator)' -f $accountName, $usersGroup.Name) {
            try { Add-LocalGroupMember -SID $BootTest.SidUsers -Member $account }
            catch [Microsoft.PowerShell.Commands.MemberExistsException] { Write-KitLog '  Already a member.' }
        }
    }
    $rights = @($BootTest.BatchRight)
    if (-not $NoDenyRights) { $rights += $BootTest.DenyRights }
    $state['deny_rights'] = (-not $NoDenyRights)
    Save-BootTestState -State $state
    Invoke-Step ('Give {0} these rights: {1}' -f $accountName, ($rights -join ', ')) {
        Initialize-LsaRightsType
        [SlateOpsBootTest.LsaRights]::Add($sid, [string[]]$rights)
        if ($NoDenyRights) { [SlateOpsBootTest.LsaRights]::Remove($sid, [string[]]$BootTest.DenyRights) }
        Write-KitLog ('  Rights now: {0}' -f (([SlateOpsBootTest.LsaRights]::Get($sid)) -join ', '))
    }
    $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    if (-not $state.ContainsKey('userlist_key_existed')) {
        $state['userlist_key_existed'] = [bool](Test-Path -LiteralPath $userList)
        $state['specialaccounts_key_existed'] = [bool](Test-Path -LiteralPath (Split-Path -Parent $userList))
        Save-BootTestState -State $state
    }
    Invoke-Step ('Hide {0} from the sign-in screen' -f $accountName) {
        if (-not (Test-Path -LiteralPath $userList)) { New-Item -Path $userList -Force | Out-Null }
        New-ItemProperty -LiteralPath $userList -Name $accountName -PropertyType DWord -Value 0 -Force | Out-Null
    }
    # Service account access: read on the root folder itself (not inherited), read on kit, cache
    # and state, modify on svc-out and distro only. logs stays administrators-only.
    Invoke-Step ('Give {0} read access to kit, cache and state, and modify access to svc-out and distro only' -f $accountName) {
        Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($BootTest.Root, '/grant:r', ('*{0}:(RX)' -f $sid)) -Quiet | Out-Null
        foreach ($dir in @($BootTest.Kit, $BootTest.Cache, $BootTest.State)) {
            Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($dir, '/grant:r', ('*{0}:(OI)(CI)RX' -f $sid)) -Quiet | Out-Null
        }
        foreach ($dir in @($BootTest.SvcOut, $BootTest.Distro)) {
            Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($dir, '/grant:r', ('*{0}:(OI)(CI)M' -f $sid)) -Quiet | Out-Null
        }
        $problems = @(Get-BootTestTreeProblem)
        if ($problems.Count -gt 0) { throw ('{0} fails the safety check after the access change: {1}.' -f $BootTest.Root, ($problems -join '; ')) }
    }

    # On-demand task that runs allow-listed jobs as the service account.
    Invoke-Step ('Register the on-demand task {0}{1} (runs lib\svc-exec.ps1 as {2})' -f $BootTest.TaskPath, $BootTest.ExecTaskName, $accountName) {
        $action = New-ScheduledTaskAction -Execute $powershellExe `
            -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $BootTest.Kit 'lib\svc-exec.ps1'))
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        Register-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.ExecTaskName -Action $action -Settings $settings `
            -User $qualifiedName -Password $password -RunLevel Limited -Force `
            -Description 'Slate Operations boot test: runs one allow-listed job as slateops-svc. Remove with 90-cleanup.ps1.' | Out-Null
    }

    if ($dryRun) { Write-KitLog 'Would: run the job "prepare" as slateops-svc (.wslconfig, Debian import, systemd, Docker Engine, test stack)' 'WHATIF' }
    else { Invoke-SvcJob -Job 'prepare' -TimeoutMinutes 60 | Out-Null }

    # Boot task. Each setting and why:
    #   At startup trigger        starts before anyone signs in.
    #   Repetition every 1 min    starts the task again within a minute if it ever stopped
    #                             (MultipleInstances IgnoreNew makes a repeat a no-op while it runs).
    #   Password logon type       "Run whether user is logged on or not": runs in session 0.
    #   ExecutionTimeLimit PT0S   no time limit; the default stops a task after 72 hours.
    #   RestartCount/Interval     Task Scheduler tries again every minute if the start fails.
    #   Batteries settings        a laptop on battery does not block or stop it.
    #   StartWhenAvailable        a missed start runs as soon as possible.
    #   Priority 4                normal priority (the default 7 is below normal).
    Invoke-Step ('Register the boot task {0}{1} (At startup, as {2}, no time limit)' -f $BootTest.TaskPath, $BootTest.StartTaskName, $accountName) {
        $action = New-ScheduledTaskAction -Execute $powershellExe `
            -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $BootTest.Kit 'lib\start-distro.ps1'))
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1)).Repetition
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
            -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -DontStopOnIdleEnd -Priority 4
        Register-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.StartTaskName -Action $action -Trigger $trigger -Settings $settings `
            -User $qualifiedName -Password $password -RunLevel Limited -Force `
            -Description 'Slate Operations boot test: start the test distribution at boot and keep it running. Remove with 90-cleanup.ps1.' | Out-Null
    }
    $password = $null

    # Firewall: TCP 8443 only, Private profile only, from the LAN only.
    Invoke-Step ('Add Windows Defender Firewall rule {0}: inbound TCP {1}, Private profile, remote LocalSubnet' -f $BootTest.FirewallRuleName, $BootTest.Port) {
        Get-NetFirewallRule -Name $BootTest.FirewallRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        New-NetFirewallRule -Name $BootTest.FirewallRuleName -DisplayName ('SlateOps boot test TCP {0}' -f $BootTest.Port) -Group $BootTest.FirewallGroup `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort $BootTest.Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
    }
    Invoke-Step ('Add Hyper-V firewall rule {0}: WSL VM inbound TCP {1}, Private profile, remote {2}' -f $BootTest.HyperVRuleName, $BootTest.Port, $lan.Cidr) {
        Get-NetFirewallHyperVRule -Name $BootTest.HyperVRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule
        New-NetFirewallHyperVRule -Name $BootTest.HyperVRuleName -DisplayName ('SlateOps boot test TCP {0}' -f $BootTest.Port) `
            -Direction Inbound -VMCreatorId $BootTest.WslVmCreatorId -Protocol TCP -LocalPorts $BootTest.Port -RemoteAddresses $lan.Cidr `
            -Profiles Private -Action Allow | Out-Null
    }

    $localOk = $false
    Invoke-Step ('Start the boot task now and wait up to 10 minutes for {0}' -f $BootTest.StatusUrl) {
        Start-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.StartTaskName
        $deadline = (Get-Date).AddMinutes(10)
        $ready = $null
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 10
            try { $status = Get-StatusJson -TimeoutSec 5; if ($status.fresh) { $ready = $status; break } } catch { $null = $_ }
        }
        if ($ready) {
            Write-KitLog ('Status from this PC: heartbeat_count {0}, first_heartbeat {1}, last_heartbeat {2}.' -f $ready.status.heartbeat_count, $ready.status.first_heartbeat, $ready.status.last_heartbeat) 'PASS'
            $script:localOk = $true
        }
    }
    if ((-not $dryRun) -and (-not $localOk)) {
        # This PC reaching the service account's WSL VM through 127.0.0.1 is not proven. The
        # LAN check from another device is the real test, so this alone is not a setup failure.
        Write-KitLog ('{0} gave no fresh status from this PC within 10 minutes.' -f $BootTest.StatusUrl) 'WARN'
        Write-KitLog ('Check from another device now: http://{0}:{1}/ . If that also fails, run 20-status.ps1.' -f $lan.Address, $BootTest.Port) 'WARN'
    }

    $state['setup_completed_at'] = Get-UtcStamp
    $state['setup_local_check'] = $(if ($localOk) { 'fresh' } else { 'not reached from this PC' })
    Save-BootTestState -State $state
    Write-KitLog 'Setup is complete.' 'PASS'
    Write-KitLog ('From a phone or another PC on the same network, open: http://{0}:{1}/' -f $lan.Address, $BootTest.Port) 'PASS'
    Write-KitLog 'Next: do the steps in the README section "Before E1" and the baseline, then event E1.'
    exit 0
} catch {
    Write-KitLog ('Setup stopped at the first error: {0}' -f $_.Exception.Message) 'ERROR'
    Write-KitLog ($_.InvocationInfo.PositionMessage) 'ERROR'
    $logFile = Get-BootTestLogFile
    if ($logFile) { Write-KitLog ('Log: {0}' -f $logFile) 'ERROR' }
    exit 1
}
