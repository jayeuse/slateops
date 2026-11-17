# Update.Tests.ps1 - the W13b criteria of the setup program's update path that a Windows runner
# can prove (TASK-0095 part 2): the WSL step of the update path (W13b-5, plan 7.4, 10.3 F10), the
# safe read of the engine's update result (P2-3) and the SemVer order with -rc.N (W13b-10). The
# engine status, msiexec and the WSL version are the test's own stand-ins: no test starts WSL or
# installs a package.

function New-UpdateLayout {
    param([Parameter(Mandatory = $true)][string]$Name)
    $root = New-TestDirectory $Name
    foreach ($parent in @('ProgramData', 'Data')) { [void][System.IO.Directory]::CreateDirectory((Join-Path $root $parent)) }
    $layout = New-SlateOpsLayout -StateRoot (Join-Path $root 'ProgramData\SlateOps') -DataRoot (Join-Path $root 'Data\SlateOps')
    $null = Initialize-ProtectedTree -Tree $layout.StateTree
    return $layout
}

Test-Case 'W13b-5 the update path installs an older WSL only when the engine is idle, after the SHA-256 check, and gives F10 when the engine does not answer again' {
    $layout = New-UpdateLayout 'w13b-5'
    $msi = Join-Path (New-TestDirectory 'w13b-5-payload') 'wsl.2.6.1.0.x64.msi'
    [System.IO.File]::WriteAllBytes($msi, [byte[]](1, 2, 3, 4))
    $version = @{ version = '0.2.1'; wsl_version = [version]'2.6.1.0'; wsl_msi_sha256 = (Get-FileSha256 -Path $msi) }
    $logDir = New-TestDirectory 'w13b-5-log'
    Start-RunLog -RunId 'update-20261117T120000Z-w13b05' -Directory $logDir -NoConsole
    # Stand-ins: the installed WSL, the engine status answers in order (the last one repeats),
    # and msiexec.
    function Get-WslPackageVersion { return $script:W13bWsl }
    function Get-EngineStatus {
        param([hashtable]$Layout, [string]$RunId, [string]$WindowsPartVersion = '0.0.0')
        $script:W13bCalls++
        $answer = $script:W13bAnswers[[math]::Min($script:W13bCalls, $script:W13bAnswers.Count) - 1]
        if ($answer -eq 'unreachable') { return New-StepResult -Code 'unreachable' -MessageKey 'maintenance.status.unreachable' }
        return New-StepResult -Code 'ok' -MessageKey 'maintenance.status.ok' -Values @{ engine_idle = ($answer -eq 'idle') }
    }
    function Start-Process {
        param([string]$FilePath, [object[]]$ArgumentList, [switch]$Wait, [switch]$PassThru)
        $script:W13bMsi++
        return [pscustomobject]@{ ExitCode = 0 }
    }
    $run = {
        param([string[]]$Answers, [System.Collections.IDictionary]$Pinned = $version)
        $script:W13bAnswers = $Answers; $script:W13bCalls = 0; $script:W13bMsi = 0
        return Invoke-UpdateWsl -Layout $layout -RunId 'update-20261117T120000Z-w13b05' -Version $Pinned -MsiPath $msi -BackSeconds 1 -PollSeconds 0
    }
    $script:W13bWsl = [version]'2.5.10.0'
    Assert-Equal 'engine_busy' (& $run @('busy')).code 'a busy engine: no install'
    Assert-Equal 0 $script:W13bMsi 'no msiexec while the engine is busy'
    Assert-Equal 'engine_unreachable' (& $run @('unreachable')).code 'no status: no install'
    Assert-Equal 0 $script:W13bMsi 'no msiexec without a status'
    $wrong = @{ version = '0.2.1'; wsl_version = [version]'2.6.1.0'; wsl_msi_sha256 = ('0' * 64) }
    Assert-Equal 'hash_mismatch' (& $run @('idle') $wrong).code
    Assert-Equal 0 $script:W13bMsi 'no msiexec after a failed SHA-256 check'
    Assert-Equal 'wsl_not_back' (& $run @('idle', 'unreachable')).code 'F10: no status in the time after the install'
    Assert-Equal 1 $script:W13bMsi
    Assert-Equal 'wsl_updated' (& $run @('idle', 'unreachable', 'busy')).code 'any status answer counts'
    Assert-Equal 1 $script:W13bMsi
    $script:W13bWsl = [version]'2.7.0.0'
    Assert-Equal 'present' (& $run @('busy')).code 'a newer WSL is kept'
    Assert-Equal 0 $script:W13bCalls 'no status call when nothing is installed'
    Assert-Equal 0 $script:W13bMsi
    $log = [System.IO.File]::ReadAllText((Join-Path $logDir 'update-20261117T120000Z-w13b05.log'))
    Assert-True ($log -match 'WSL 2\.7\.0\.0 is installed') $log
    Assert-True ($log -match 'F10') $log
}

