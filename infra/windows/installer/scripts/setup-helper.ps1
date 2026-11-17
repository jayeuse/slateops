<#
setup-helper.ps1 - the hidden helper that the setup program starts for each Windows-side
action (wizard spec 5.2 "How the check runs", plan F4b). Setup runs elevated; Inno Setup makes
{tmp} administrator-only, and this script runs from {tmp}\scripts (or, for maintenance, from
C:\ProgramData\SlateOps\scripts).

  powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File setup-helper.ps1
      -Action <name> -RunId <run ID> -OutFile <result .json> [action options]

The action is one name from a fixed list. The result is one JSON object in -OutFile with a safe
code and a message key (W8 maps them to the spec's copy). Progress lines go to the run log
(plan 10.1). Paths: -OutFile and -InputFile must be inside the helper's own root folder, and
every other path is fixed or comes from the administrator-only state folder.
Windows PowerShell 5.1, ASCII only.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('state-check', 'check', 'recheck', 'facts', 'time-zone', 'fix-network-private', 'remove-kit',
        'save-progress', 'clear-resume', 'restart', 'prepare-pc', 'prepare-data', 'service', 'job', 'job-result',
        'start-boot', 'windows-steps')]
    [string]$Action,
    [Parameter(Mandatory = $true)][string]$RunId,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string]$DataRoot = '',
    [string]$SetupPath = '',
    [ValidateSet('', 'check_restart', 'feature_restart', 'continue_later', 'install_started', 'install_finished', 'key_saved')][string]$Stage = '',
    [string]$Job = '',
    [string]$InputFile = '',
    [string]$RequestId = '',
    [string]$PemFile = '',
    [switch]$Firmware,
    [switch]$Lid,
    [switch]$Cancel
)

# S91-6: modules load only from Windows PowerShell's own folder, never from a folder in the
# caller's module path.
$env:PSModulePath = Join-Path $PSHOME 'Modules'
foreach ($name in @('Common', 'Checks', 'Facts', 'Exec', 'Service', 'Windows')) { . (Join-Path $PSScriptRoot ('lib\{0}.ps1' -f $name)) }

$helperRoot = Split-Path -Parent $PSScriptRoot
$layout = New-SlateOpsLayout

function Assert-InsideRoot {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($helperRoot.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'path_outside_root' }
    return $full
}

function Write-HelperResult {
    # "code" and "message_key" come first in the file (P2-2; the setup program reads the first
    # "code").
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Result)
    $text = ConvertTo-HelperResultText -Result $Result -Action $Action -RunId $RunId
    $temp = $script:outPath + '.tmp'
    [System.IO.File]::WriteAllText($temp, $text, (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $script:outPath) { Remove-PathNoFollow -Path $script:outPath }
    [System.IO.File]::Move($temp, $script:outPath)
}

function Read-HelperVersion {
    return Read-SetupVersion -Path (Join-Path $PSScriptRoot 'version.json')
}

