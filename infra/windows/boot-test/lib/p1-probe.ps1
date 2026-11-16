<#
p1-probe.ps1 - the action of the one-time P1 task \SlateOpsBootTest\P1Probe (runs as SYSTEM at startup).

It does nothing unless 30-p1.ps1 armed it (state.json p1_probe_armed = true). Then, with
nobody signed in:
  1. Measure: from Windows start (LastBootUpTime) it reads https://<name>.local/api/ready every
     5 s with curl.exe (the hosts entry maps the name to 127.0.0.1) and samples the memory of
     the WSL VM process (vmmemWSL or vmmem) into logs\p1-probe-vmmem.csv. It records the first
     answer 200 and how many people were signed in at that moment.
  2. F10 (only when p1_f10_armed): 2 minutes after ready, it installs the pinned WSL MSI of the
     selected version from the administrators-only cache, after the folder safety check and a
     SHA-256 check right before msiexec. Same version as installed = repair install
     (REINSTALL=ALL); older installed = upgrade. Then it measures the outage until
     /api/ready answers 200 again (the boot task must attach the distribution by itself).
  3. It writes logs\p1-probe-result.json and disarms itself.
It takes no input from Linux. The only values it reads are in state.json, which only
administrators and SYSTEM can write.
Log: C:\ProgramData\SlateOpsBootTest\logs\p1-probe.log
#>
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'common.ps1')

$curl = Join-Path $env:SystemRoot 'System32\curl.exe'
$result = [ordered]@{}

function Get-ReadyCode {
    param([string]$HostName)
    $out = & $curl -sk -o NUL -w '%{http_code}' --max-time 4 ('https://{0}/api/ready' -f $HostName) 2>$null
    return [string]$out
}

function Add-Sample {
    param([string]$Phase)
    $mib = Get-VmmemMiB
    # DateTimeOffset gives true Unix seconds (Get-Date -UFormat %s in PowerShell 5.1 adds the time zone).
    $line = '{0},{1},{2}' -f [DateTimeOffset]::UtcNow.ToUnixTimeSeconds(), $(if ($null -eq $mib) { '' } else { $mib }), $Phase
    Add-Content -LiteralPath $BootTest.P1.ProbeSamples -Value $line -Encoding ASCII
    return $mib
}

function Wait-Ready {
    # Polls until /api/ready answers 200 or the limit ends. Returns the time of the first 200,
    # and the first failed probe (outage start) when -TrackOutage is set.
    param([string]$HostName, [datetime]$Until, [string]$Phase, [switch]$TrackOutage)
    $firstFail = $null
    $peak = 0
    while ((Get-Date) -lt $Until) {
        $mib = Add-Sample -Phase $Phase
        if (($null -ne $mib) -and ($mib -gt $peak)) { $peak = $mib }
        $code = Get-ReadyCode -HostName $HostName
        if ($code -eq '200') {
            if ((-not $TrackOutage) -or $firstFail) { return @{ Ready = (Get-Date); FirstFail = $firstFail; PeakMiB = $peak } }
        } elseif ($TrackOutage -and (-not $firstFail)) {
            $firstFail = Get-Date
        }
        Start-Sleep -Seconds 5
    }
    return @{ Ready = $null; FirstFail = $firstFail; PeakMiB = $peak }
}