Test-Case 'W13b-5 the engine status gives engine_idle only for a JSON true' {
    function Get-WslPackageVersion { return [version]'2.6.1.0' }
    function Invoke-ExecJobAndWait {
        param([hashtable]$Layout, [string]$Job, [string]$RunId, [string]$InputText = '', [int]$TimeoutSeconds = 600)
        return @{ code = 'ok'; exit_code = 0; job = $Job }
    }
    function Read-EngineOutput { param([hashtable]$Layout, [System.Collections.IDictionary]$Result) return $script:W13bOutput }
    $layout = New-UpdateLayout 'w13b-5-idle'
    foreach ($case in @(@{ value = $true; idle = $true }, @{ value = 'true'; idle = $false }, @{ value = 1; idle = $false }, @{ value = $false; idle = $false })) {
        $script:W13bOutput = @{ code = 'ok'; state = 'installed'; engine_idle = $case.value }
        $status = Get-EngineStatus -Layout $layout -RunId 'update-20261117T120000Z-w13b06'
        Assert-Equal $case.idle $status.values['engine_idle'] ('engine_idle {0}' -f $case.value)
    }
}

Test-Case 'W13b P2-3 the update result gives only a known state and a whole number of GB to the setup program' {
    $layout = New-UpdateLayout 'w13b-p2-3'
    [void][System.IO.Directory]::CreateDirectory($layout.SvcOut)
    $read = {
        param([string]$Json)
        $id = [guid]::NewGuid().ToString()
        $path = Join-Path $layout.SvcOut ('{0}.stdout.json' -f $id)
        [System.IO.File]::WriteAllText($path, $Json, (New-Object System.Text.UTF8Encoding($false)))
        $result = @{ job = 'update'; exit_code = 3; stdout_file = ('{0}.stdout.json' -f $id); stdout_bytes = (Get-Item -LiteralPath $path).Length; stdout_sha256 = (Get-FileSha256 -Path $path) }
        return Get-UpdateOutcome -Layout $layout -Result $result
    }
    $rolled = & $read '{"code":"migration_failed","message_key":"update.migration_failed","update":"rolled_back"}'
    Assert-Equal 'rolled_back 0' ('{0} {1}' -f $rolled.update_state, $rolled.needs_gb)
    $space = & $read '{"code":"insufficient_space","message_key":"update.insufficient_space","needs_gb":12,"update":"failed"}'
    Assert-Equal 'failed 12' ('{0} {1}' -f $space.update_state, $space.needs_gb)
    $odd = & $read '{"code":"x","update":"rolled_back; del","needs_gb":"12"}'
    Assert-Equal ' 0' ('{0} {1}' -f $odd.update_state, $odd.needs_gb) 'an unknown state and a text number are dropped'
    $none = Get-UpdateOutcome -Layout $layout -Result @{ job = 'update'; exit_code = 2; stdout_file = '' }
    Assert-Equal ' 0' ('{0} {1}' -f $none.update_state, $none.needs_gb) 'no output file: nothing to show'
}

Test-Case 'W13b-10 the setup program orders -rc.N by number, so rc.10 updates rc.9' {
    Assert-Equal -1 (Compare-ReleaseVersion -Left '0.1.0-rc.9' -Right '0.1.0-rc.10')
    Assert-Equal 'M05' (Get-SetupEntry -Progress $null -Installed '0.1.0-rc.9' -SetupVersion '0.1.0-rc.10').screen
    Assert-Equal 'M01' (Get-SetupEntry -Progress $null -Installed '0.1.0-rc.10' -SetupVersion '0.1.0-rc.9').screen
}

