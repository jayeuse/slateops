<#
svc-exec.ps1 - runs one allow-listed job as the service account slateops-svc.

The on-demand scheduled task \SlateOpsBootTest\Exec starts this script as slateops-svc
("Run whether user is logged on or not"). WSL distributions and .wslconfig belong to the
user who runs wsl.exe, so every WSL step for the test distribution must run here, not
in the owner's session.

Input: C:\ProgramData\SlateOpsBootTest\state\request.txt, "<job> <request-id>". Only
administrators can write that file. Jobs:
  prepare     Write the account's .wslconfig, import Debian, configure systemd, install
              Docker Engine, start the test stack.
  status      Report WSL and the stack. It never starts a stopped distribution.
  unregister  Stop and unregister the distribution, remove the account's .wslconfig.
P1 jobs (installer plan slice S1 and spikes; parameters come from state.json):
  restart-vm        wsl --shutdown for this account, so .wslconfig applies; the boot task
                    attaches again within a minute.
  s1-<command>      Run linux/s1/s1.sh <command> in the distribution as root (install,
                    stop-test-stack, measure-idle (after install, after the restart), backup,
                    restore-timing, report, port80 start/stop, avahi start/stop, abort, remove).
  spike-import      Import the throwaway distribution SlateOpsSpike (automount off) for F3/F5.
  f5-drvfs          F5: mount the USB drive with drvfs in SlateOpsSpike; time Restic on it.
  f3-move           F3: stop SlateOpsSpike and move its disk out of the registered folder.
  f3-unregister     F3: unregister SlateOpsSpike; check that the moved disk stays.
  spike-unregister  Cleanup: unregister SlateOpsSpike if it exists.
  f4-pipe           F4: connect to the wizard's named pipe, check its owner, answer SHA-256.
  spike-clean       Delete everything inside the spike folder (as this account; the
                    administrator side then deletes only the emptied folder).
  f5-clean          Delete everything inside the F5 folder on the USB drive (same rule).
  As the throwaway account slateops-f3 (task \SlateOpsBootTest\F3) only:
  f3-import-in-place  F3: register the moved disk under this new account; read the marker.
  f3-cleanup          Unregister the F3 distribution of this account.
Output: <out>\svc-exec-<job>.log and <out>\svc-exec-result.json (request ID, exit code and
safe job data). <out> is svc-out for slateops-svc and f3-out for slateops-f3; the
administrator side only reads it.
The admin side (Invoke-SvcJob in common.ps1) waits for that result.

-WhatIf: log the steps of the requested job and change nothing.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()

. (Join-Path $PSScriptRoot 'common.ps1')

$isF3 = ($env:USERNAME -ieq $BootTest.P1.F3AccountName)
if ($isF3) { $jobNames = $BootTest.F3Jobs; $outDir = $BootTest.F3Out } else { $jobNames = $BootTest.SvcJobs; $outDir = $BootTest.SvcOut }
$resultFile = Join-Path $outDir 'svc-exec-result.json'
$requestId = ''
$job = ''
$exitCode = 1
# Safe values (no secrets) that a job returns to the administrator side in the result file.
$script:JobData = [ordered]@{}

function Get-LinuxPath {
    # C:\ProgramData\SlateOpsBootTest\kit\linux -> /mnt/c/ProgramData/SlateOpsBootTest/kit/linux
    param([Parameter(Mandatory = $true)][string]$WindowsPath)
    $drive = $WindowsPath.Substring(0, 1).ToLowerInvariant()
    $rest = $WindowsPath.Substring(2) -replace '\\', '/'
    return ('/mnt/{0}{1}' -f $drive, $rest)
}

function Test-DistroRegistered {
    $list = Invoke-Wsl -ArgumentList @('--list', '--quiet') -NoThrow -Quiet
    return (@($list.Output | Where-Object { $_.Trim() -eq $BootTest.DistroName }).Count -gt 0)
}

