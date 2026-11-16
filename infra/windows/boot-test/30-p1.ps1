<#
30-p1.ps1 - P1 of the Windows installer plan: measure the real Slate Operations stack on this PC
(slice S1) and run the hands-on spikes F1, F2, F3, F4, F5 and F10. One script runs every
automatic part, asks only when a person must act, and writes one results file.

Phase 1 (you start it, signed in):
  1. Checks the PC (administrator, module logging, build, network, free space, memory).
  2. Packs the repository source from the extracted ZIP into one tar file (tar.exe).
  3. Runs 10-setup.ps1 (it reuses an existing slateops-svc setup, or creates it), then restarts
     the account's WSL VM so the memory setting applies, and stops the 8443 test stack.
  4. S1: builds the server and Caddy images inside the distribution, starts the production
     stack with throwaway secrets that never leave Linux, Caddy with an internal certificate
     on <computer name>.local, ports 443 and 80 (Private profile, local network only) and a
     hosts entry <name>.local -> 127.0.0.1 on this PC. Measures idle memory, sizes, one
     offline backup and a restore timing. F2: this PC reads https://<name>.local/api/ready.
  5. Asks you to check the address on a phone (F1, F2), optionally a second name with Avahi
     (F1), optionally a USB drive (F5). Runs F3 with a throwaway distribution and a throwaway
     account. Prepares F10 and the boot probe. Runs the F4 test installer if you have it.
  6. Restarts Windows once. Do not sign in for 12 minutes after the sign-in screen appears.
Phase 2 (opens by itself after you sign in): collects the boot measurements and F10, guides the
F4 Modify and Uninstall checks, and writes the results file to your Desktop and to
C:\ProgramData\SlateOpsBootTest\logs.

Run in Windows PowerShell opened with "Run as administrator", in the boot-test folder of the ZIP:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\30-p1.ps1
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\30-p1.ps1 -WhatIf
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\30-p1.ps1 -Skip F4,F5
-WhatIf shows each step and changes nothing (no log file, no state).
Run it again after a stop: finished steps are skipped. Cleanup: 90-cleanup.ps1 (or -P1Only).
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    # Phase 2. The resume task sets it after the restart.
    [switch]$Resume,
    # Steps to skip, separated by commas, for example -Skip F4,F5. Names: S1, Backup, Restore,
    # F1, F1Avahi, F2Phone, F3, F4, F5, F10. S1 skips the whole stack (and the steps that need it).
    # One string, because powershell.exe -File passes "F4,F5" as one argument.
    [string]$Skip = '',
    # Memory for the WSL VM of slateops-svc during P1 (.wslconfig memory=).
    [ValidateRange(4, 32)][int]$WslMemoryGB = 8,
    # Path of the F4 test installer, if it is not in this folder or in Downloads.
    [string]$F4Installer = ''
)

. (Join-Path $PSScriptRoot 'lib\common.ps1')

$dryRun = [bool]$WhatIfPreference
$powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$curl = Join-Path $env:SystemRoot 'System32\curl.exe'
$script:VmSamples = @{}

# ---------------------------------------------------------------------------
# P1 state (state\p1-state.json): steps, answers, data. No secret is ever stored.
# ---------------------------------------------------------------------------

function Read-P1State {
    $p1 = @{ phase = 'start'; steps = @{}; answers = @{}; data = @{}; skip = @() }
    if (Test-Path -LiteralPath $BootTest.P1.StateFile) {
        $object = Get-Content -LiteralPath $BootTest.P1.StateFile -Raw | ConvertFrom-Json
        foreach ($property in $object.PSObject.Properties) {
            if (@('steps', 'answers', 'data') -contains $property.Name) {
                foreach ($inner in $property.Value.PSObject.Properties) { $p1[$property.Name][$inner.Name] = $inner.Value }
            } else {
                $p1[$property.Name] = $property.Value
            }
        }
    }
    return $p1
}

function Save-P1State {
    if ($dryRun) { return }
    $script:P1['updated_utc'] = Get-UtcStamp
    Set-Content -LiteralPath $BootTest.P1.StateFile -Value (ConvertTo-Json -InputObject $script:P1 -Depth 8) -Encoding UTF8
}

function Save-P1Step {
    param([string]$Id, [string]$Status, [string]$Reason = '')
    $script:P1.steps[$Id] = [ordered]@{ status = $Status; reason = $Reason; at = (Get-UtcStamp) }
    Save-P1State
}

function Get-P1StepStatus {
    param([string]$Id)
    if ($script:P1.steps.ContainsKey($Id)) { return [string]$script:P1.steps[$Id].status }
    return ''
}

function Get-SkipException { param([string]$Reason) return (New-Object System.OperationCanceledException $Reason) }

function Invoke-P1Step {
    # Runs one step once. A finished or skipped step is not run again. A step that throws an
    # OperationCanceledException is recorded as skipped with that reason.
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [string[]]$SkipWith = @(),
        [string[]]$Needs = @(),
        [switch]$Fatal
    )
    $status = Get-P1StepStatus -Id $Id
    if (@('done', 'skipped') -contains $status) { Write-KitLog ('{0}: already {1}.' -f $Title, $status); return }
    foreach ($group in $SkipWith) {
        if ($script:SkipList -contains $group) { Write-KitLog ('{0}: skipped (-Skip {1}).' -f $Title, $group) 'WARN'; Save-P1Step -Id $Id -Status 'skipped' -Reason ('-Skip {0}' -f $group); return }
    }
    if ($dryRun) { Write-KitLog ('Would: {0}' -f $Title) 'WHATIF'; return }
    foreach ($need in $Needs) {
        if ((Get-P1StepStatus -Id $need) -ne 'done') {
            # "blocked" is not final: the next run checks it again.
            Write-KitLog ('{0}: not run, because step {1} is not done.' -f $Title, $need) 'WARN'
            Save-P1Step -Id $Id -Status 'blocked' -Reason ('needs step {0}' -f $need); return
        }
    }
    Write-KitLog ('==== {0} ====' -f $Title) 'STEP'
    try {
        & $Action
        Save-P1Step -Id $Id -Status 'done'
    } catch [System.OperationCanceledException] {
        Write-KitLog ('{0}: skipped ({1}).' -f $Title, $_.Exception.Message) 'WARN'
        Save-P1Step -Id $Id -Status 'skipped' -Reason $_.Exception.Message
    } catch {
        Write-KitLog ('{0}: FAILED: {1}' -f $Title, $_.Exception.Message) 'FAIL'
        Save-P1Step -Id $Id -Status 'failed' -Reason $_.Exception.Message
        if ($Fatal) { throw }
    }
}

# ---------------------------------------------------------------------------
# Prompts. Every human step can be skipped.
# ---------------------------------------------------------------------------

function Read-P1Choice {
    param([Parameter(Mandatory = $true)][string]$Question, [string[]]$Allowed = @('Y', 'N', 'S'))
    try { [Console]::Beep(880, 250) } catch { $null = $_ }
    while ($true) {
        $answer = ([string](Read-Host ('{0} [{1}]' -f $Question, ($Allowed -join '/')))).Trim().ToUpperInvariant()
        if ($Allowed -contains $answer) { Write-KitLog ('{0} -> {1}' -f $Question, $answer); return $answer }
        Write-Host ('Type one of: {0}' -f ($Allowed -join ', '))
    }
}

function Show-P1Instruction {
    param([string[]]$Lines)
    Write-Host ''
    foreach ($line in $Lines) { Write-Host ('  ' + $line) -ForegroundColor Yellow }
    Write-Host ''
}

function Wait-P1Human {
    # Shows the instruction and waits. S skips the step.
    param([string[]]$Lines)
    Show-P1Instruction -Lines $Lines
    if ((Read-P1Choice -Question 'Type Y when you are ready, or S to skip this step' -Allowed @('Y', 'S')) -eq 'S') { throw (Get-SkipException 'skipped by the owner') }
}

function Save-P1Answer { param([string]$Key, [string]$Value) $script:P1.answers[$Key] = $Value; Save-P1State }

# ---------------------------------------------------------------------------
# Measurements on the Windows side
# ---------------------------------------------------------------------------

function Add-VmmemSample {
    param([string]$Phase)
    $mib = Get-VmmemMiB
    if ($null -eq $mib) { return }
    if (-not $script:VmSamples.ContainsKey($Phase)) { $script:VmSamples[$Phase] = New-Object System.Collections.Generic.List[double] }
    $script:VmSamples[$Phase].Add([double]$mib)
}

function Save-VmmemSummary {
    param([string]$Phase)
    if (-not $script:VmSamples.ContainsKey($Phase)) { return }
    $values = @($script:VmSamples[$Phase] | Sort-Object)
    $script:P1.data[('vmmem_' + $Phase)] = [ordered]@{
        samples = $values.Count; max_mib = $values[-1]; median_mib = $values[[int][math]::Floor($values.Count / 2)]
    }
    Save-P1State
}

function Get-DistroVhdSize {
    $vhd = Join-Path $BootTest.Distro 'vhd\ext4.vhdx'
    if (Test-Path -LiteralPath $vhd) { return (Get-Item -LiteralPath $vhd).Length }
    return $null
}