Test-Case 'W13b after an update only the receive parts of other versions leave the payload folder; a link in the tree leaves everything in place' {
    # Parent decision (DEC-0036, TASK-0095): the fixed part names of other versions go; the parts
    # of this version, the shared manifest names, the Linux image and other files stay.
    $outside = New-TestDirectory 'w13b-payload-outside'
    [System.IO.File]::WriteAllText((Join-Path $outside 'keep.txt'), 'outside')
    $root = New-AdminOnlyFolder 'SlateOpsW13bPayload'
    try {
        $layout = New-SlateOpsLayout -StateRoot (Join-Path $root 'ProgramData\SlateOps') -DataRoot (Join-Path $root 'SlateOps')
        $null = Initialize-ProtectedTree -Tree $layout.DataTree
        [void][System.IO.Directory]::CreateDirectory($layout.Payload)
        $names = @('release-manifest.json', 'release-manifest.json.sigstore.json',
            'slateops-engine-0.2.1.tar.gz', 'slateops-server-0.2.1-amd64.oci.tar', 'slateops-caddy-0.2.1-amd64.oci.tar',
            'slateops-engine-0.2.0.tar.gz', 'slateops-server-0.2.0-amd64.oci.tar', 'slateops-caddy-0.2.1-rc.3-amd64.oci.tar',
            'slateops-linux-0.2.0-amd64.tar.gz', 'notes.txt')
        foreach ($name in $names) { [System.IO.File]::WriteAllText((Join-Path $layout.Payload $name), 'part') }
        # Preconditions: the test folders pass the same checks as Copy-PayloadPart.
        $parentProblems = @(Get-FolderParentProblem -Path $layout.DataRoot)
        Assert-Equal 0 $parentProblems.Count ('parent: ' + ($parentProblems -join '; '))
        $treeProblems = @(Get-TreeProblem -Tree $layout.DataTree -ServiceSid '')
        Assert-Equal 0 $treeProblems.Count ('tree: ' + ($treeProblems -join '; '))
        $result = Remove-OldPayloadParts -Layout $layout -Version '0.2.1'
        Assert-Equal 'removed 4' ('{0} {1}' -f $result.code, $result.values.count)
        $left = @(Get-ChildItem -LiteralPath $layout.Payload -Force | ForEach-Object { $_.Name } | Sort-Object)
        Assert-Equal @('notes.txt', 'release-manifest.json', 'release-manifest.json.sigstore.json', 'slateops-caddy-0.2.1-amd64.oci.tar',
            'slateops-engine-0.2.1.tar.gz', 'slateops-linux-0.2.0-amd64.tar.gz', 'slateops-server-0.2.1-amd64.oci.tar') $left
        Assert-Equal $true (Test-Path -LiteralPath (Join-Path $outside 'keep.txt')) 'the folder behind the link stays'
        $again = Remove-OldPayloadParts -Layout $layout -Version '0.2.1'
        Assert-Equal 'none 0' ('{0} {1}' -f $again.code, $again.values.count) 'a second run finds nothing'
        # A link inside the protected data tree fails the tree check, as in Copy-PayloadPart: the
        # removal changes nothing and never follows the link.
        [System.IO.File]::WriteAllText((Join-Path $layout.Payload 'slateops-engine-0.2.0.tar.gz'), 'part')
        $null = New-Item -ItemType SymbolicLink -Path (Join-Path $layout.Payload 'slateops-engine-0.1.0.tar.gz') -Target $outside
        $refused = Remove-OldPayloadParts -Layout $layout -Version '0.2.1'
        Assert-Equal 'data_folder_parent_unsafe' $refused.code
        Assert-Equal $true (Test-Path -LiteralPath (Join-Path $layout.Payload 'slateops-engine-0.2.0.tar.gz')) 'nothing is removed while the tree holds a link'
        Assert-Equal $true (Test-Path -LiteralPath (Join-Path $outside 'keep.txt')) 'the folder behind the link stays'
        Remove-PathNoFollow -Path (Join-Path $layout.Payload 'slateops-engine-0.1.0.tar.gz')
    } finally { Remove-PathNoFollow -Path $root }
}