function Test-DistroRunning {
    $list = Invoke-Wsl -ArgumentList @('--list', '--running', '--quiet') -NoThrow -Quiet
    return (@($list.Output | Where-Object { $_.Trim() -eq $BootTest.DistroName }).Count -gt 0)
}

function Get-DistroNetworkingMode {
    # Asks WSL inside the distribution which networking mode it uses (wslinfo --networking-mode).
    $result = Invoke-Wsl -ArgumentList @('-d', $BootTest.DistroName, '-u', 'root', '--exec', '/bin/sh', '-c', 'wslinfo --networking-mode') -NoThrow
    $mode = @($result.Output | Where-Object { $_.Trim() }) | Select-Object -First 1
    if ($null -eq $mode) { return '' }
    return ([string]$mode).Trim().ToLowerInvariant()
}

function Write-WslConfig {
    param([Parameter(Mandatory = $true)][int]$MemoryGB)
    $path = Join-Path $env:USERPROFILE '.wslconfig'
    # vmIdleTimeout=-1 keeps the WSL VM, instanceIdleTimeout=-1 keeps the distribution:
    # WSL needs both to keep running with no interactive user (WSL maintainer, issue #13291).
    $lines = @(
        '# Written by the Slate Operations boot-test kit for the account slateops-svc.',
        '[wsl2]',
        ('memory={0}GB' -f $MemoryGB),
        'vmIdleTimeout=-1',
        'networkingMode=mirrored',
        ('defaultVhdSize={0}' -f $BootTest.DistroDiskSize),
        '',
        '[general]',
        'instanceIdleTimeout=-1'
    )
    Invoke-Step ('Write {0}' -f $path) {
        Set-Content -LiteralPath $path -Value $lines -Encoding ASCII
        foreach ($line in $lines) { Write-KitLog ('  {0}' -f $line) }
    }
}

function Expand-GzipFile {
    param([Parameter(Mandatory = $true)][string]$Source, [Parameter(Mandatory = $true)][string]$Destination)
    $in = [System.IO.File]::OpenRead($Source)
    try {
        $gzip = New-Object System.IO.Compression.GZipStream($in, [System.IO.Compression.CompressionMode]::Decompress)
        $out = [System.IO.File]::Create($Destination)
        try { $gzip.CopyTo($out) } finally { $out.Dispose(); $gzip.Dispose() }
    } finally { $in.Dispose() }
}