function Get-FreeGB {
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $env:SystemDrive)
    return [math]::Round($disk.FreeSpace / 1GB, 1)
}

function Get-ReadyCode {
    param([string]$Path = '/api/ready')
    $out = & $curl -sk -o NUL -w '%{http_code}' --max-time 8 ('https://{0}{1}' -f $script:P1.host, $Path) 2>$null
    return [string]$out
}

# ---------------------------------------------------------------------------
# Windows-side network for P1: firewall rules and the hosts entry
# ---------------------------------------------------------------------------

function Add-P1NetworkRule {
    param([string]$Cidr)
    foreach ($port in @(443, 80)) {
        $name = $BootTest.P1.WindowsRules[$port]
        Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        New-NetFirewallRule -Name $name -DisplayName ('SlateOps P1 TCP {0}' -f $port) -Group $BootTest.FirewallGroup `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private -RemoteAddress LocalSubnet | Out-Null
        $hyperV = $BootTest.P1.HyperVRules[$port]
        Get-NetFirewallHyperVRule -Name $hyperV -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule
        New-NetFirewallHyperVRule -Name $hyperV -DisplayName ('SlateOps P1 TCP {0}' -f $port) -Direction Inbound `
            -VMCreatorId $BootTest.WslVmCreatorId -Protocol TCP -LocalPorts $port -RemoteAddresses $Cidr -Profiles Private -Action Allow | Out-Null
        Write-KitLog ('  Rules for TCP {0}: Windows (Private, LocalSubnet) and Hyper-V (Private, {1}).' -f $port, $Cidr)
    }
}

function Add-P1HostsEntry {
    param([string]$HostName)
    $path = Get-P1HostsPath
    $backup = Join-Path $BootTest.State 'hosts.before-p1'
    if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $path -Destination $backup }
    $lines = @(Get-Content -LiteralPath $path | Where-Object { $_ -notlike ('*' + $BootTest.P1.HostsMarker + '*') })
    # Rewrite the whole file from lines, so the new line never joins a last line without a line end.
    Set-Content -LiteralPath $path -Value ($lines + @(('127.0.0.1 {0} {1}' -f $HostName, $BootTest.P1.HostsMarker))) -Encoding ASCII
    Invoke-Native -FilePath 'ipconfig.exe' -ArgumentList @('/flushdns') -Quiet | Out-Null
    Write-KitLog ('  hosts: 127.0.0.1 {0} (a copy of the old file: {1}).' -f $HostName, $backup)
}

# ---------------------------------------------------------------------------
# F3 throwaway account slateops-f3 and its on-demand task
# ---------------------------------------------------------------------------