$exitCode = 0
try {
    if (-not (Test-RunId $RunId)) { throw 'run_id_invalid' }
    $script:outPath = Assert-InsideRoot $OutFile
    if (-not (Test-Administrator)) { throw 'not_administrator' }

    # Log: the state tree's setup folder when it exists and passes the quick check, else the
    # helper's own folder (before S07 creates the state tree, plan 10.1 item 4).
    # P2-3: the SID from the administrator-only record, also after a partial service step.
    $serviceSid = Get-RecordedServiceSid -Layout $layout
    $logDir = Open-LogDirectory -Layout $layout -Kind 'setup' -ServiceSid $serviceSid
    if (-not $logDir) {
        $logDir = Join-Path $helperRoot 'logs'
        if (-not (Test-Path -LiteralPath $logDir)) { [void][System.IO.Directory]::CreateDirectory($logDir) }
    }
    Start-RunLog -RunId $RunId -Directory $logDir -Append -NoConsole
    Write-RunLog ('helper.{0}' -f $Action) 'INFO' ('start (setup helper, {0})' -f $PSScriptRoot)

    $result = [ordered]@{}
    switch ($Action) {
        'state-check' {
            $step = Test-StateFolder -Layout $layout -ServiceSid $serviceSid
            if ($step.code -eq 'safe') { $null = Invoke-LogRotation -Directory (Join-Path $layout.Logs 'setup') }
            $result = $step
            if ($step.code -eq 'safe') { $result.values = @{ entry = (Get-SetupEntry -Progress (Read-SetupProgress -Layout $layout)) } }
        }
        { $_ -in @('check', 'recheck') } {
            $pinned = [version]'0.0.0.0'
            try { $pinned = (Read-HelperVersion).wsl_version } catch { Write-RunLog 'helper.check' 'WARN' 'version.json not readable; C26 compares with 0.0.0.0' }
            $facts = Get-PcCheckFacts
            $only = @()
            if ($Action -eq 'recheck') { $only = $SlateOpsCheck.RecheckIds }
            $items = @(Invoke-PcCheck -Facts $facts -PinnedWsl $pinned -Only $only)
            foreach ($item in $items) { Write-RunLog ('check.{0}' -f $item.id.ToLowerInvariant()) 'INFO' ('{0} {1}' -f $item.class, $item.code) }
            $verdict = Get-PcVerdict -Results $items
            Write-RunLog 'check.verdict' 'INFO' $verdict.verdict
            $result = @{ code = $verdict.verdict; message_key = $verdict.message_key; values = @{ verdict = $verdict; items = $items } }
        }
        'facts' {
            $setupVersion = ''
            try { $setupVersion = (Read-HelperVersion).version } catch { $setupVersion = '' }
            $drive = ''
            if ($DataRoot -and (Test-DataRootPath $DataRoot)) { $drive = $DataRoot.Substring(0, 2) }
            $facts = Get-EnvironmentFacts -SetupVersion $setupVersion -DataDrive $drive
            Write-RunLog 'facts' 'INFO' (Protect-LogText (ConvertTo-JsonText $facts))
            $result = @{ code = 'recorded'; message_key = 'facts.recorded'; values = $facts }
        }
        'time-zone' {
            $windowsId = (Get-TimeZone).Id
            $iana = ConvertTo-IanaTimeZone -WindowsId $windowsId
            Write-RunLog 'helper.time_zone' 'INFO' ('{0} -> {1}' -f $windowsId, $iana)
            if ($iana) { $result = New-StepResult -Code 'mapped' -MessageKey 'setup.time_zone.mapped' -Values @{ windows_id = $windowsId; iana = $iana } }
            else { $result = New-StepResult -Code 'unmapped' -MessageKey 'setup.time_zone.unmapped' -Values @{ windows_id = $windowsId } }
        }
        'fix-network-private' {
            $lan = Get-LanFact
            if (-not $lan) { $result = New-StepResult -Code 'no_network' -MessageKey 'check.c09.not_connected' }
            else {
                Write-RunLog 'check.c10.fix' 'INFO' ('network "{0}" was {1}' -f $lan.network_name, $lan.category)
                Set-NetConnectionProfile -InterfaceIndex $lan.interface_index -NetworkCategory Private
                $result = New-StepResult -Code 'fixed' -MessageKey 'check.c10.fixed'
            }
        }
        'remove-kit' { $result = Remove-KitLeftovers }
        'save-progress' {
            if (-not $Stage) { throw 'stage_missing' }
            $ready = Initialize-StateFolder -Layout $layout -ServiceSid $serviceSid
            if ($ready.code -ne 'ready') { $result = $ready; break }
            Save-SetupProgress -Layout $layout -Stage $Stage -RunId $RunId
            if (@('check_restart', 'feature_restart') -contains $Stage) { $result = Register-SetupResume -SetupPath $SetupPath }
            else { $result = New-StepResult -Code 'saved' -MessageKey 'setup.progress.saved' }
        }
        'clear-resume' {
            if ($Cancel -and (Test-Path -LiteralPath $layout.State)) { Assert-TreeWritable -Tree $layout.StateTree -Directory $layout.State -ServiceSid $serviceSid }
            $result = Clear-SetupResume -Layout $layout -Progress:$Cancel
        }
        'restart' { $result = Invoke-PcRestart -Firmware:$Firmware }
        'prepare-pc' {
            $version = Read-HelperVersion
            $ready = Initialize-StateFolder -Layout $layout -ServiceSid $serviceSid
            if ($ready.code -ne 'ready') { $result = $ready; break }
            $feature = Enable-VirtualMachinePlatform -Layout $layout
            $msi = Join-Path (Join-Path $helperRoot 'payload') $version.wsl_msi_name
            $wsl = Install-WslPackage -Layout $layout -MsiPath $msi -Sha256 $version.wsl_msi_sha256 -PinnedVersion $version.wsl_version
            $restart = [bool]$feature.values.restart_needed -or ($wsl.values.ContainsKey('restart_needed') -and [bool]$wsl.values.restart_needed)
            if (@('present', 'installed') -notcontains $wsl.code) { $result = $wsl }
            else { $result = New-StepResult -Code 'prepared' -MessageKey 'prepare.prepared' -Values @{ restart_needed = $restart; feature = $feature.code; wsl = $wsl.code } }
        }
        'prepare-data' {
            $version = Read-HelperVersion
            $ready = Initialize-StateFolder -Layout $layout -ServiceSid $serviceSid
            if ($ready.code -ne 'ready') { $result = $ready; break }
            $data = Initialize-DataFolder -Layout $layout -DataRoot $DataRoot -ServiceSid $serviceSid
            if ($data.code -ne 'ready') { $result = $data; break }
            $copy = Install-ScriptsCopy -Layout $layout -SourceDir $PSScriptRoot
            if ($copy.code -ne 'copied') { $result = $copy; break }
            $parts = @($version.linux_image_name) + @(Get-ReceivePartNames -Version $version.version)
            $copied = Copy-PayloadPart -Layout $layout -SourceDir (Join-Path $helperRoot 'payload') -Names $parts -ServiceSid $serviceSid
            if ($copied.code -ne 'copied') { $result = $copied; break }
            $result = New-StepResult -Code 'ready' -MessageKey 'setup.data.ready' -Values $data.values
        }
        'service' {
            $state = Read-InstallState -Layout $layout
            Set-LayoutDataRoot -Layout $layout -DataRoot $state.data_root
            $result = Install-ServiceAccountAndTasks -Layout $layout
        }
        'job' {
            $bytes = New-Object byte[] 0
            if ($InputFile) { $bytes = [System.IO.File]::ReadAllBytes((Assert-InsideRoot $InputFile)) }
            Assert-TreeWritable -Tree $layout.StateTree -Directory $layout.Requests -ServiceSid $serviceSid
            $id = Submit-ExecRequest -Layout $layout -Job $Job -RunId $RunId -InputBytes $bytes
            $result = New-StepResult -Code 'started' -MessageKey 'exec.started' -Values @{ request_id = $id }
        }
        'job-result' {
            $value = Get-ExecResult -Layout $layout -RequestId $RequestId
            if ($null -eq $value) {
                $info = Get-ScheduledTaskInfo -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.ExecTaskName
                $result = New-StepResult -Code 'waiting' -MessageKey 'exec.waiting' -Values @{ last_task_result = [long]$info.LastTaskResult }
            } else {
                $values = @{ exec = $value }
                if (((Get-DictValue $value 'job') -eq 'log-bundle') -and ((Get-DictValue $value 'exit_code') -eq 0)) {
                    $output = Read-EngineOutput -Layout $layout -Result $value
                    $values.bundle = Save-LogBundle -Output $output -DestinationPath (Join-Path $helperRoot ('linux-{0}.tar.gz' -f $RunId))
                }
                $result = New-StepResult -Code 'done' -MessageKey 'exec.done' -Values $values
            }
        }
        'start-boot' {
            Start-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.StartTaskName
            $result = New-StepResult -Code 'started' -MessageKey 'setup.boot.started'
        }
        'windows-steps' {
            $lan = Get-LanFact
            if (-not $lan) { $result = New-StepResult -Code 'no_network' -MessageKey 'check.c09.not_connected'; break }
            $cidr = ConvertTo-NetworkCidr -Address $lan.address -PrefixLength $lan.prefix_length
            Assert-TreeWritable -Tree $layout.StateTree -Directory $layout.State -ServiceSid $serviceSid
            # P3-9: the address is the DNS host name in lower case.
            $hostName = ([string](Get-CimInstance -ClassName Win32_ComputerSystem).DNSHostName).ToLowerInvariant()
            $steps = @()
            $steps += Set-FirewallRules -Layout $layout -Cidr $cidr
            $steps += Set-HostsEntry -Layout $layout -HostName ('{0}.local' -f $hostName)
            $pem = [System.IO.File]::ReadAllText((Assert-InsideRoot $PemFile), [System.Text.Encoding]::ASCII)
            $ca = Install-TrustedCa -Layout $layout -Pem $pem
            $steps += $ca
            $steps += Set-KeepAwake -Layout $layout -Lid:$Lid
            $failed = @($steps | Where-Object { @('added', 'set') -notcontains $_.code })
            if ($failed.Count -gt 0) { $result = $failed[0] }
            else { $result = New-StepResult -Code 'done' -MessageKey 'install.windows.done' -Values @{ security_code = $ca.values.security_code } }
        }
    }
    Write-RunLog ('helper.{0}' -f $Action) 'INFO' ('result {0}' -f $result.code)
    Write-HelperResult -Result $result
} catch {
    $code = $_.Exception.Message
    if ($code -notmatch '^[a-z0-9_]{1,64}$') { $code = 'helper_failed' }
    try { Write-RunLog ('helper.{0}' -f $Action) 'ERROR' ('{0} {1}' -f $_.Exception.Message, $_.InvocationInfo.PositionMessage) } catch { $null = $_ }
    try { if ($script:outPath) { Write-HelperResult -Result @{ code = $code; message_key = ('helper.{0}' -f $code) } } } catch { $null = $_ }
    $exitCode = 1
}
exit $exitCode