function Invoke-PrepareJob {
    $state = Read-BootTestState
    $memory = 6
    if ($state.ContainsKey('wsl_memory_gb')) { $memory = [int]$state['wsl_memory_gb'] }
    $webNetwork = 'bridge'
    if ($state.ContainsKey('web_network')) { $webNetwork = [string]$state['web_network'] }
    Write-KitLog ('Account: {0}; profile: {1}; memory {2} GB; web network {3}' -f $env:USERNAME, $env:USERPROFILE, $memory, $webNetwork)

    Write-WslConfig -MemoryGB $memory

    if (Test-DistroRegistered) {
        Write-KitLog ('Distribution {0} is already registered for this account; import skipped.' -f $BootTest.DistroName)
    } else {
        $arch = Get-Architecture
        $wslFile = Join-Path $BootTest.Cache ('debian-{0}.wsl' -f $arch.ToLowerInvariant())
        $tarFile = Join-Path $BootTest.Distro 'rootfs.tar'
        $vhdDir = Join-Path $BootTest.Distro 'vhd'
        Invoke-Step ('Check SHA-256 of {0}' -f $wslFile) {
            $hash = (Get-FileHash -LiteralPath $wslFile -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($hash -ne $BootTest.Rootfs[$arch].Sha256) { throw ('SHA-256 mismatch for {0}: {1}' -f $wslFile, $hash) }
            Write-KitLog ('  SHA-256 {0} (matches the pinned value)' -f $hash)
        }
        # The .wsl file is a gzip-compressed tar. Decompress it so "wsl --import" gets a plain tar.
        Invoke-Step ('Decompress {0} to {1}' -f $wslFile, $tarFile) { Expand-GzipFile -Source $wslFile -Destination $tarFile }
        Invoke-Step ('Import distribution {0} into {1}' -f $BootTest.DistroName, $vhdDir) {
            New-Item -ItemType Directory -Path $vhdDir -Force | Out-Null
            Invoke-Wsl -ArgumentList @('--import', $BootTest.DistroName, $vhdDir, $tarFile, '--version', '2') | Out-Null
        }
        Invoke-Step ('Remove {0}' -f $tarFile) { Remove-Item -LiteralPath $tarFile -Force }
    }

    $lib = $BootTest.LinuxLib
    Copy-LinuxKit
    Invoke-Step 'Write /etc/wsl.conf (systemd on)' {
        Invoke-Wsl -ArgumentList @('-d', $BootTest.DistroName, '-u', 'root', '--exec', '/bin/sh', "$lib/setup-base.sh") | Out-Null
    }
    Invoke-Step ('Restart the distribution so systemd starts (wsl --terminate {0})' -f $BootTest.DistroName) {
        Invoke-Wsl -ArgumentList @('--terminate', $BootTest.DistroName) | Out-Null
        $deadline = (Get-Date).AddSeconds(60)
        while ((Test-DistroRunning) -and ((Get-Date) -lt $deadline)) { Start-Sleep -Seconds 2 }
        if (Test-DistroRunning) { throw 'The distribution did not stop within 60 s.' }
    }
    Invoke-Step ('Install Docker Engine and start the test stack (profile {0}); this can take 10 minutes' -f $webNetwork) {
        Invoke-Wsl -ArgumentList @('-d', $BootTest.DistroName, '-u', 'root', '--exec', '/bin/bash', "$lib/setup-docker.sh", $webNetwork) | Out-Null
    }
    Invoke-Step 'Check that the distribution uses mirrored networking' {
        $mode = Get-DistroNetworkingMode
        if ($mode -ne 'mirrored') { throw ('The distribution uses networking mode "{0}", not "mirrored". Read the .wslconfig lines above.' -f $mode) }
        Write-KitLog '  Networking mode: mirrored.' 'PASS'
    }
    Invoke-Step 'Record WSL state' {
        Invoke-Wsl -ArgumentList @('--version') -NoThrow | Out-Null
        Invoke-Wsl -ArgumentList @('--list', '--verbose') -NoThrow | Out-Null
    }
}

function Copy-LinuxKit {
    # Copy the Linux files into the distribution and strip Windows line ends (CR) from them.
    # The command holds no double quotes, so Windows PowerShell 5.1 passes it to wsl.exe intact.
    $linuxKit = Get-LinuxPath -WindowsPath (Join-Path $BootTest.Kit 'linux')
    $lib = $BootTest.LinuxLib
    $copy = ('rm -rf {0} && mkdir -p {0} && cp -R {1}/. {0}/ && find {0} -type f -exec sed -i ''s/\r$//'' {{}} + && find {0} -type f -name ''*.sh'' -exec chmod 0755 {{}} + && chmod 0755 {0}/payload/www/cgi-bin/index.cgi' -f $lib, $linuxKit)
    Invoke-Step ('Copy the Linux kit files to {0} in the distribution' -f $lib) {
        Invoke-Wsl -ArgumentList @('-d', $BootTest.DistroName, '-u', 'root', '--exec', '/bin/sh', '-c', $copy) | Out-Null
    }
}

function Get-P1Parameter {
    # Reads one P1 parameter from state.json (only administrators write that file) and checks
    # it against a pattern. A value that does not match stops the job.
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][string]$Pattern)
    $state = Read-BootTestState
    if (-not $state.ContainsKey($Name)) { throw ('state.json has no {0}.' -f $Name) }
    $value = [string]$state[$Name]
    if ($value -notmatch $Pattern) { throw ('state.json value {0} has an unexpected form.' -f $Name) }
    return $value
}