function New-P1F3Account {
    # Register-ScheduledTask receives the password: check the logging policy again (it can change
    # between runs).
    $logged = @(Get-PasswordModuleLogged)
    if ($logged.Count -gt 0) { throw ('PowerShell module logging is on for {0}; it would record the F3 account password.' -f ($logged -join ', ')) }
    $name = $BootTest.P1.F3AccountName
    $password = Get-RandomPassword
    $secure = ConvertTo-KitSecureString -Text $password
    if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) {
        Set-LocalUser -Name $name -Password $secure
    } else {
        New-LocalUser -Name $name -Password $secure -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires `
            -FullName 'SlateOps P1 F3 test' -Description 'SlateOps P1 spike F3. Remove with 90-cleanup.' | Out-Null
    }
    $account = Get-LocalUser -Name $name
    $sid = $account.SID.Value
    try { Add-LocalGroupMember -SID $BootTest.SidUsers -Member $account } catch [Microsoft.PowerShell.Commands.MemberExistsException] { $null = $_ }
    Initialize-LsaRightsType
    [SlateOpsBootTest.LsaRights]::Add($sid, [string[]](@($BootTest.BatchRight) + $BootTest.DenyRights))
    $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    if (-not (Test-Path -LiteralPath $userList)) { New-Item -Path $userList -Force | Out-Null }
    New-ItemProperty -LiteralPath $userList -Name $name -PropertyType DWord -Value 0 -Force | Out-Null
    foreach ($dir in @($BootTest.F3Out, $BootTest.Spike)) { if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null } }
    # /L: change the named item itself, never the target of a link.
    Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($BootTest.Root, '/grant', ('*{0}:(RX)' -f $sid), '/L') -Quiet | Out-Null
    foreach ($dir in @($BootTest.Kit, $BootTest.State)) { Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($dir, '/grant', ('*{0}:(OI)(CI)RX' -f $sid), '/L') -Quiet | Out-Null }
    foreach ($dir in @($BootTest.F3Out, $BootTest.Spike)) { Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($dir, '/grant', ('*{0}:(OI)(CI)M' -f $sid), '/L') -Quiet | Out-Null }
    $kept = Join-Path $BootTest.Spike 'kept\ext4.vhdx'
    if (Test-Path -LiteralPath $kept) { Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($kept, '/grant', ('*{0}:M' -f $sid), '/L') -Quiet | Out-Null }
    $action = New-ScheduledTaskAction -Execute $powershellExe -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $BootTest.Kit 'lib\svc-exec.ps1'))
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.F3TaskName -Action $action -Settings $settings `
        -User ('{0}\{1}' -f $env:COMPUTERNAME, $name) -Password $password -RunLevel Limited -Force `
        -Description 'Slate Operations P1 spike F3: runs one job as slateops-f3. Remove with 90-cleanup.ps1.' | Out-Null
    $password = $null
    $problems = @(Get-BootTestTreeProblem)
    if ($problems.Count -gt 0) { throw ('{0} fails the safety check after the F3 access change: {1}.' -f $BootTest.Root, ($problems -join '; ')) }
}

function Remove-P1F3Account {
    if (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.F3TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.F3TaskName -Confirm:$false
    }
    $sid = Get-BootTestF3Sid
    if ($sid) {
        foreach ($dir in @($BootTest.Root, $BootTest.Kit, $BootTest.State, $BootTest.Spike, $BootTest.F3Out)) {
            if (Test-Path -LiteralPath $dir) { Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($dir, '/remove:g', ('*{0}' -f $sid)) -Quiet -NoThrow | Out-Null }
        }
    }
    Remove-KitLocalAccount -Name $BootTest.P1.F3AccountName -Sid $sid
    if (Test-Path -LiteralPath $BootTest.F3Out) { Remove-PathNoFollow -Path $BootTest.F3Out }
}

# ---------------------------------------------------------------------------
# Phase 1
# ---------------------------------------------------------------------------

function Get-RepoRoot {
    $root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
    foreach ($sentinel in @('.dockerignore', 'backend\pyproject.toml', 'frontend\package-lock.json', 'infra\docker\backend.Dockerfile', 'packaging\backup\backup_installation.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $sentinel))) { return $null }
    }
    return $root
}

function Invoke-Phase1 {
    Invoke-P1Step -Id 'checks' -Title 'Check this PC' -Fatal -Action {
        $logged = @(Get-PasswordModuleLogged)
        if ($logged.Count -gt 0) { throw ('PowerShell module logging is on for {0}. It would record an account password. Turn it off, then run again.' -f ($logged -join ', ')) }
        $win = Get-WindowsInfo
        if ($win.Build -lt $BootTest.MinBuild) { throw ('Windows build {0} is below {1}.' -f $win.Build, $BootTest.MinBuild) }
        $lan = Get-LanInfo
        if ($null -eq $lan) { throw 'No connected network with a default gateway.' }
        if ($lan.Category -ne 'Private') { throw ('The network "{0}" is {1}. Set it to Private, then run again.' -f $lan.NetworkName, $lan.Category) }
        $cs = Get-CimInstance -ClassName Win32_ComputerSystem
        $ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
        if ($ramGB -lt ($WslMemoryGB + 4)) { throw ('This PC has {0} GB of memory. P1 gives the WSL VM {1} GB and needs {2} GB in total. Use -WslMemoryGB with a smaller value.' -f $ramGB, $WslMemoryGB, ($WslMemoryGB + 4)) }
        $free = Get-FreeGB
        if ($free -lt $BootTest.P1.MinFreeGB) { throw ('Drive {0} has {1} GB free. P1 needs {2} GB (image builds and the stack). Free space, then run again.' -f $env:SystemDrive, $free, $BootTest.P1.MinFreeGB) }
        $dnsName = ([string]$cs.DNSHostName).ToLowerInvariant()
        $hostName = '{0}.local' -f $dnsName
        if ($hostName -notmatch '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.local$') { throw ('The computer name "{0}" cannot be a .local name (use letters, digits and hyphens only).' -f $dnsName) }
        foreach ($port in @(443, 80)) {
            if (Test-PortListening -Port $port) { throw ('Another program listens on TCP {0} (for example IIS or Skype). Stop it, then run again.' -f $port) }
        }
        $script:P1.host = $hostName
        $script:P1.lan_address = $lan.Address
        $script:P1.lan_cidr = $lan.Cidr
        $script:P1.wsl_memory_gb = $WslMemoryGB
        $script:P1.data['pc'] = [ordered]@{
            windows = ('{0}, edition {1}, version {2}, build {3}.{4}' -f $win.Caption, $win.EditionId, $win.DisplayVersion, $win.Build, $win.Ubr)
            cpu = (@(Get-CimInstance -ClassName Win32_Processor)[0]).Name
            logical_processors = $cs.NumberOfLogicalProcessors
            ram_gb = $ramGB
            free_gb_before = $free
            wsl_version_before = [string](Get-WslVersion)
            architecture = (Get-Architecture)
            network = ('{0} ({1})' -f $lan.InterfaceAlias, $lan.Category)
        }
        Write-KitLog ('Name for this PC: {0}; LAN address {1}; free {2} GB; RAM {3} GB.' -f $hostName, $lan.Address, $free, $ramGB) 'PASS'
    }

    Invoke-P1Step -Id 'source' -Title 'Pack the repository source for the image builds' -SkipWith 'S1' -Fatal -Action {
        $repo = Get-RepoRoot
        if (-not $repo) { throw 'Run 30-p1.ps1 from infra\windows\boot-test in the extracted ZIP: the repository files are not found two folders up.' }
        if (Test-Path -LiteralPath $BootTest.Root) {
            $problems = @(Get-BootTestTreeProblem)
            if ($problems.Count -gt 0) { throw ('{0} fails the safety check: {1}. Run 90-cleanup.ps1, then run again.' -f $BootTest.Root, ($problems -join '; ')) }
        }
        $null = Initialize-BootTestRoot
        $problems = @(Get-BootTestTreeProblem)
        if ($problems.Count -gt 0) { throw ('{0} fails the safety check: {1}.' -f $BootTest.Root, ($problems -join '; ')) }
        if (-not (Test-Path -LiteralPath $BootTest.Source)) { New-Item -ItemType Directory -Path $BootTest.Source | Out-Null }
        if (Test-Path -LiteralPath $BootTest.P1.SourceTar) { Remove-Item -LiteralPath $BootTest.P1.SourceTar -Force }
        $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
        Invoke-Native -FilePath $tar -ArgumentList @('-cf', $BootTest.P1.SourceTar, '-C', $repo, '--exclude=node_modules', '--exclude=.venv',
            '--exclude=__pycache__', '.dockerignore', 'backend', 'frontend', 'contracts', 'infra', 'packaging') -Quiet | Out-Null
        Write-KitLog ('  {0}: {1:N1} MB.' -f $BootTest.P1.SourceTar, ((Get-Item -LiteralPath $BootTest.P1.SourceTar).Length / 1MB)) 'PASS'
    }

    Invoke-P1Step -Id 'setup' -Title 'Boot-test setup (reuses an existing setup, or creates it)' -Fatal -Action {
        $before = Get-UtcStamp
        # Its output shows live in this window; 10-setup.ps1 writes its own log as well.
        & $powershellExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot '10-setup.ps1') -WslMemoryGB $WslMemoryGB -ContinueP1
        if ($LASTEXITCODE -ne 0) { throw ('10-setup.ps1 stopped with exit code {0}. Read its log in {1}.' -f $LASTEXITCODE, $BootTest.Logs) }
        $state = Read-BootTestState
        if ((-not $state.ContainsKey('setup_completed_at')) -or ([string]$state['setup_completed_at'] -lt $before)) {
            Save-P1State
            Write-KitLog 'Windows must restart before setup can finish. Restart now and sign in. Setup continues, then this script starts again.' 'WARN'
            exit 0
        }
        $sid = Get-BootTestServiceSid
        Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($BootTest.Source, '/grant:r', ('*{0}:(OI)(CI)RX' -f $sid), '/L') -Quiet | Out-Null
        $state['p1_host'] = $script:P1.host
        Save-BootTestState -State $state
    }

    Invoke-P1Step -Id 'restart-vm' -Title ('Restart the WSL VM of slateops-svc so the {0} GB memory setting applies' -f $WslMemoryGB) -Fatal -Action {
        $result = Invoke-SvcJob -Job 'restart-vm' -TimeoutMinutes 6
        $script:P1.data['mem_total'] = [string]$result.data.mem_total
    }

    Invoke-P1Step -Id 'stop-test-stack' -Title 'Stop the 8443 boot-test stack (it uses memory during the measurements)' -SkipWith 'S1' -Action {
        $null = Invoke-SvcJob -Job 's1-stop-test-stack' -TimeoutMinutes 5
    }

    Invoke-P1Step -Id 'install' -Title 'S1: build the images and start the real stack (unattended; 20 to 60 minutes)' -SkipWith 'S1' -Needs 'setup' -Action {
        Show-P1Instruction -Lines @('This step runs by itself. You can leave the PC; it beeps when it needs you.')
        $script:LowDisk = $false
        try {
            # The distribution disk grows on C: during the builds. Below 5 GB free, stop the job.
            $null = Invoke-SvcJob -Job 's1-install' -TimeoutMinutes 115 -OnPoll {
                Add-VmmemSample -Phase 'install'
                if ((Get-FreeGB) -lt 5) { $script:LowDisk = $true; 'abort' }
            }
        } catch {
            if ($script:LowDisk) {
                $cleaned = 'and its cache removed'
                try { $null = Invoke-SvcJob -Job 's1-abort' -TimeoutMinutes 10 -NoThrow }
                catch { $cleaned = ('but its cache was not removed ({0})' -f $_.Exception.Message) }
                throw ('Drive {0} has less than 5 GB free, so the build was stopped {1}. Free space on {0}, then run 30-p1.ps1 again.' -f $env:SystemDrive, $cleaned)
            }
            throw
        }
        Save-VmmemSummary -Phase 'install'
        $script:P1.data['vhd_bytes_after_install'] = Get-DistroVhdSize
        $script:P1.data['free_gb_after_install'] = Get-FreeGB
    }

    Invoke-P1Step -Id 'network' -Title 'Open TCP 443 and 80 (Private, local network) and add the hosts entry' -Needs 'install' -Action {
        Add-P1NetworkRule -Cidr $script:P1.lan_cidr
        Add-P1HostsEntry -HostName $script:P1.host
    }

    Invoke-P1Step -Id 'idle' -Title 'S1: idle memory and sizes' -Needs 'install' -Action {
        $null = Invoke-SvcJob -Job 's1-measure-idle' -TimeoutMinutes 10 -OnPoll { Add-VmmemSample -Phase 'idle' }
        Save-VmmemSummary -Phase 'idle'
        $script:P1.data['vhd_bytes_idle'] = Get-DistroVhdSize
    }

    Invoke-P1Step -Id 'f2-local' -Title ('F2: this PC reads https://{0}/api/ready through the hosts entry' -f $script:P1.host) -Needs 'network' -Action {
        $addresses = @([System.Net.Dns]::GetHostAddresses($script:P1.host) | ForEach-Object { $_.IPAddressToString })
        $ready = Get-ReadyCode
        $page = Get-ReadyCode -Path '/'
        $script:P1.data['f2_local'] = [ordered]@{ resolves_to = ($addresses -join ','); api_ready_code = $ready; root_page_code = $page }
        if ($ready -ne '200') { throw ('https://{0}/api/ready answered "{1}" on this PC (expected 200).' -f $script:P1.host, $ready) }
        Write-KitLog ('  {0} -> {1}; /api/ready 200; / {2}.' -f $script:P1.host, ($addresses -join ','), $page) 'PASS'
    }

    Invoke-P1Step -Id 'backup' -Title 'S1: one offline backup (the stack stops for a few minutes) and the ordered restart' -SkipWith 'Backup' -Needs 'install' -Action {
        $null = Invoke-SvcJob -Job 's1-backup' -TimeoutMinutes 60 -OnPoll { Add-VmmemSample -Phase 'backup' }
        Save-VmmemSummary -Phase 'backup'
    }

    Invoke-P1Step -Id 'restore' -Title 'S1: restore timing (restic restore into a scratch folder)' -SkipWith 'Restore' -Needs 'backup' -Action {
        $null = Invoke-SvcJob -Job 's1-restore-timing' -TimeoutMinutes 60
    }

    Invoke-P1Step -Id 'f1-phone' -Title 'F1 and F2: open the address on a phone' -SkipWith 'F1', 'F2Phone' -Needs 'network' -Action {
        $null = Invoke-SvcJob -Job 's1-port80-start' -TimeoutMinutes 5
            Wait-P1Human -Lines @(
                'Take a phone (iPhone or Android) that uses the same Wi-Fi network as this PC (not mobile data).',
                ('1. Open this address in the phone browser: https://{0}' -f $script:P1.host),
                '   A certificate warning is expected. Select "Show details" or "Advanced", then "visit this website" or "Proceed".',
                '   The Slate Operations sign-in page should appear.',
                ('2. Open: http://{0}/   (port 80, by address)' -f $script:P1.lan_address),
                ('3. Open: http://{0}/   (port 80, by name)' -f $script:P1.host),
                '   Pages 2 and 3 should say "Port 80 works."')
            Save-P1Answer -Key 'phone_os' -Value (Read-P1Choice -Question 'Phone: I = iPhone, A = Android' -Allowed @('I', 'A'))
            Save-P1Answer -Key 'f1_https_name' -Value (Read-P1Choice -Question ('1. Did https://{0} show the sign-in page (after the warning)?' -f $script:P1.host))
            Save-P1Answer -Key 'f2_http80_ip' -Value (Read-P1Choice -Question ('2. Did http://{0}/ show "Port 80 works."?' -f $script:P1.lan_address))
            Save-P1Answer -Key 'f2_http80_name' -Value (Read-P1Choice -Question ('3. Did http://{0}/ show "Port 80 works."?' -f $script:P1.host))
    }

    Invoke-P1Step -Id 'f1-avahi' -Title 'F1 (optional): can Avahi in Linux publish a second name beside Windows?' -SkipWith 'F1', 'F1Avahi' -Needs 'network' -Action {
        if ((Read-P1Choice -Question 'Test a second name (slateops-p1.local) with Avahi? About 3 minutes. Y = test, S = skip' -Allowed @('Y', 'S')) -eq 'S') { throw (Get-SkipException 'skipped by the owner') }
        $state = Read-BootTestState
        $state['p1_avahi_name'] = 'slateops-p1.local'
        Save-BootTestState -State $state
        $rule = $BootTest.P1.HyperVMdnsRule
        try {
            Get-NetFirewallHyperVRule -Name $rule -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule
            New-NetFirewallHyperVRule -Name $rule -DisplayName 'SlateOps P1 mDNS (Avahi test)' -Direction Inbound -VMCreatorId $BootTest.WslVmCreatorId `
                -Protocol UDP -LocalPorts 5353 -RemoteAddresses $script:P1.lan_cidr -Profiles Private -Action Allow | Out-Null
            $null = Invoke-SvcJob -Job 's1-port80-start' -TimeoutMinutes 5
            $null = Invoke-SvcJob -Job 's1-avahi-start' -TimeoutMinutes 10
            Show-P1Instruction -Lines @('On the phone, open: http://slateops-p1.local/', 'It should say "Port 80 works." Wait up to 1 minute and reload once if it does not.')
            Save-P1Answer -Key 'f1_avahi_second_name' -Value (Read-P1Choice -Question 'Did http://slateops-p1.local/ show "Port 80 works."?')
            Save-P1Answer -Key 'f1_windows_name_after_avahi' -Value (Read-P1Choice -Question ('Open https://{0} again. Does it still show the sign-in page?' -f $script:P1.host))
        } finally {
            $null = Invoke-SvcJob -Job 's1-avahi-stop' -TimeoutMinutes 10 -NoThrow
            $null = Invoke-SvcJob -Job 's1-port80-stop' -TimeoutMinutes 5 -NoThrow
            Get-NetFirewallHyperVRule -Name $rule -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule
        }
    }
    # The port 80 page runs only for the phone checks.
    if ((-not $dryRun) -and ((Get-P1StepStatus -Id 'install') -eq 'done')) { $null = Invoke-SvcJob -Job 's1-port80-stop' -TimeoutMinutes 5 -NoThrow }

    $spikeSkip = @()
    if (($script:SkipList -contains 'F3') -and ($script:SkipList -contains 'F5')) { $spikeSkip = @('F3') }
    Invoke-P1Step -Id 'spike-import' -Title 'F3/F5: import the throwaway distribution SlateOpsSpike (automount off)' -SkipWith $spikeSkip -Needs 'setup' -Action {
        $sid = Get-BootTestServiceSid
        if (-not (Test-Path -LiteralPath $BootTest.Spike)) { New-Item -ItemType Directory -Path $BootTest.Spike | Out-Null }
        Invoke-Native -FilePath 'icacls.exe' -ArgumentList @($BootTest.Spike, '/grant:r', ('*{0}:(OI)(CI)M' -f $sid), '/L') -Quiet | Out-Null
        $state = Read-BootTestState
        $state['p1_spike_marker'] = ([guid]::NewGuid().ToString('N'))
        Save-BootTestState -State $state
        $null = Invoke-SvcJob -Job 'spike-import' -TimeoutMinutes 15
    }

    Invoke-P1Step -Id 'f5' -Title 'F5 (optional): USB drive with drvfs and Restic speed' -SkipWith 'F5' -Needs 'spike-import' -Action {
        Show-P1Instruction -Lines @(
            'F5 needs a USB drive with at least 1 GB free. The test writes about 250 MB into a new folder',
            'SlateOps-F5-<number> on the drive and deletes that folder at the end. It changes no other file.',
            'Use a drive with no private files: during the test the whole drive is visible inside Linux.')
        Wait-P1Human -Lines @('Plug in the USB drive now. Wait until Windows shows it in File Explorer.')
        $drives = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=2' | Where-Object { $_.FreeSpace -gt 1GB })
        if ($drives.Count -eq 0) {
            # Some USB drives report as fixed disks. Offer the other fixed drives, after a confirmation.
            $fixed = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' | Where-Object { ($_.DeviceID -ne $env:SystemDrive) -and ($_.FreeSpace -gt 1GB) })
            if ($fixed.Count -eq 0) { throw (Get-SkipException 'no USB drive with 1 GB free was found') }
            Show-P1Instruction -Lines @(('No removable drive was found. These drives are fixed drives: {0}' -f (($fixed | ForEach-Object { $_.DeviceID }) -join ', ')),
                'Use one only if it is the USB drive, or a drive with no private files: during the test the whole drive is visible inside Linux.')
            if ((Read-P1Choice -Question 'Use one of these drives for F5? Y = yes, S = skip F5' -Allowed @('Y', 'S')) -eq 'S') { throw (Get-SkipException 'skipped by the owner (no removable drive)') }
            $drives = $fixed
        }
        $letters = @($drives | ForEach-Object { $_.DeviceID.Substring(0, 1).ToUpperInvariant() })
        $letter = $letters[0]
        if ($letters.Count -gt 1) { $letter = Read-P1Choice -Question ('Which drive? {0}' -f ($letters -join ', ')) -Allowed $letters }
        $drive = @($drives | Where-Object { $_.DeviceID -like ($letter + ':') })[0]
        $folderName = 'SlateOps-F5-{0}' -f ([guid]::NewGuid().ToString('N').Substring(0, 8))
        $folder = '{0}:\{1}' -f $letter, $folderName
        $state = Read-BootTestState
        $state['p1_f5_drive'] = $letter
        $state['p1_f5_folder'] = $folderName
        Save-BootTestState -State $state
        # The folder gets its access list in the same call that creates it (Administrators, SYSTEM,
        # slateops-svc). FAT and exFAT drives keep no access list.
        $security = Get-ProtectedDirectorySecurity
        $svcRule = New-Object System.Security.AccessControl.FileSystemAccessRule((New-Object System.Security.Principal.SecurityIdentifier((Get-BootTestServiceSid))), 'Modify', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
        $security.AddAccessRule($svcRule)
        $aclMode = 'set at creation'
        try { [void][System.IO.Directory]::CreateDirectory($folder, $security) }
        catch { New-Item -ItemType Directory -Path $folder | Out-Null; $aclMode = ('none: {0}' -f $_.Exception.Message) }
        try {
            $result = Invoke-SvcJob -Job 'f5-drvfs' -TimeoutMinutes 40 -NoThrow
            $script:P1.data['f5'] = [ordered]@{
                file_system = $drive.FileSystem; drive_type = $drive.DriveType; size_gb = [math]::Round($drive.Size / 1GB, 1); folder_acl = $aclMode
                job_exit = $(if ($result) { $result.exit_code } else { 'no result' }); result = $(if ($result) { [string]$result.data.f5 } else { '' })
            }
            if ((-not $result) -or ([int]$result.exit_code -ne 0)) { throw 'The F5 job failed. Read svc-out\svc-exec-f5-drvfs.log.' }
        } finally {
            # slateops-svc can change this folder: it empties it, then only the empty folder is deleted here.
            if (Test-Path -LiteralPath $folder) {
                $null = Invoke-SvcJob -Job 'f5-clean' -TimeoutMinutes 10 -NoThrow
                Remove-EmptiedFolder -Path $folder
            }
        }
    }

    Invoke-P1Step -Id 'f3' -Title 'F3: move the disk, unregister, register again under a new account' -SkipWith 'F3' -Needs 'spike-import' -Action {
        $data = [ordered]@{}
        $move = Invoke-SvcJob -Job 'f3-move' -TimeoutMinutes 10
        $data['move'] = $move.data
        $unregister = Invoke-SvcJob -Job 'f3-unregister' -TimeoutMinutes 10 -NoThrow
        $data['unregister'] = $(if ($unregister) { $unregister.data } else { 'no result' })
        if (-not (Test-Path -LiteralPath (Join-Path $BootTest.Spike 'kept\ext4.vhdx'))) {
            $script:P1.data['f3'] = $data
            throw 'wsl --unregister deleted the moved disk, or the move failed. That answers F3 (fail).'
        }
        try {
            New-P1F3Account
            $import = Invoke-SvcJob -Job 'f3-import-in-place' -Account 'f3' -TimeoutMinutes 15 -NoThrow
            $data['import_in_place'] = $(if ($import) { $import.data } else { 'no result' })
            $data['import_exit'] = $(if ($import) { $import.exit_code } else { 'no result' })
        } finally {
            if (-not ($data['import_exit'] -eq 0)) { $null = Invoke-SvcJob -Job 'f3-cleanup' -Account 'f3' -TimeoutMinutes 5 -NoThrow }
            Remove-P1F3Account
            $script:P1.data['f3'] = $data
            Save-P1State
        }
        if (-not ($data['import_exit'] -eq 0)) { throw 'F3 import-in-place under the new account failed. Read the F3 data in the results.' }
        # slateops-svc can change the spike folder: it deletes the leftovers itself.
        $null = Invoke-SvcJob -Job 'spike-clean' -TimeoutMinutes 10 -NoThrow
    }
    # The throwaway distribution must not run during the boot measurement.
    if ((-not $dryRun) -and ((Get-P1StepStatus -Id 'spike-import') -eq 'done') -and ((Get-P1StepStatus -Id 'f3') -ne 'done')) {
        $null = Invoke-SvcJob -Job 'spike-unregister' -TimeoutMinutes 10 -NoThrow
    }

    Invoke-P1Step -Id 'f10-prepare' -Title 'F10: download the WSL MSI that matches the installed version (SHA-256 checked)' -SkipWith 'F10' -Needs 'install' -Action {
        $installed = Get-WslVersion
        $arch = Get-Architecture
        $key = [string]$installed
        $mode = 'repair'
        if (-not $BootTest.P1.WslMsi.ContainsKey($key)) {
            if ($installed -lt $BootTest.P1.WslNewestStable) { $key = [string]$BootTest.P1.WslNewestStable; $mode = 'upgrade' }
            else { throw (Get-SkipException ('no pinned MSI for the installed WSL {0}' -f $installed)) }
        }
        $pin = $BootTest.P1.WslMsi[$key][$arch]
        $file = Join-Path $BootTest.Cache ('wsl.{0}.{1}.msi' -f $key, $arch.ToLowerInvariant())
        $good = (Test-Path -LiteralPath $file) -and ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -eq $pin.Sha256)
        if (-not $good) {
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $pin.Url -OutFile $file -UseBasicParsing -UserAgent 'SlateOpsBootTest/1.0 (WindowsPowerShell/5.1)'
            $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($hash -ne $pin.Sha256) { Remove-Item -LiteralPath $file -Force; throw ('SHA-256 mismatch for the WSL {0} MSI; the file was deleted.' -f $key) }
        }
        $state = Read-BootTestState
        $state['p1_f10_msi_version'] = $key
        $state['p1_f10_mode'] = $mode
        Save-BootTestState -State $state
        $script:P1.data['f10_plan'] = [ordered]@{ installed = [string]$installed; msi = $key; mode = $mode }
        Write-KitLog ('  F10 plan: {0} of WSL {1} (installed {2}). A repair may not exercise the upgrade path.' -f $mode, $key, $installed) 'PASS'
    }

    # A failed or blocked stack step must be retried before the restart: after it, phase 2 runs.
    if ((-not $dryRun) -and ($script:SkipList -notcontains 'S1')) {
        $broken = @()
        foreach ($id in @('install', 'network', 'idle', 'backup')) {
            $status = Get-P1StepStatus -Id $id
            if (@('failed', 'blocked') -contains $status) { $broken += ('{0} ({1}: {2})' -f $id, $status, $script:P1.steps[$id].reason) }
        }
        if ($broken.Count -gt 0) {
            foreach ($item in $broken) { Write-KitLog ('Not complete: {0}' -f $item) 'ERROR' }
            Show-P1Instruction -Lines @('P1 stops before the restart, because a stack step did not complete (red lines above).',
                'Nothing is lost. Correct the cause, then run 30-p1.ps1 again: it repeats only the steps that did not complete.',
                'To continue without the stack (no measurements, no boot test, no F10), run:',
                '  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\30-p1.ps1 -Skip S1')
            Save-P1State
            exit 1
        }
    }

    Invoke-P1Step -Id 'arm' -Title 'Arm the boot probe (SYSTEM, at startup) and the resume task (at your sign-in)' -Action {
        # The SYSTEM task runs kit scripts and the cached MSI: check the whole kit folder first.
        $problems = @(Get-BootTestTreeProblem)
        if ($problems.Count -gt 0) { throw ('{0} fails the safety check: {1}. Run 90-cleanup.ps1, then run again.' -f $BootTest.Root, ($problems -join '; ')) }
        $state = Read-BootTestState
        $state['p1_probe_armed'] = ((Get-P1StepStatus -Id 'install') -eq 'done')
        $state['p1_f10_armed'] = ((Get-P1StepStatus -Id 'f10-prepare') -eq 'done')
        Save-BootTestState -State $state
        if (Test-Path -LiteralPath $BootTest.P1.ProbeResult) { Remove-Item -LiteralPath $BootTest.P1.ProbeResult -Force }
        $action = New-ScheduledTaskAction -Execute $powershellExe -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $BootTest.Kit 'lib\p1-probe.ps1'))
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ProbeTaskName -Action $action -Trigger $trigger -Principal $principal `
            -Settings $settings -Force -Description 'Slate Operations P1: boot measurement and F10 (runs once when armed). Remove with 90-cleanup.ps1.' | Out-Null
        $owner = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $resume = ('-NoProfile -ExecutionPolicy Bypass -NoExit -Command "& ''{0}'' -Resume"' -f (Join-Path $BootTest.Kit '30-p1.ps1'))
        $action = New-ScheduledTaskAction -Execute $powershellExe -Argument $resume
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $owner
        $principal = New-ScheduledTaskPrincipal -UserId $owner -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
        Register-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ResumeTaskName -Action $action -Trigger $trigger -Principal $principal `
            -Settings $settings -Force -Description 'Slate Operations P1: continue after the restart. 30-p1.ps1 deletes this task.' | Out-Null
    }

    # The arm step must also be complete before the restart (F4 can restart Windows).
    if ((-not $dryRun) -and ((Get-P1StepStatus -Id 'arm') -ne 'done')) {
        Write-KitLog ('Not complete: arm ({0}: {1})' -f (Get-P1StepStatus -Id 'arm'), $script:P1.steps['arm'].reason) 'ERROR'
        # A half-made arm step must not start phase 2 at the next sign-in.
        if (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ResumeTaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ResumeTaskName -Confirm:$false
        }
        Show-P1Instruction -Lines @('P1 stops before the restart, because the boot probe and the resume task could not be prepared (red line above).',
            'Nothing is lost. Correct the cause, then run 30-p1.ps1 again: it repeats only the steps that did not complete.')
        Save-P1State
        exit 1
    }

    Invoke-P1Step -Id 'f4-run' -Title 'F4 (optional): run the test installer (it asks for the one restart)' -SkipWith 'F4' -Action {
        $candidates = @($F4Installer, (Join-Path $PSScriptRoot $BootTest.P1.F4ExeName), (Join-Path $env:USERPROFILE ('Downloads\' + $BootTest.P1.F4ExeName))) | Where-Object { $_ }
        $exe = @($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }) | Select-Object -First 1
        if (-not $exe) { throw (Get-SkipException ('{0} was not found in this folder or in Downloads' -f $BootTest.P1.F4ExeName)) }
        if ($BootTest.P1.F4Sha256 -notmatch '^[0-9a-f]{64}$') { throw (Get-SkipException 'the kit has no pinned SHA-256 for the test installer') }
        $hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $BootTest.P1.F4Sha256) { throw ('{0} has SHA-256 {1}, not the pinned {2}. Download it again from the draft release.' -f (Split-Path -Leaf $exe), $hash, $BootTest.P1.F4Sha256) }
        if (-not (Test-Path -LiteralPath $BootTest.F4Dir)) { New-Item -ItemType Directory -Path $BootTest.F4Dir | Out-Null }
        $copy = Join-Path $BootTest.F4Dir $BootTest.P1.F4ExeName
        Copy-Item -LiteralPath $exe -Destination $copy -Force
        Unblock-File -LiteralPath $copy
        if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $BootTest.P1.F4Sha256) {
            Remove-Item -LiteralPath $copy -Force
            throw 'The copy of the test installer has another SHA-256 than the checked file. Refused.'
        }
        Show-P1Instruction -Lines @(
            'CAUTION: the test installer can restart Windows at once. Save your work and close other programs now.',
            'The test installer "Slate Operations P1 installer test" opens now. It installs nothing of the product.',
            'Windows can show "Windows protected your PC" (the file is not signed): select "More info", then "Run anyway".',
            '1. Select Next on each page.',
            '2. At "Preparing to Install" it says that the PC must restart. Select "No, I will restart my computer later", then Finish.',
            '   This script restarts the PC in the next step.',
            '   If the PC restarts anyway: do NOT sign in for 12 minutes after the sign-in screen appears.')
        # Marked done before it starts: if the owner selects "Restart now" in the installer, Windows
        # restarts at once, and phase 2 must still find the F4 run and the armed probe.
        Save-P1Step -Id 'f4-run' -Status 'done' -Reason 'launched'
        $process = Start-Process -FilePath $copy -PassThru -Wait
        $script:P1.data['f4_first_run_exit'] = $process.ExitCode
    }

    Invoke-P1Step -Id 'restart' -Title 'Restart Windows for the boot measurement and F10' -Action {
        $script:P1.phase = 'restarting'
        $script:P1.data['restart_requested_utc'] = Get-UtcStamp
        Save-P1State
        Show-P1Instruction -Lines @(
            'CAUTION: Windows restarts. Save your work and close other programs now. Unsaved work is lost.',
            'After the restart, when the sign-in screen appears: do NOT sign in for 12 minutes (set a timer on your phone).',
            'Windows then starts Slate Operations with nobody signed in, and this kit measures the time and runs F10.',
            'After 12 minutes, sign in. This script opens again by itself.')
        if ((Read-P1Choice -Question 'Restart now? Y = restart in 30 seconds, S = skip the restart (no boot measurement, no F10)' -Allowed @('Y', 'S')) -eq 'S') {
            $state = Read-BootTestState
            $state['p1_probe_armed'] = $false
            $state['p1_f10_armed'] = $false
            Save-BootTestState -State $state
            throw (Get-SkipException 'skipped by the owner')
        }
        Save-P1Step -Id 'restart' -Status 'done'
        Invoke-Native -FilePath 'shutdown.exe' -ArgumentList @('/r', '/t', '30', '/c', 'Slate Operations P1: restart. Do not sign in for 12 minutes.') | Out-Null
        Write-KitLog 'Windows restarts in 30 seconds.' 'WARN'
        exit 0
    }
    # Restart skipped: go straight to phase 2 (no boot measurement).
    Invoke-Phase2
}

