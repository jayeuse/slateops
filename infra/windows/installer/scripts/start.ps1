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

foreach ($name in @('Common', 'Checks', 'Exec')) { . (Join-Path $PSScriptRoot ('lib\{0}.ps1' -f $name)) }

$layout = New-SlateOpsLayout
$serviceSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$runId = New-RunId -Kind 'boot'
$logDir = Open-LogDirectory -Layout $layout -Kind 'start' -ServiceSid $serviceSid
if (-not $logDir) { exit 3 }
Start-RunLog -RunId $runId -Directory $logDir -NoConsole
$null = Invoke-LogRotation -Directory $logDir
$runDir = Join-Path $logDir $runId
[void][System.IO.Directory]::CreateDirectory($runDir)

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
        $process = Start-Process -FilePath $wslExe -ArgumentList @('-d', $SlateOps.DistroName, '-u', 'root', '--exec', $SlateOps.KeepAlivePath, 'infinity') `
            -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $runDir ('keepalive-{0}.out.txt' -f $attach)) `
            -RedirectStandardError (Join-Path $runDir ('keepalive-{0}.err.txt' -f $attach))
        $null = $process.Handle
        $statusInput = Get-StatusInput
        if ($statusInput) {
            $stdout = Join-Path $runDir ('status-{0}.json' -f $attach)
            $stderr = Join-Path $runDir ('status-{0}.err.txt' -f $attach)
            $writer = { param($stream) $stream.Write($statusInput, 0, $statusInput.Length) }
            $run = Invoke-ProcessWithInput -FilePath $wslExe -ArgumentList (Get-EngineArguments -Job 'status') -WriteInput $writer -StdoutPath $stdout -StderrPath $stderr
            $null = Limit-ErrorFile -Path $stderr
            $engine = Get-EngineCode -Path $stdout
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