function Invoke-RestartVmJob {
    Invoke-Step 'Stop the WSL VM of this account (wsl --shutdown), so .wslconfig applies at the next start' {
        Invoke-Wsl -ArgumentList @('--shutdown') | Out-Null
    }
    Invoke-Step 'Wait until the boot task attaches the distribution again (up to 3 minutes)' {
        $deadline = (Get-Date).AddMinutes(3)
        while ((-not (Test-DistroRunning)) -and ((Get-Date) -lt $deadline)) { Start-Sleep -Seconds 5 }
        if (-not (Test-DistroRunning)) { throw 'The distribution did not start again within 3 minutes. Run 20-status.ps1.' }
        Write-KitLog '  The distribution runs again.' 'PASS'
        $memory = Invoke-Wsl -ArgumentList @('-d', $BootTest.DistroName, '-u', 'root', '--exec', '/bin/sh', '-c', 'grep MemTotal /proc/meminfo') -NoThrow
        $script:JobData['mem_total'] = (@($memory.Output) -join ' ')
    }
}

function Invoke-S1Job {
    param([Parameter(Mandatory = $true)][string]$Name)
    $s1 = $BootTest.P1.LinuxS1
    $arguments = switch ($Name) {
        's1-install' {
            $hostName = Get-P1Parameter -Name 'p1_host' -Pattern '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.local$'
            @('install', '--host', $hostName, '--source', (Get-LinuxPath -WindowsPath $BootTest.P1.SourceTar))
        }
        's1-port80-start' { @('port80', 'start') }
        's1-port80-stop' { @('port80', 'stop') }
        's1-avahi-start' { @('avahi', 'start', (Get-P1Parameter -Name 'p1_avahi_name' -Pattern '^[a-z0-9-]{1,40}\.local$')) }
        's1-avahi-stop' { @('avahi', 'stop') }
        's1-measure-idle' { @('measure-idle', 'install') }
        's1-measure-idle-boot' { @('measure-idle', 'after_boot') }
        default { @($Name.Substring(3)) }
    }
    if (@('s1-remove', 's1-abort') -notcontains $Name) { Copy-LinuxKit }
    $result = Invoke-Wsl -ArgumentList (@('-d', $BootTest.DistroName, '-u', 'root', '--exec', '/bin/bash', $s1) + $arguments) -NoThrow
    if ($Name -eq 's1-report') {
        $json = @($result.Output | Where-Object { $_.StartsWith('{') }) | Select-Object -Last 1
        if ($json) { Set-Content -LiteralPath (Join-Path $outDir 's1-report.json') -Value $json -Encoding UTF8 }
    }
    if ($result.ExitCode -ne 0) { throw ('s1.sh {0} failed with exit code {1}.' -f ($arguments -join ' '), $result.ExitCode) }
}

function Get-SpikeVhd { return (Join-Path $BootTest.Spike 'vhd\ext4.vhdx') }
function Get-SpikeKeptVhd { return (Join-Path $BootTest.Spike 'kept\ext4.vhdx') }

function Test-NamedDistroRegistered {
    param([Parameter(Mandatory = $true)][string]$Name)
    $list = Invoke-Wsl -ArgumentList @('--list', '--quiet') -NoThrow -Quiet
    return (@($list.Output | Where-Object { $_.Trim() -eq $Name }).Count -gt 0)
}