# ---------------------------------------------------------------------------
# Phase 2 (after the restart and your sign-in)
# ---------------------------------------------------------------------------

function Invoke-Phase2 {
    if (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ResumeTaskName -ErrorAction SilentlyContinue) {
        if (-not $dryRun) { Unregister-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ResumeTaskName -Confirm:$false }
    }
    $script:P1.phase = 'after-restart'
    Save-P1State

    Invoke-P1Step -Id 'f4-resume' -Title 'F4: the test installer after the restart (finish it before the next steps)' -SkipWith 'F4' -Needs 'f4-run' -Action {
        Show-P1Instruction -Lines @('After your sign-in, the test installer should have opened again by itself (RunOnce).',
            'If it is open: select Next on each page until Finish. Wait until it is closed.',
            'The next steps use the same Exec task, so the installer must be closed first.')
        Save-P1Answer -Key 'f4_resumed_window' -Value (Read-P1Choice -Question 'Did the test installer open again after the sign-in? (Answer when it is closed)')
        Save-P1Answer -Key 'f4_uac_prompt' -Value (Read-P1Choice -Question 'Did Windows ask "Do you want to allow this app to make changes" before it opened?')
        Save-P1Answer -Key 'f4_progress_seen' -Value (Read-P1Choice -Question 'Did the page "Long action" show a moving progress bar, then continue?')
    }

    try {
    Invoke-P1Step -Id 'probe-wait' -Title 'Wait for the boot probe and F10 to finish' -Needs 'arm' -Action {
        $script:P1.data['signed_in_utc'] = Get-UtcStamp
        $deadline = (Get-Date).AddMinutes(35)
        while ((-not (Test-Path -LiteralPath $BootTest.P1.ProbeResult)) -and ((Get-Date) -lt $deadline)) {
            $state = Read-BootTestState
            if (-not ($state.ContainsKey('p1_probe_armed') -and [bool]$state['p1_probe_armed'])) { break }
            $probeTask = Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ProbeTaskName -ErrorAction SilentlyContinue
            if ((-not $probeTask) -or ($probeTask.State -ne 'Running')) {
                $info = $null
                if ($probeTask) { $info = Get-ScheduledTaskInfo -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ProbeTaskName }
                throw ('The boot probe does not run and wrote no result (last run {0}, result 0x{1:X8}). Read logs\p1-probe.log.' -f $(if ($info) { $info.LastRunTime } else { 'never' }), $(if ($info) { $info.LastTaskResult } else { 0 }))
            }
            Write-KitLog 'The boot probe still runs (it reads /api/ready and runs F10). Waiting...'
            Start-Sleep -Seconds 30
        }
        if (Test-Path -LiteralPath $BootTest.P1.ProbeResult) {
            $script:P1.data['probe'] = Get-Content -LiteralPath $BootTest.P1.ProbeResult -Raw | ConvertFrom-Json
        } else { throw 'The boot probe wrote no result. Read logs\p1-probe.log.' }
    }
    } finally {
        # The SYSTEM task is removed after phase 2 reached this point, whatever the result: after
        # its result, after a failure, and after a skipped restart.
        if ((-not $dryRun) -and (Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ProbeTaskName -ErrorAction SilentlyContinue)) {
            Unregister-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.P1.ProbeTaskName -Confirm:$false
        }
    }

    Invoke-P1Step -Id 'idle-boot' -Title 'S1: idle memory after the restart (empty installation)' -Needs 'install' -Action {
        $null = Invoke-SvcJob -Job 's1-measure-idle-boot' -TimeoutMinutes 10 -OnPoll { Add-VmmemSample -Phase 'idle_boot' }
        Save-VmmemSummary -Phase 'idle_boot'
    }

    Invoke-P1Step -Id 'report' -Title 'S1: collect the Linux-side measurements' -Needs 'install' -Action {
        $null = Invoke-SvcJob -Job 's1-report' -TimeoutMinutes 5
        $file = Join-Path $BootTest.SvcOut 's1-report.json'
        $item = Get-Item -LiteralPath $file -Force
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 's1-report.json is a link; refused.' }
        $script:P1.data['s1'] = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
        $script:P1.data['vhd_bytes_final'] = Get-DistroVhdSize
        $script:P1.data['free_gb_final'] = Get-FreeGB
    }

    Invoke-P1Step -Id 'f4-checks' -Title 'F4: Modify and Uninstall in Settings' -SkipWith 'F4' -Needs 'f4-run' -Action {
        Wait-P1Human -Lines @('Open Settings > Apps > Installed apps. Find "Slate Operations P1 installer test".',
            'Select the three dots (...) next to it. Select "Modify" if it is there.')
        Save-P1Answer -Key 'f4_modify' -Value (Read-P1Choice -Question 'Did "Modify" exist, and did a window "Maintenance mode works" open?')
        Wait-P1Human -Lines @('In the same place, select the three dots (...) again, then "Uninstall".',
            'A page "Keep your data?" should open. Select "Keep my data", then OK. Let the uninstall finish.')
        Save-P1Answer -Key 'f4_uninstall_page' -Value (Read-P1Choice -Question 'Did the page "Keep your data?" open, and did the uninstall finish?')
    }

    $file = Write-P1Result
    Write-KitLog ('Results: {0}' -f $file) 'PASS'
    Show-P1Instruction -Lines @('P1 is complete.', ('1. Send the results file to the team: {0}' -f $file),
        '2. When the team has the results, run 90-cleanup.ps1 (it removes everything that the kit and P1 added).')
    if (-not $dryRun) { Start-Process -FilePath 'notepad.exe' -ArgumentList @(('"{0}"' -f $file)) }
}