try {
    Initialize-BootTestLog -Name 'p1-probe' -Append
    $state = Read-BootTestState
    if (-not ($state.ContainsKey('p1_probe_armed') -and [bool]$state['p1_probe_armed'])) { exit 0 }
    $hostName = [string]$state['p1_host']
    if ($hostName -notmatch '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.local$') { throw 'state.json p1_host has an unexpected form.' }
    $boot = (Get-CimInstance -ClassName Win32_OperatingSystem).LastBootUpTime
    $started = Get-Date
    $result['windows_boot_utc'] = Get-UtcStamp -Time $boot
    $result['probe_started_utc'] = Get-UtcStamp -Time $started
    $result['probe_started_after_boot_seconds'] = [math]::Round(($started - $boot).TotalSeconds, 1)
    $result['wsl_version_before'] = [string](Get-WslVersion)
    Write-KitLog ('P1 probe armed: Windows started {0}; reading https://{1}/api/ready every 5 s.' -f $result['windows_boot_utc'], $hostName)
    if (-not (Test-Path -LiteralPath $BootTest.P1.ProbeSamples)) { Set-Content -LiteralPath $BootTest.P1.ProbeSamples -Value 'epoch,vmmem_working_set_mib,phase' -Encoding ASCII }

    # With F10 armed, F10 starts after a fixed delay even when this probe never sees ready (for
    # example when SYSTEM cannot reach the WSL loopback). Phase 2 then judges the reattach from the
    # Linux watcher's boot records. The owner waits 12 minutes, so F10 must start by 8 minutes.
    $f10Armed = ($state.ContainsKey('p1_f10_armed') -and [bool]$state['p1_f10_armed'])
    $readyLimit = $(if ($f10Armed) { $boot.AddMinutes(8) } else { $boot.AddMinutes(25) })
    $wait = Wait-Ready -HostName $hostName -Until $readyLimit -Phase 'startup'
    if ($wait.Ready) {
        $result['ready_utc'] = Get-UtcStamp -Time $wait.Ready
        $result['windows_start_to_ready_seconds'] = [math]::Round(($wait.Ready - $boot).TotalSeconds, 1)
        $result['signed_in_at_ready'] = Get-SignedIn
        Write-KitLog ('Ready {0} s after Windows started.' -f $result['windows_start_to_ready_seconds']) 'PASS'
        # Two more minutes of startup memory samples.
        $tailUntil = (Get-Date).AddMinutes(2)
        while ((Get-Date) -lt $tailUntil) { $mib = Add-Sample -Phase 'after-ready'; if (($null -ne $mib) -and ($mib -gt $wait.PeakMiB)) { $wait.PeakMiB = $mib }; Start-Sleep -Seconds 5 }
        $result['vmmem_startup_peak_mib'] = $wait.PeakMiB
        $result['vmmem_after_ready_mib'] = Get-VmmemMiB
    } else {
        $result['ready_utc'] = $null
        $result['note'] = ('This probe got no 200 until {0} UTC. The Linux-side watcher result decides.' -f (Get-UtcStamp -Time $readyLimit))
        Write-KitLog $result['note'] 'WARN'
    }

    # ---------------- F10 ----------------
    $f10 = [ordered]@{ status = 'not run' }
    if (-not $f10Armed) {
        $f10.reason = 'not armed (skipped in 30-p1.ps1)'
    } else {
        if (-not $wait.Ready) { $f10.note_start = 'started after the fixed delay; this probe never saw ready, so the Linux watcher decides the reattach' }
        $version = [string]$state['p1_f10_msi_version']
        $mode = [string]$state['p1_f10_mode']
        $arch = Get-Architecture
        if ((-not $BootTest.P1.WslMsi.ContainsKey($version)) -or (@('repair', 'upgrade') -notcontains $mode)) { throw 'state.json F10 values have an unexpected form.' }
        $msi = Join-Path $BootTest.Cache ('wsl.{0}.{1}.msi' -f $version, $arch.ToLowerInvariant())
        $problems = @(Get-BootTestTreeProblem)
        if ($problems.Count -gt 0) { throw ('{0} fails the safety check: {1}' -f $BootTest.Root, ($problems -join '; ')) }
        $hash = (Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $BootTest.P1.WslMsi[$version][$arch].Sha256) { throw ('SHA-256 mismatch for {0} right before msiexec.' -f $msi) }
        $f10.mode = $mode
        $f10.msi_version = $version
        $f10.signed_in_at_start = Get-SignedIn
        $msiLog = Join-Path $BootTest.Logs 'p1-f10-msi.log'
        $arguments = @('/i', ('"{0}"' -f $msi), '/qn', '/norestart', '/l*v', ('"{0}"' -f $msiLog))
        if ($mode -eq 'repair') { $arguments = @('/i', ('"{0}"' -f $msi), 'REINSTALL=ALL', 'REINSTALLMODE=vamus', '/qn', '/norestart', '/l*v', ('"{0}"' -f $msiLog)) }
        $msiStart = Get-Date
        $f10.msi_start_epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        $f10.msi_start_utc = Get-UtcStamp -Time $msiStart
        Write-KitLog ('F10: msiexec {0} of WSL {1} as SYSTEM (SHA-256 checked).' -f $mode, $version) 'STEP'
        $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList $arguments -PassThru
        $null = $process.Handle
        # Probe while msiexec runs too: the outage can start inside the install.
        $firstFail = $null
        while (-not $process.HasExited) {
            $null = Add-Sample -Phase 'f10'
            if (((Get-ReadyCode -HostName $hostName) -ne '200') -and (-not $firstFail)) { $firstFail = Get-Date }
            Start-Sleep -Seconds 5
        }
        $process.WaitForExit()
        $msiEnd = Get-Date
        $f10.msiexec_exit_code = $process.ExitCode
        $f10.msiexec_seconds = [math]::Round(($msiEnd - $msiStart).TotalSeconds, 1)
        $f10.wsl_version_after = [string](Get-WslVersion)
        # Then wait for 200 after the first failure (up to 15 minutes), or stop after 3 minutes
        # when no probe has failed: the MSI then did not restart the WSL VM.
        $readyAgain = $null
        while ((Get-Date) -lt $msiEnd.AddMinutes(15)) {
            $null = Add-Sample -Phase 'f10'
            $code = Get-ReadyCode -HostName $hostName
            if ($code -ne '200') { if (-not $firstFail) { $firstFail = Get-Date } }
            elseif ($firstFail) { $readyAgain = Get-Date; break }
            elseif ((Get-Date) -gt $msiEnd.AddMinutes(3)) { break }
            Start-Sleep -Seconds 5
        }
        if ($readyAgain) {
            $f10.ready_again_utc = Get-UtcStamp -Time $readyAgain
            $f10.ready_again_after_msi_end_seconds = [math]::Round(($readyAgain - $msiEnd).TotalSeconds, 1)
            $f10.outage_seconds = [math]::Round(($readyAgain - $firstFail).TotalSeconds, 1)
        } elseif (-not $firstFail) {
            $f10.outage_seconds = 0
            $f10.note = 'No probe failed during or 3 minutes after msiexec: the MSI did not restart the WSL VM.'
        } else {
            $f10.ready_again_utc = $null
            $f10.note = 'The service did not answer 200 again within 15 minutes after msiexec ended.'
        }
        $f10.start_task_state_after = [string](Get-ScheduledTask -TaskPath $BootTest.TaskPath -TaskName $BootTest.StartTaskName).State
        $f10.status = 'ran'
    }
    $result['f10'] = $f10
} catch {
    $result['error'] = $_.Exception.Message
    try { Write-KitLog ('P1 probe stopped: {0}' -f $_.Exception.Message) 'ERROR' } catch { $null = $_ }
} finally {
    try {
        $state = Read-BootTestState
        if ($state.ContainsKey('p1_probe_armed') -and [bool]$state['p1_probe_armed']) {
            # Result first, then disarm: 30-p1.ps1 reads the result once the probe is disarmed.
            $result['finished_utc'] = Get-UtcStamp
            Set-Content -LiteralPath $BootTest.P1.ProbeResult -Value (New-Object -TypeName psobject -Property $result | ConvertTo-Json -Depth 5) -Encoding UTF8
            $state['p1_probe_armed'] = $false
            $state['p1_f10_armed'] = $false
            Save-BootTestState -State $state
        }
    } catch { $null = $_ }
}
exit 0