function Invoke-SpikeImportJob {
    $name = $BootTest.P1.SpikeDistroName
    $marker = Get-P1Parameter -Name 'p1_spike_marker' -Pattern '^[0-9a-f]{32}$'
    if (Test-NamedDistroRegistered -Name $name) { throw ('{0} is already registered. Run 90-cleanup.ps1 -P1Only first.' -f $name) }
    $arch = Get-Architecture
    $wslFile = Join-Path $BootTest.Cache ('debian-{0}.wsl' -f $arch.ToLowerInvariant())
    $hash = (Get-FileHash -LiteralPath $wslFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $BootTest.Rootfs[$arch].Sha256) { throw ('SHA-256 mismatch for {0}: {1}' -f $wslFile, $hash) }
    $tarFile = Join-Path $BootTest.Spike 'rootfs.tar'
    $vhdDir = Join-Path $BootTest.Spike 'vhd'
    Invoke-Step ('Import the throwaway distribution {0} into {1}' -f $name, $vhdDir) {
        Expand-GzipFile -Source $wslFile -Destination $tarFile
        New-Item -ItemType Directory -Path $vhdDir -Force | Out-Null
        Invoke-Wsl -ArgumentList @('--import', $name, $vhdDir, $tarFile, '--version', '2') | Out-Null
        Remove-Item -LiteralPath $tarFile -Force
    }
    # While automount is still on (first start), copy the F5 script in. Then turn automount,
    # interop and systemd off, as the installer's Linux image will (plan 3.1).
    $f5 = Get-LinuxPath -WindowsPath (Join-Path $BootTest.Kit 'linux\s1\f5.sh')
    $setup = ('sed ''s/\r$//'' {0} > /usr/local/bin/p1-f5.sh && chmod 0755 /usr/local/bin/p1-f5.sh && echo {1} > /root/p1-marker && printf ''[automount]\nenabled=false\n\n[interop]\nenabled=false\nappendWindowsPath=false\n\n[boot]\nsystemd=false\n\n[user]\ndefault=root\n'' > /etc/wsl.conf' -f $f5, $marker)
    Invoke-Step ('Write the marker and /etc/wsl.conf (automount off) in {0}' -f $name) {
        Invoke-Wsl -ArgumentList @('-d', $name, '-u', 'root', '--exec', '/bin/sh', '-c', $setup) | Out-Null
        Invoke-Wsl -ArgumentList @('--terminate', $name) | Out-Null
    }
    $check = Invoke-Wsl -ArgumentList @('-d', $name, '-u', 'root', '--exec', '/bin/sh', '-c', 'if [ -e /mnt/c/Windows ]; then echo automount-on; else echo automount-off; fi') -NoThrow
    $script:JobData['automount'] = (@($check.Output) -join ' ').Trim()
    if ($script:JobData['automount'] -ne 'automount-off') { throw 'Automount is still on in the throwaway distribution.' }
    Write-KitLog '  Automount is off in the throwaway distribution.' 'PASS'
}

function Invoke-F5Job {
    $name = $BootTest.P1.SpikeDistroName
    $drive = Get-P1Parameter -Name 'p1_f5_drive' -Pattern '^[D-Z]$'
    $folder = Get-P1Parameter -Name 'p1_f5_folder' -Pattern '^SlateOps-F5-[0-9a-f]{8}$'
    $result = Invoke-Wsl -ArgumentList @('-d', $name, '-u', 'root', '--exec', '/bin/bash', '/usr/local/bin/p1-f5.sh', ('{0}:' -f $drive), $folder) -NoThrow
    $json = @($result.Output | Where-Object { $_.StartsWith('{') }) | Select-Object -Last 1
    if ($json) { $script:JobData['f5'] = $json }
    if ($result.ExitCode -ne 0) { throw ('p1-f5.sh failed with exit code {0}.' -f $result.ExitCode) }
}

function Invoke-F3MoveJob {
    $name = $BootTest.P1.SpikeDistroName
    $source = Get-SpikeVhd
    $target = Get-SpikeKeptVhd
    Invoke-Wsl -ArgumentList @('--terminate', $name) -NoThrow | Out-Null
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    $moved = $false
    $script:JobData['shutdown_fallback'] = $false
    foreach ($round in 1, 2) {
        $deadline = (Get-Date).AddSeconds(60)
        while ((-not $moved) -and ((Get-Date) -lt $deadline)) {
            try { Move-Item -LiteralPath $source -Destination $target -ErrorAction Stop; $moved = $true }
            catch { Start-Sleep -Seconds 5 }
        }
        if ($moved -or ($round -eq 2)) { break }
        # The disk stays attached to the account's WSL VM. Stop the VM (the main distribution
        # too; the boot task attaches it again) and record the fallback.
        Write-KitLog '  The disk is still in use after wsl --terminate; stopping the WSL VM of this account.' 'WARN'
        $script:JobData['shutdown_fallback'] = $true
        Invoke-Wsl -ArgumentList @('--shutdown') -NoThrow | Out-Null
    }
    $script:JobData['moved'] = $moved
    if (-not $moved) { throw ('Could not move {0}.' -f $source) }
    Write-KitLog ('  Moved {0} to {1}.' -f $source, $target) 'PASS'
}