# ---------------------------------------------------------------------------
# Results file (Markdown, no secrets)
# ---------------------------------------------------------------------------

function Get-Answer { param([string]$Key) if ($script:P1.answers.ContainsKey($Key)) { return [string]$script:P1.answers[$Key] } return '' }

function Get-Verdict {
    # PASS / FAIL / NOT RUN from a condition, with the step status as the reason when not run.
    param([string]$StepId, $Pass, [string]$NotRunReason = '')
    $status = Get-P1StepStatus -Id $StepId
    if ($status -eq 'failed') { return ('FAIL ({0})' -f ([string]$script:P1.steps[$StepId].reason -replace '\|', '/')) }
    if ($status -ne 'done') {
        $reason = $NotRunReason
        if ($script:P1.steps.ContainsKey($StepId)) { $reason = ('{0}: {1}' -f $script:P1.steps[$StepId].status, $script:P1.steps[$StepId].reason) }
        if (-not $reason) { $reason = 'not reached' }
        return ('NOT RUN ({0})' -f $reason)
    }
    if ($null -eq $Pass) { return 'NOT DETERMINED' }
    if ($Pass) { return 'PASS' } else { return 'FAIL' }
}

function ConvertTo-YesNoPass { param([string]$Answer) if ($Answer -eq 'Y') { return $true } elseif ($Answer -eq 'N') { return $false } return $null }

