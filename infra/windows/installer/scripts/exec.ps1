<#
exec.ps1 - the action of the on-demand task \SlateOps\Exec (runs as slateops-svc; plan 3.1).

Input: C:\ProgramData\SlateOps\requests\request.json ({"request_id", "job", "run_id"}) and
requests\input.json (the job's standard input, at most 64 KiB). Only administrators can write
requests\. Output: svc-out\exec-result.json and svc-out\<request ID>.stdout.json; the
administrator side reads them as data. Log: logs\exec\<run ID>.log (plan 10.1).
It takes no parameters: nothing in the task's command line comes from a request.
Windows PowerShell 5.1, ASCII only.
#>
[CmdletBinding()]
param()

foreach ($name in @('Common', 'Checks', 'Exec')) { . (Join-Path $PSScriptRoot ('lib\{0}.ps1' -f $name)) }

$layout = New-SlateOpsLayout
$exitCode = 3
try {
    $serviceSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $runId = $null
    try {
        $peek = ConvertFrom-JsonUnlimited ([System.IO.File]::ReadAllText($layout.RequestFile, [System.Text.Encoding]::UTF8))
        if (($peek -is [System.Collections.IDictionary]) -and (Test-RunId (Get-DictValue $peek 'run_id'))) { $runId = [string](Get-DictValue $peek 'run_id') }
    } catch { $runId = $null }
    if (-not $runId) { $runId = New-RunId -Kind 'maintenance' }
    $logDir = Open-LogDirectory -Layout $layout -Kind 'exec' -ServiceSid $serviceSid
    if (-not $logDir) { throw 'The log folder fails the safety check.' }
    Start-RunLog -RunId $runId -Directory $logDir -Append -NoConsole
    $null = Invoke-LogRotation -Directory $logDir
    $result = Invoke-ExecRequest -Layout $layout
    $exitCode = [int]$result.exit_code
} catch {
    try { Write-RunLog 'exec' 'ERROR' $_.Exception.Message } catch { $null = $_ }
    $exitCode = 3
}
exit $exitCode
