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
Output: svc-out\svc-exec-<job>.log and svc-out\svc-exec-result.json (request ID and exit code).
svc-out is the service account's own folder; the administrator side only reads it.
The admin side (Invoke-SvcJob in common.ps1) waits for that result.

-WhatIf: log the steps of the requested job and change nothing.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()

. (Join-Path $PSScriptRoot 'common.ps1')

$jobNames = @('prepare', 'status', 'unregister')
$requestId = ''
$job = ''
$exitCode = 1

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

    $linuxKit = Get-LinuxPath -WindowsPath (Join-Path $BootTest.Kit 'linux')
    $lib = $BootTest.LinuxLib
    # Copy the Linux files into the distribution and strip Windows line ends (CR) from them.
    # The command holds no double quotes, so Windows PowerShell 5.1 passes it to wsl.exe intact.
    $copy = ('rm -rf {0} && mkdir -p {0} && cp -R {1}/. {0}/ && find {0} -type f -exec sed -i ''s/\r$//'' {{}} + && find {0} -type f -name ''*.sh'' -exec chmod 0755 {{}} + && chmod 0755 {0}/payload/www/cgi-bin/index.cgi' -f $lib, $linuxKit)
    Invoke-Step ('Copy the Linux kit files to {0} in the distribution' -f $lib) {
        Invoke-Wsl -ArgumentList @('-d', $BootTest.DistroName, '-u', 'root', '--exec', '/bin/sh', '-c', $copy) | Out-Null
    }
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
    Initialize-BootTestLog -Name ('svc-exec-{0}' -f $job) -Append -DryRun:$dryRun -Directory $BootTest.SvcOut
    # Delete this account's own old result, so the administrator side never needs to write here.
    if ((-not $dryRun) -and (Test-Path -LiteralPath $BootTest.ResultFile)) { Remove-Item -LiteralPath $BootTest.ResultFile -Force }
    Write-KitLog ('==== Job "{0}" started (request {1}) as {2} ====' -f $job, $requestId, $env:USERNAME)
    switch ($job) {
        'prepare'    { Invoke-PrepareJob }
        'status'     { Invoke-StatusJob }
        'unregister' { Invoke-UnregisterJob }
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
        }
        Set-Content -LiteralPath $BootTest.ResultFile -Value ($result | ConvertTo-Json) -Encoding ASCII
    }
}
exit $exitCode