function Invoke-F3UnregisterJob {
    $name = $BootTest.P1.SpikeDistroName
    $kept = Get-SpikeKeptVhd
    $before = (Get-Item -LiteralPath $kept).Length
    # A failed unregister is an F3 answer too: record its exit code, never stop here.
    $unregister = Invoke-Wsl -ArgumentList @('--unregister', $name) -NoThrow
    $script:JobData['unregister_exit'] = $unregister.ExitCode
    $script:JobData['registered_after'] = (Test-NamedDistroRegistered -Name $name)
    $script:JobData['kept_exists_after'] = (Test-Path -LiteralPath $kept)
    $script:JobData['kept_bytes_before'] = $before
    if ($script:JobData['kept_exists_after']) { $script:JobData['kept_bytes_after'] = (Get-Item -LiteralPath $kept).Length }
    $script:JobData['old_folder_files'] = @(Get-ChildItem -LiteralPath (Join-Path $BootTest.Spike 'vhd') -Force -ErrorAction SilentlyContinue).Count
}

function Invoke-SpikeUnregisterJob {
    $name = $BootTest.P1.SpikeDistroName
    if (Test-NamedDistroRegistered -Name $name) {
        Invoke-Step ('Unregister the throwaway distribution {0}' -f $name) { Invoke-Wsl -ArgumentList @('--unregister', $name) -NoThrow | Out-Null }
    } else { Write-KitLog ('{0} is not registered for this account.' -f $name) }
}

function Invoke-F3ImportInPlaceJob {
    $name = $BootTest.P1.SpikeDistroName + 'F3'
    $marker = Get-P1Parameter -Name 'p1_spike_marker' -Pattern '^[0-9a-f]{32}$'
    $kept = Get-SpikeKeptVhd
    $import = Invoke-Wsl -ArgumentList @('--import-in-place', $name, $kept) -NoThrow
    $script:JobData['import_in_place_exit'] = $import.ExitCode
    if ($import.ExitCode -ne 0) { throw ('wsl --import-in-place failed with exit code {0}.' -f $import.ExitCode) }
    $read = Invoke-Wsl -ArgumentList @('-d', $name, '-u', 'root', '--exec', '/bin/cat', '/root/p1-marker') -NoThrow
    $script:JobData['marker_match'] = ((@($read.Output) -join '').Trim() -eq $marker)
    Invoke-Wsl -ArgumentList @('--unregister', $name) -NoThrow | Out-Null
    Invoke-Wsl -ArgumentList @('--shutdown') -NoThrow | Out-Null
    if (-not $script:JobData['marker_match']) { throw 'The marker in the re-registered disk does not match.' }
}

function Invoke-F3CleanupJob {
    $name = $BootTest.P1.SpikeDistroName + 'F3'
    if (Test-NamedDistroRegistered -Name $name) { Invoke-Wsl -ArgumentList @('--unregister', $name) -NoThrow | Out-Null }
    Invoke-Wsl -ArgumentList @('--shutdown') -NoThrow | Out-Null
}

function Clear-FolderContent {
    # Runs as slateops-svc: deletes the items inside a folder that this account may change. It
    # never follows a link (Remove-PathNoFollow), and the folder itself stays.
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { Write-KitLog ('{0} does not exist.' -f $Path); return }
    $count = 0
    foreach ($child in @(Get-ChildItem -LiteralPath $Path -Force)) { Remove-PathNoFollow -Path $child.FullName; $count++ }
    $script:JobData['removed_items'] = $count
    Write-KitLog ('  Emptied {0} ({1} top-level items).' -f $Path, $count) 'PASS'
}