function Get-Path {
    # Safe nested read: Get-Path $object 'a.b.c' returns $null when a part is missing.
    param($Object, [string]$Path)
    $current = $Object
    foreach ($part in $Path.Split('.')) {
        if ($null -eq $current) { return $null }
        if ($current -is [System.Collections.IDictionary]) { $current = $current[$part] }
        elseif ($current.PSObject.Properties[$part]) { $current = $current.$part }
        else { return $null }
    }
    return $current
}

function Write-P1Result {
    $d = $script:P1.data
    $s1 = $d['s1']
    $probe = $d['probe']
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('# Slate Operations P1 results')
    $lines.Add('')
    $lines.Add(('Written {0} UTC by 30-p1.ps1. No secret values are in this file.' -f (Get-UtcStamp)))
    $lines.Add('')
    $lines.Add('## PC and versions')
    $lines.Add('')
    foreach ($key in @('windows', 'cpu', 'logical_processors', 'ram_gb', 'architecture', 'network', 'free_gb_before', 'wsl_version_before')) {
        $lines.Add(('- {0}: {1}' -f $key, (Get-Path $d ('pc.' + $key))))
    }
    $lines.Add(('- WSL version now: {0}' -f (Get-WslVersion)))
    $lines.Add(('- .wslconfig memory for slateops-svc: {0} GB; Linux MemTotal: {1}' -f $script:P1.wsl_memory_gb, $d['mem_total']))
    $lines.Add(('- Name: {0}; LAN address: {1}' -f $script:P1.host, $script:P1.lan_address))
    $lines.Add('')
    $lines.Add('## Steps')
    $lines.Add('')
    $lines.Add('| Step | Status | Reason |')
    $lines.Add('|---|---|---|')
    $order = @('checks', 'source', 'setup', 'restart-vm', 'stop-test-stack', 'install', 'network', 'idle', 'f2-local', 'backup', 'restore',
        'f1-phone', 'f1-avahi', 'spike-import', 'f5', 'f3', 'f10-prepare', 'arm', 'f4-run', 'restart', 'f4-resume', 'probe-wait', 'idle-boot', 'report', 'f4-checks')
    foreach ($id in @($order | Where-Object { $script:P1.steps.ContainsKey($_) })) {
        $lines.Add(('| {0} | {1} | {2} |' -f $id, $script:P1.steps[$id].status, ([string]$script:P1.steps[$id].reason -replace '\|', '/')))
    }
    $lines.Add('')
    $lines.Add('## S1 measurements')
    $lines.Add('')
    $lines.Add('| Measurement | Value | Source |')
    $lines.Add('|---|---|---|')
    $lines.Add(('| Windows start to HTTPS /api/ready, nobody signed in | {0} s | boot probe (Windows, curl through the hosts entry) |' -f (Get-Path $probe 'windows_start_to_ready_seconds')))
    $lines.Add(('| Signed in at ready (console user, explorer count) | {0}, {1} | boot probe |' -f (Get-Path $probe 'signed_in_at_ready.console_user_present'), (Get-Path $probe 'signed_in_at_ready.explorer_processes')))
    $boots = @(Get-Path $s1 'boots' | Where-Object { $_ })
    foreach ($boot in $boots) {
        # Get-Path: a watcher that timed out has no ready time, and strict mode stops on a missing key.
        $bootId = ([string](Get-Path $boot 'boot_id') + '--------').Substring(0, 8)
        $lines.Add(('| Linux boot {0}: Linux start to ready | {1} s (ready {2}) | Linux watcher |' -f $bootId, (Get-Path $boot 'linux_boot_to_ready_seconds'), (Get-Path $boot 'ready_utc')))
        $lines.Add(('| Linux boot {0}: memory used, startup max | {1} MiB of {2} MiB | Linux sampler (MemTotal - MemAvailable) |' -f $bootId, (Get-Path $boot 'startup_memory.used_mib_max'), (Get-Path $boot 'startup_memory.mem_total_mib')))
    }
    $lines.Add(('| WSL VM process at startup, max | {0} MiB | boot probe (vmmemWSL working set) |' -f (Get-Path $probe 'vmmem_startup_peak_mib')))
    foreach ($label in @('install', 'after_boot')) {
        $when = $(if ($label -eq 'install') { 'after the install' } else { 'after the restart' })
        $lines.Add(('| Idle memory used (Linux) {0}, file cache dropped first, mean / max; empty installation (lower limit) | {1} / {2} MiB of {3} MiB | s1.sh measure-idle |' -f $when,
            (Get-Path $s1 ('idle.' + $label + '.used_mib_mean')), (Get-Path $s1 ('idle.' + $label + '.used_mib_max')), (Get-Path $s1 ('idle.' + $label + '.mem_total_mib'))))
    }
    $lines.Add(('| Idle WSL VM process after install, median / max; empty installation (lower limit) | {0} / {1} MiB | 30-p1 (vmmemWSL) |' -f (Get-Path $d 'vmmem_idle.median_mib'), (Get-Path $d 'vmmem_idle.max_mib')))
    $lines.Add(('| Idle WSL VM process after the restart, median / max; empty installation (lower limit) | {0} / {1} MiB | 30-p1 (vmmemWSL) |' -f (Get-Path $d 'vmmem_idle_boot.median_mib'), (Get-Path $d 'vmmem_idle_boot.max_mib')))
    $lines.Add(('| Install and build WSL VM process, max (not for R4: the real installer does not build) | {0} MiB | 30-p1 (vmmemWSL) |' -f (Get-Path $d 'vmmem_install.max_mib')))
    $backups = @(Get-Path $s1 'backups' | Where-Object { $_ })
    foreach ($backup in $backups) {
        $lines.Add(('| Backup {0}: outage / backup command / restart; empty installation (lower limit) | {1} / {2} / {3} s | s1.sh backup |' -f (Get-Path $backup 'outcome'), (Get-Path $backup 'outage_seconds'), (Get-Path $backup 'backup_command_seconds'), (Get-Path $backup 'restart_seconds')))
        $lines.Add(('| Backup: memory used during it (Linux), max; empty installation (lower limit) | {0} MiB | Linux sampler |' -f (Get-Path $backup 'memory_during_backup.used_mib_max')))
        $lines.Add(('| Backup: repository size | {0} bytes | du |' -f (Get-Path $backup 'repository_bytes')))
    }
    $lines.Add(('| Backup: WSL VM process, max | {0} MiB | 30-p1 (vmmemWSL) |' -f (Get-Path $d 'vmmem_backup.max_mib')))
    $lines.Add(('| Restore: restic restore into scratch; empty installation (lower limit) | {0} s for {1} bytes | s1.sh restore-timing |' -f (Get-Path $s1 'restore_timing.restic_restore_seconds'), (Get-Path $s1 'restore_timing.restored_bytes')))
    $lines.Add(('| Restore: full restore | {0} | - |' -f (Get-Path $s1 'restore_timing.full_restore')))
    $lines.Add(('| Image total (after install) | {0} bytes | docker image inspect |' -f (Get-Path $s1 'sizes.after_install.images_total_bytes')))
    $lines.Add(('| Root file system used after install (build cache removed) | {0} bytes | df |' -f (Get-Path $s1 'sizes.after_install.root_fs.used_bytes')))
    $lines.Add(('| Root file system used after the build (with build cache) | {0} bytes | df |' -f (Get-Path $s1 'sizes.after_build.root_fs.used_bytes')))
    $lines.Add(('| VHD file after install / now (holds freed build space; the real installer does not build) | {0} / {1} bytes | ext4.vhdx size |' -f $d['vhd_bytes_after_install'], $d['vhd_bytes_final']))
    $lines.Add(('| Free space on {0} before / after install / now | {1} / {2} / {3} GB | Win32_LogicalDisk |' -f $env:SystemDrive, (Get-Path $d 'pc.free_gb_before'), $d['free_gb_after_install'], $d['free_gb_final']))
    $lines.Add('')
    # F10: judged from the probe and from the Linux watcher's boot records after msiexec started.
    $f10Info = Get-Path $probe 'f10'
    $f10Verdict = ('NOT RUN ({0})' -f (Get-Path $f10Info 'reason'))
    if ((Get-Path $f10Info 'status') -eq 'ran') {
        $msiExit = [int](Get-Path $f10Info 'msiexec_exit_code')
        $msiStart = [double](Get-Path $f10Info 'msi_start_epoch')
        $newBoots = @(@(Get-Path $s1 'boots' | Where-Object { $_ }) | Where-Object { [double](Get-Path $_ 'linux_boot_epoch') -ge ($msiStart - 5) })
        $linuxReady = @($newBoots | Where-Object { $null -ne (Get-Path $_ 'ready_epoch') }).Count -gt 0
        $windowsReady = ($null -ne (Get-Path $f10Info 'ready_again_utc'))
        $nobody = -not [bool](Get-Path $f10Info 'signed_in_at_start.console_user_present')
        if ($msiExit -eq 3010) { $f10Verdict = 'NOT DETERMINED (msiexec exit 3010: Windows must restart first)' }
        elseif ($msiExit -ne 0) { $f10Verdict = ('FAIL (msiexec exit {0})' -f $msiExit) }
        elseif ($newBoots.Count -eq 0) { $f10Verdict = 'NOT DETERMINED (VM not restarted: no new Linux boot after msiexec started)' }
        elseif ($nobody -and ($windowsReady -or $linuxReady)) { $f10Verdict = 'PASS' }
        elseif (-not $nobody) { $f10Verdict = 'FAIL (someone was signed in when msiexec started)' }
        else { $f10Verdict = 'FAIL (the service did not become ready again)' }
        $f10Verdict += (' [new Linux boot after msiexec: {0}; Linux ready: {1}; Windows probe ready again: {2}]' -f $(if ($newBoots.Count) { 'yes' } else { 'no' }), $linuxReady, $windowsReady)
    }
    $lines.Add('## Spike verdicts')
    $lines.Add('')
    $lines.Add('| Spike | Pass condition | Verdict |')
    $lines.Add('|---|---|---|')
    $lines.Add(('| F1 Windows mDNS | The phone ({0}) opens https://{1} and shows the sign-in page | {2} |' -f (Get-Answer 'phone_os'), $script:P1.host, (Get-Verdict 'f1-phone' (ConvertTo-YesNoPass (Get-Answer 'f1_https_name')))))
    $lines.Add(('| F1 Avahi second name | The phone opens http://slateops-p1.local/ and the Windows name still works | {0} |' -f (Get-Verdict 'f1-avahi' $(if ((Get-Answer 'f1_avahi_second_name') -eq 'S') { $null } else { ((Get-Answer 'f1_avahi_second_name') -eq 'Y') -and ((Get-Answer 'f1_windows_name_after_avahi') -eq 'Y') }))))
    $lines.Add(('| F2 LAN, port 443 by name | The phone reaches Caddy on 443. This row repeats the F1 answer (the same phone check), so a failed F1 name lookup also fails it | {0} |' -f (Get-Verdict 'f1-phone' (ConvertTo-YesNoPass (Get-Answer 'f1_https_name')))))
    $lines.Add(('| F2 LAN, port 80 by address | The phone opens http://{0}/ (Docker-published port 80 in mirrored mode; standalone test page, the product has no :80 listener yet) | {1} |' -f $script:P1.lan_address, (Get-Verdict 'f1-phone' (ConvertTo-YesNoPass (Get-Answer 'f2_http80_ip')))))
    $lines.Add(('| F2 server PC through hosts | This PC reads https://{0}/api/ready = 200 | {1} |' -f $script:P1.host, (Get-Verdict 'f2-local' ((Get-Path $d 'f2_local.api_ready_code') -eq '200'))))
    $f3pass = ((Get-Path $d 'f3.unregister.kept_exists_after') -eq $true) -and ((Get-Path $d 'f3.unregister.kept_bytes_after') -eq (Get-Path $d 'f3.unregister.kept_bytes_before')) -and ((Get-Path $d 'f3.import_in_place.marker_match') -eq $true)
    $lines.Add(('| F3 | After the move, unregister keeps the disk (same size), and import-in-place under a new account reads the marker | {0} |' -f (Get-Verdict 'f3' $f3pass)))
    $f4 = @()
    if ((-not $dryRun) -and (Test-Path -LiteralPath $BootTest.P1.F4ResultFile)) { $f4 = @(Get-Content -LiteralPath $BootTest.P1.F4ResultFile) }
    $d['f4_results'] = $f4
    $resumeVerdict = Get-Verdict 'f4-resume' (($f4 -contains 'resume_is_admin=1') -and ((Get-Answer 'f4_resumed_window') -eq 'Y'))
    if ($resumeVerdict -eq 'PASS') { $resumeVerdict = $(if ((Get-Answer 'f4_uac_prompt') -eq 'Y') { 'PASS (UAC prompt)' } elseif ((Get-Answer 'f4_uac_prompt') -eq 'N') { 'PASS (no prompt)' } else { 'PASS (prompt not recorded)' }) }
    $lines.Add(('| F4 RunOnce resume elevates | The test installer opens again after the sign-in and runs as administrator. "UAC prompt" means RunOnce started it without elevation and Setup asked | {0} |' -f $resumeVerdict))
    $lines.Add(('| F4 long action with progress | The progress page moves and the action ends | {0} |' -f (Get-Verdict 'f4-resume' (($f4 -contains 'long_action=ok') -and ((Get-Answer 'f4_progress_seen') -eq 'Y')))))
    $lines.Add(('| F4 named pipe (Pascal Script pipe server, no helper) | The Exec job reads the value through the pipe and answers its SHA-256 | {0} |' -f (Get-Verdict 'f4-resume' ($f4 -contains 'pipe=ok'))))
    $lines.Add(('| F4 Modify in Settings | "Modify" opens the maintenance window | {0} |' -f (Get-Verdict 'f4-checks' (($f4 -contains 'modify_opened=1') -or ((Get-Answer 'f4_modify') -eq 'Y')))))
    $lines.Add(('| F4 custom uninstall page | "Keep your data?" opens and the uninstall ends | {0} |' -f (Get-Verdict 'f4-checks' (((Get-Answer 'f4_uninstall_page') -eq 'Y') -and (@($f4 | Where-Object { $_ -like 'uninstall_choice=*' }).Count -gt 0)))))
    $f5json = $null
    try { if (Get-Path $d 'f5.result') { $f5json = (Get-Path $d 'f5.result') | ConvertFrom-Json } } catch { $f5json = $null }
    $lines.Add(('| F5 | drvfs mounts the USB drive with automount off; Restic backup and check pass ({0} MiB/s backup) | {1} |' -f (Get-Path $f5json 'backup_mib_per_second'), (Get-Verdict 'f5' ([bool](Get-Path $f5json 'mounted') -and ((Get-Path $d 'f5.job_exit') -eq 0)))))
    $lines.Add(('| F10 | The WSL MSI ({0}) installs from the SYSTEM task with nobody signed in, the WSL VM restarts, and the service is ready again by itself (Windows probe or the Linux watcher''s new boot record) | {1} |' -f (Get-Path $f10Info 'mode'), $f10Verdict))
    $lines.Add('')
    $lines.Add('## Raw data (JSON)')
    $lines.Add('')
    $lines.Add('```json')
    $lines.Add((ConvertTo-Json -InputObject ([ordered]@{ answers = $script:P1.answers; data = $d; steps = $script:P1.steps }) -Depth 10))
    $lines.Add('```')
    $name = 'p1-results-{0}.md' -f (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
    $file = Join-Path $BootTest.Logs $name
    if (-not $dryRun) {
        Set-Content -LiteralPath $file -Value $lines -Encoding UTF8
        $desktop = [Environment]::GetFolderPath('Desktop')
        if ($desktop -and (Test-Path -LiteralPath $desktop)) { Copy-Item -LiteralPath $file -Destination (Join-Path $desktop $name); $file = Join-Path $desktop $name }
    } else {
        foreach ($line in $lines) { Write-KitLog ('  {0}' -f $line) 'WHATIF' }
    }
    return $file
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

try {
    Assert-Administrator
    if ((-not $dryRun) -and (Test-Path -LiteralPath $BootTest.Root)) {
        $problems = @(Get-BootTestTreeProblem -Quick -Directory $BootTest.State)
        if ($problems.Count -gt 0) { throw ('{0} fails the safety check: {1}. Run 90-cleanup.ps1, then run again.' -f $BootTest.Root, ($problems -join '; ')) }
    }
    Initialize-BootTestLog -Name '30-p1' -DryRun:$dryRun
    Write-KitLog ('Slate Operations P1 (installer plan S1 and spikes): {0}.' -f $(if ($Resume) { 'phase 2, after the restart' } else { 'phase 1' })) 'STEP'
    if ($dryRun) { Write-KitLog 'Dry run (-WhatIf): nothing changes.' 'WHATIF' }
    $script:P1 = Read-P1State
    $allowedSkip = @('S1', 'Backup', 'Restore', 'F1', 'F1Avahi', 'F2Phone', 'F3', 'F4', 'F5', 'F10')
    $skipItems = @($Skip -split '[,;\s]+' | Where-Object { $_ } | ForEach-Object {
            $item = $_
            $match = @($allowedSkip | Where-Object { $_ -ieq $item })
            if ($match.Count -eq 0) { throw ('-Skip: unknown step "{0}". Use: {1}.' -f $item, ($allowedSkip -join ', ')) }
            $match[0]
        })
    if ((-not $Resume) -and $PSBoundParameters.ContainsKey('Skip')) { $script:P1.skip = $skipItems }
    if (-not $script:P1.host) { $script:P1.host = ('{0}.local' -f ([string](Get-CimInstance -ClassName Win32_ComputerSystem).DNSHostName).ToLowerInvariant()) }
    $script:SkipList = @($script:P1.skip)
    if ($Resume -or ($script:P1.phase -eq 'restarting') -or ($script:P1.phase -eq 'after-restart')) { Invoke-Phase2 } else { Invoke-Phase1 }
    exit 0
} catch {
    Write-KitLog ('P1 stopped: {0}' -f $_.Exception.Message) 'ERROR'
    Write-KitLog ($_.InvocationInfo.PositionMessage) 'ERROR'
    $logFile = Get-BootTestLogFile
    if ($logFile) { Write-KitLog ('Log: {0}. Correct the cause and run 30-p1.ps1 again; finished steps are skipped.' -f $logFile) 'ERROR' }
    exit 1
}
