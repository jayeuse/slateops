<#
start.ps1 - the action of the boot task \SlateOps\Start (runs as slateops-svc; plan 3.1, W7-6).

The kit's lib/start-distro.ps1 with the product's names. At Windows startup, with nobody signed
in, Task Scheduler runs this script. It keeps one process attached to the distribution
(/bin/sleep infinity, the final process of the kit's keepalive.sh), so WSL does not stop the
distribution; systemd then starts Docker and the stack. After each attach it sends the
Windows-part version and the installed WSL version to the engine's status job on standard input
(plan 3.2 rule 2, 7.4 rule 4), and logs only the safe code. If wsl.exe ends (a WSL update,
wsl --shutdown), it logs the exit code, waits 30 s and attaches again. It never ends by itself;
the task has no time limit. Log: logs\start\<boot run ID>.log (plan 10.1).
Windows PowerShell 5.1, ASCII only.
#>
[CmdletBinding()]
param()

# S91-6: modules load only from Windows PowerShell's own folder.
$env:PSModulePath = Join-Path $PSHOME 'Modules'
foreach ($name in @('Common', 'Checks', 'Exec', 'Mdns')) { . (Join-Path $PSScriptRoot ('lib\{0}.ps1' -f $name)) }

$layout = New-SlateOpsLayout
# Owner request 2026-11-25: with Start with Windows off, nothing starts until the settings
# program's Start. The task runs this every minute, so it ends before it writes a log.
if (-not (Test-StartAllowed -Layout $layout)) { exit 0 }
$serviceSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$runId = New-RunId -Kind 'boot'
$logDir = Open-LogDirectory -Layout $layout -Kind 'start' -ServiceSid $serviceSid
if (-not $logDir) { exit 3 }
Start-RunLog -RunId $runId -Directory $logDir -NoConsole
$null = Invoke-LogRotation -Directory $logDir
$runDir = Join-Path $logDir $runId
[void][System.IO.Directory]::CreateDirectory($runDir)

# DEC-0039: our own mDNS responder answers for <label>.local on a thread of this process (the
# program that the inbound UDP 5353 rule names); it ends with this process.
$label = Get-InstallAddressLabel -Layout $layout
$script:MdnsWorker = $null
if ($label) {
    try { $script:MdnsWorker = Start-MdnsResponderThread -Label $label -RunId $runId -LogDir $logDir -LibDir (Join-Path $PSScriptRoot 'lib') }
    catch { Write-RunLog 'boot.mdns' 'ERROR' ('mDNS responder not started: {0}' -f $_.Exception.Message) }
} else { Write-RunLog 'boot.mdns' 'WARN' 'no address label recorded; this PC answers no mDNS query for Slate Operations' }

function Get-StatusInput {
    # {"run_id", "windows_part_version", "wsl_version"} (engine status.py KEYS), or $null when
    # either version cannot be read.
    $windowsPart = $null
    try { $windowsPart = (Read-SetupVersion -Path (Join-Path $layout.Scripts 'version.json')).version } catch { $windowsPart = $null }
    $wsl = Get-WslPackageVersion
    if ((-not $windowsPart) -or (-not $wsl)) { return $null }
    $text = ConvertTo-JsonText ([ordered]@{ run_id = $runId; windows_part_version = $windowsPart; wsl_version = $wsl.ToString() })
    return [System.Text.Encoding]::UTF8.GetBytes($text)
}

$wslExe = Get-WslExe
$attach = 0
while ($true) {
    $attach++
    $exitCode = $null
    try {
        Write-RunLog 'boot.attach' 'INFO' ('attach {0}: > wsl.exe -d {1} -u root --exec {2} infinity' -f $attach, $SlateOps.DistroName, $SlateOps.KeepAlivePath)
        # -PassThru and WaitForExit() wait for wsl.exe only; Start-Process -Wait would wait for
        # every child too. Reading Handle first keeps ExitCode available (kit).
        # P3-4: fixed file names, overwritten at each attach, so the run folder does not grow
        # while the task runs for months.
        $process = Start-Process -FilePath $wslExe -ArgumentList @('-d', $SlateOps.DistroName, '-u', 'root', '--exec', $SlateOps.KeepAlivePath, 'infinity') `
            -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $runDir 'keepalive.out.txt') `
            -RedirectStandardError (Join-Path $runDir 'keepalive.err.txt')
        $null = $process.Handle
        $statusInput = Get-StatusInput
        if ($statusInput) {
            $stdout = Join-Path $runDir 'status.json'
            $stderr = Join-Path $runDir 'status.err.txt'
            foreach ($path in @($stdout, $stderr)) { if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path } }
            $writer = { param($sink) Write-InputBytes -Sink $sink -Buffer $statusInput }
            $run = Invoke-ProcessWithInput -FilePath $wslExe -ArgumentList (Get-EngineArguments -Job 'status') -WriteInput $writer -StdoutPath $stdout -StderrPath $stderr
            $null = Limit-ErrorFile -Path $stderr
            # S91-8: the cap is checked again before the file is read.
            if (($run.stdout_total -gt $SlateOpsExec.StdoutCap) -or ((Get-Item -LiteralPath $stdout -Force).Length -gt $SlateOpsExec.StdoutCap)) { $engine = @{ code = 'output_too_large' } }
            else { $engine = Get-EngineCode -Path $stdout }
            # AC-W6: the status output names the administrator's address; only the code stays.
            if (Test-Path -LiteralPath $stdout) { Remove-PathNoFollow -Path $stdout }
            Write-RunLog 'boot.status' 'INFO' ('status: exit code {0}, code {1}, {2} ms' -f $run.exit_code, $engine.code, $run.duration_ms)
        } else {
            Write-RunLog 'boot.status' 'WARN' 'status skipped: the Windows-part or the WSL version cannot be read'
        }
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    } catch {
        Write-RunLog 'boot.attach' 'ERROR' ('attach {0}: {1}' -f $attach, $_.Exception.Message)
    }
    Write-RunLog 'boot.attach' 'WARN' ('attach {0}: wsl.exe ended (exit code {1}); attaching again in 30 s' -f $attach, $exitCode)
    Start-Sleep -Seconds 30
}