function Invoke-SpikeCleanJob {
    if (Test-NamedDistroRegistered -Name $BootTest.P1.SpikeDistroName) { throw 'SlateOpsSpike is still registered; unregister it first.' }
    Clear-FolderContent -Path $BootTest.Spike
}

function Invoke-F5CleanJob {
    $drive = Get-P1Parameter -Name 'p1_f5_drive' -Pattern '^[D-Z]$'
    $folder = Get-P1Parameter -Name 'p1_f5_folder' -Pattern '^SlateOps-F5-[0-9a-f]{8}$'
    Clear-FolderContent -Path ('{0}:\{1}' -f $drive, $folder)
}

function Invoke-F4PipeJob {
    # The F4 wizard created \\.\pipe\slateops-p1-f4-<request id> (first instance, no remote
    # clients, access for Administrators and slateops-svc only) before it started this job.
    # Check the pipe owner first, then read one line (at most 4096 bytes) and answer its
    # SHA-256. The value itself is never written to a log.
    $pipeName = 'slateops-p1-f4-{0}' -f $requestId
    $client = New-Object System.IO.Pipes.NamedPipeClientStream('.', $pipeName, [System.IO.Pipes.PipeDirection]::InOut)
    try {
        $client.Connect(30000)
        $script:JobData['connected'] = $true
        $security = $client.GetAccessControl()
        $owner = $security.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
        $script:JobData['owner_sid'] = $owner
        $script:JobData['dacl'] = $security.GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access)
        if ($owner -ne $BootTest.SidAdministrators) { throw ('The pipe owner is {0}, not Administrators. Refused.' -f $owner) }
        $bytes = New-Object System.Collections.Generic.List[byte]
        while ($bytes.Count -lt 4096) {
            $next = $client.ReadByte()
            if (($next -lt 0) -or ($next -eq 10)) { break }
            $bytes.Add([byte]$next)
        }
        $script:JobData['bytes_read'] = $bytes.Count
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { $hex = -join ($sha.ComputeHash($bytes.ToArray()) | ForEach-Object { $_.ToString('x2') }) } finally { $sha.Dispose() }
        $answer = [System.Text.Encoding]::ASCII.GetBytes($hex + "`n")
        $client.Write($answer, 0, $answer.Length)
        $client.Flush()
        Write-KitLog ('  Read {0} bytes from the pipe and answered their SHA-256 (the value is not logged).' -f $bytes.Count) 'PASS'
    } finally { $client.Dispose() }
}

function Invoke-StatusJob {
    Invoke-Wsl -ArgumentList @('--version') -NoThrow | Out-Null
    Invoke-Wsl -ArgumentList @('--list', '--verbose') -NoThrow | Out-Null
    $config = Join-Path $env:USERPROFILE '.wslconfig'
    if (Test-Path -LiteralPath $config) {
        Write-KitLog ('{0}:' -f $config)
        foreach ($line in (Get-Content -LiteralPath $config)) { Write-KitLog ('  {0}' -f $line) }
    } else {
        Write-KitLog ('{0} is missing.' -f $config) 'WARN'
    }
    if (-not (Test-DistroRegistered)) { Write-KitLog ('Distribution {0} is not registered.' -f $BootTest.DistroName) 'FAIL'; return }
    if (-not (Test-DistroRunning)) {
        Write-KitLog ('Distribution {0} is NOT running. This job does not start it, so the test result stays true.' -f $BootTest.DistroName) 'FAIL'
        return
    }
    Write-KitLog ('Distribution {0} is running.' -f $BootTest.DistroName) 'PASS'
    $mode = Get-DistroNetworkingMode
    if ($mode -eq 'mirrored') { Write-KitLog 'Networking mode: mirrored.' 'PASS' }
    else { Write-KitLog ('Networking mode: "{0}", not "mirrored". The LAN cannot reach the service in this mode.' -f $mode) 'FAIL' }
    Invoke-Wsl -ArgumentList @('-d', $BootTest.DistroName, '-u', 'root', '--exec', '/bin/sh', ('{0}/status.sh' -f $BootTest.LinuxLib)) -NoThrow | Out-Null
}

function Invoke-UnregisterJob {
    if (Test-DistroRegistered) {
        Invoke-Step ('Stop distribution {0}' -f $BootTest.DistroName) {
            Invoke-Wsl -ArgumentList @('--terminate', $BootTest.DistroName) -NoThrow | Out-Null
        }
        Invoke-Step ('Unregister distribution {0} (deletes its virtual disk)' -f $BootTest.DistroName) {
            Invoke-Wsl -ArgumentList @('--unregister', $BootTest.DistroName) | Out-Null
        }
    } else {
        Write-KitLog ('Distribution {0} is not registered; nothing to unregister.' -f $BootTest.DistroName)
    }
    Invoke-Step 'Stop the WSL VM of this account (wsl --shutdown)' {
        Invoke-Wsl -ArgumentList @('--shutdown') -NoThrow | Out-Null
    }
    $config = Join-Path $env:USERPROFILE '.wslconfig'
    if (Test-Path -LiteralPath $config) {
        Invoke-Step ('Remove {0}' -f $config) { Remove-Item -LiteralPath $config -Force }
    }
}

try {
    $raw = (Get-Content -LiteralPath $BootTest.RequestFile -Raw).Trim()
    $parts = @($raw -split '\s+')
    if ($parts.Count -ne 2) { throw 'The request file must hold "<job> <request-id>".' }
    $job = $parts[0].ToLowerInvariant()
    $requestId = $parts[1]
    if ($jobNames -notcontains $job) { throw ('Unknown job "{0}". Allowed: {1}.' -f $job, ($jobNames -join ', ')) }
    $null = [guid]::Parse($requestId)

    $dryRun = [bool]$WhatIfPreference
    Initialize-BootTestLog -Name ('svc-exec-{0}' -f $job) -Append -DryRun:$dryRun -Directory $outDir
    # Delete this account's own old result, so the administrator side never needs to write here.
    if ((-not $dryRun) -and (Test-Path -LiteralPath $resultFile)) { Remove-Item -LiteralPath $resultFile -Force }
    Write-KitLog ('==== Job "{0}" started (request {1}) as {2} ====' -f $job, $requestId, $env:USERNAME)
    switch -Wildcard ($job) {
        'prepare'            { Invoke-PrepareJob }
        'status'             { Invoke-StatusJob }
        'unregister'         { Invoke-UnregisterJob }
        'restart-vm'         { Invoke-RestartVmJob }
        's1-*'               { Invoke-S1Job -Name $job }
        'spike-import'       { Invoke-SpikeImportJob }
        'f5-drvfs'           { Invoke-F5Job }
        'f3-move'            { Invoke-F3MoveJob }
        'f3-unregister'      { Invoke-F3UnregisterJob }
        'spike-unregister'   { Invoke-SpikeUnregisterJob }
        'f4-pipe'            { Invoke-F4PipeJob }
        'spike-clean'        { Invoke-SpikeCleanJob }
        'f5-clean'           { Invoke-F5CleanJob }
        'f3-import-in-place' { Invoke-F3ImportInPlaceJob }
        'f3-cleanup'         { Invoke-F3CleanupJob }
    }
    Write-KitLog ('==== Job "{0}" finished ====' -f $job) 'PASS'
    $exitCode = 0
} catch {
    try {
        Write-KitLog ('Job "{0}" stopped: {1}' -f $job, $_.Exception.Message) 'ERROR'
        Write-KitLog ($_.InvocationInfo.PositionMessage) 'ERROR'
    } catch { }
    $exitCode = 1
} finally {
    if ((-not [bool]$WhatIfPreference) -and $requestId) {
        $result = New-Object -TypeName psobject -Property @{
            request_id  = $requestId
            job         = $job
            exit_code   = $exitCode
            finished_at = (Get-UtcStamp)
            data        = (New-Object -TypeName psobject -Property $script:JobData)
        }
        Set-Content -LiteralPath $resultFile -Value ($result | ConvertTo-Json -Depth 4) -Encoding UTF8
    }
}
exit $exitCode
