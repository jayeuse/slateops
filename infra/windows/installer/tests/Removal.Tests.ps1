# Removal.Tests.ps1 - DEC-0041 (TASK-0097): setup is a complete installation or nothing. An earlier
# run that did not finish is removed at start (AC-W4); the removal never deletes kept data and
# turns WSL and Virtual Machine Platform off only when setup turned them on and no other
# distribution is registered (AC-W3, with the parent's WSL guard). Every reader and command is
# the test's own: no test lists the runner's distributions or changes a Windows feature.

function New-RemovalLayout {
    param([Parameter(Mandatory = $true)][string]$Name)
    $root = New-TestDirectory $Name
    foreach ($parent in @('ProgramData', 'Data')) { [void][System.IO.Directory]::CreateDirectory((Join-Path $root $parent)) }
    $layout = New-SlateOpsLayout -StateRoot (Join-Path $root 'ProgramData\SlateOps')
    $null = Initialize-ProtectedTree -Tree $layout.StateTree
    return $layout
}

Test-Case 'AC-W4 an earlier run that did not finish is removed at start; only a restart that setup asked for continues' {
    # Rows: stage ('' = no progress file), Windows records left, installed version, expected
    # "screen next cleanup".
    $rows = @(
        @('continue_later', $true, '', 'S01  cleanup'),
        @('install_started', $true, '', 'S01  cleanup'),
        @('check_restart', $true, '', 'S02  '),
        # R-1 (Security S97-3): a finished install is never removed at start, even when its program
        # record is gone (an uninstall that left parts behind).
        @('key_saved', $true, '', 'S01  '),
        @('', $true, '', 'S01  cleanup'),
        @('feature_restart', $true, '', 'S06 S07 '),
        @('install_finished', $true, '', 'S06 S14 '),
        @('', $false, '', 'S01  '),
        # Denials: an installed program is never removed at start.
        @('install_started', $true, '0.2.0', 'M01  '),
        @('key_saved', $true, '0.2.0', 'M01  '),
        @('', $true, '0.2.0', 'M01  '),
        @('install_finished', $true, '0.2.0', 'S06 S14 ')
    )
    foreach ($row in $rows) {
        $progress = $null
        if ($row[0]) { $progress = @{ stage = $row[0]; setup_version = '0.2.0' } }
        $entry = Get-SetupEntry -Progress $progress -Leftover:$row[1] -Installed $row[2] -SetupVersion '0.2.0'
        $cleanup = $(if ($entry['cleanup'] -eq $true) { 'cleanup' } else { '' })
        Assert-Equal $row[3] ('{0} {1} {2}' -f $entry.screen, $entry.next, $cleanup) ('{0}, records {1}, installed "{2}"' -f $row[0], $row[1], $row[2])
    }
}

Test-Case 'AC-W4 the records of an earlier run are the progress file, install.json or windows-changes.json, whatever stage they hold' {
    $layout = New-RemovalLayout 'ac-w4-records'
    Assert-Equal $false (Test-SetupLeftover -Layout $layout) 'an empty state folder'
    [System.IO.File]::WriteAllText($layout.ProgressFile, '{"schema_version":1,"stage":"stage_of_an_older_setup"}')
    Assert-Equal $true (Test-SetupLeftover -Layout $layout) 'a progress file with a stage that this setup does not know'
    Remove-Item -LiteralPath $layout.ProgressFile
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ vmp_enabled_by_setup = $true })
    Assert-Equal $true (Test-SetupLeftover -Layout $layout) 'the Windows changes of S05'
    Remove-Item -LiteralPath (Join-Path $layout.State 'windows-changes.json')
    Write-JsonFile -Path $layout.StateFile -Value ([ordered]@{ schema_version = 1; data_root = 'D:\SlateOps' })
    Assert-Equal $true (Test-SetupLeftover -Layout $layout) 'install.json'
}

Test-Case 'AC-W9 a restart that setup asked for continues and removes nothing; a run that stopped without one is removed' {
    # Rows: saved progress (with its marks), expected "screen next cleanup". prepared: S05 ran in
    # this run before the restart was asked (S11 "Restart now", the C04 firmware restart), so
    # WSL and Virtual Machine Platform stay and setup continues after S05.
    $rows = @(
        @(@{ stage = 'check_restart'; prepared = $true; setup_version = '0.2.0' }, 'S06 S07 ', 'restart asked at S11 after S05: continues, WSL kept'),
        @(@{ stage = 'check_restart'; setup_version = '0.2.0' }, 'S02  ', 'restart asked at S02 before S05: continues at S02'),
        @(@{ stage = 'feature_restart'; setup_version = '0.2.0' }, 'S06 S07 ', 'the S05 restart'),
        @(@{ stage = 'install_started' }, 'S01  cleanup', 'any run after Install started'),
        @($null, 'S01  cleanup', 'stopped with no asked restart (S05 records only)')
    )
    foreach ($row in $rows) {
        $entry = Get-SetupEntry -Progress $row[0] -Leftover -SetupVersion '0.2.0'
        $cleanup = $(if ($entry['cleanup'] -eq $true) { 'cleanup' } else { '' })
        Assert-Equal $row[1] ('{0} {1} {2}' -f $entry.screen, $entry.next, $cleanup) $row[2]
    }
    Assert-Equal $true ((Get-SetupEntry -Progress @{ stage = 'check_restart'; setup_version = '0.2.0' } -Leftover -SetupVersion '0.2.0')['welcome_back']) 'S02 says Welcome back'
    # The mark is saved as a true or false mark only.
    $layout = New-RemovalLayout 'ac-w9-mark'
    Save-SetupProgress -Layout $layout -Stage 'check_restart' -RunId 'install-20261118T090700Z-abc123' -Marks @{ prepared = $true }
    Assert-Equal $true ((Read-SetupProgress -Layout $layout)['prepared'])
}

Test-Case 'QA N4 a restart continues only when the same setup version asked for it; progress of another setup file is removed' {
    # DEC-0038: rows: saved progress, this setup's version, expected "screen next cleanup".
    $rows = @(
        @(@{ stage = 'feature_restart'; setup_version = '0.2.0' }, '0.2.0', 'S06 S07 ', 'same version'),
        @(@{ stage = 'feature_restart'; setup_version = '0.2.0-rc.24' }, '0.2.0', 'S01  cleanup', 'another setup file'),
        @(@{ stage = 'feature_restart' }, '0.2.0', 'S01  cleanup', 'a setup file that saved no version'),
        @(@{ stage = 'check_restart'; prepared = $true; setup_version = '0.2.0-rc.24' }, '0.2.0', 'S01  cleanup', 'a check restart of another setup file'),
        @(@{ stage = 'feature_restart'; setup_version = '0.2.0' }, '', 'S01  cleanup', 'this setup cannot read its own version')
    )
    foreach ($row in $rows) {
        $entry = Get-SetupEntry -Progress $row[0] -Leftover -SetupVersion $row[1]
        $cleanup = $(if ($entry['cleanup'] -eq $true) { 'cleanup' } else { '' })
        Assert-Equal $row[2] ('{0} {1} {2}' -f $entry.screen, $entry.next, $cleanup) $row[3]
    }
    $layout = New-RemovalLayout 'qa-n4-version'
    Save-SetupProgress -Layout $layout -Stage 'feature_restart' -RunId 'install-20261118T120000Z-abc123' -SetupVersion '0.2.0'
    Assert-Equal '0.2.0' ([string](Read-SetupProgress -Layout $layout)['setup_version']) 'the saved progress names its setup version'
}

Test-Case 'R-1 a program record that exists but cannot be read stops setup with Save report and removes nothing' {
    # Security S97-3: the uninstall entry is there, but its version.json is missing, unreadable or
    # of an unknown schema; whatever progress is saved, nothing is removed.
    foreach ($stage in @('', 'install_started', 'key_saved', 'install_finished', 'feature_restart')) {
        $progress = $null
        if ($stage) { $progress = @{ stage = $stage; setup_version = '0.2.0' } }
        $entry = Get-SetupEntry -Progress $progress -Leftover -ProgramUnreadable -SetupVersion '0.2.0'
        Assert-Equal 'S01 True False' ('{0} {1} {2}' -f $entry.screen, ($entry['program_unreadable'] -eq $true), ($entry['cleanup'] -eq $true)) $stage
    }
    $root = New-TestDirectory 'r-1-program'
    Assert-Equal 'none' (Get-InstalledProgramState -InstallLocation $null -KeyFound:$false).state 'no uninstall entry'
    Assert-Equal 'unreadable' (Get-InstalledProgramState -InstallLocation '' -KeyFound).state 'an entry with no install location'
    Assert-Equal 'unreadable' (Get-InstalledProgramState -InstallLocation $root -KeyFound).state 'no version.json'
    [System.IO.File]::WriteAllText((Join-Path $root 'version.json'), '{"schema_version":2,"version":"0.3.0"}')
    Assert-Equal 'unreadable' (Get-InstalledProgramState -InstallLocation $root -KeyFound).state 'an unknown schema'
    [System.IO.File]::WriteAllText((Join-Path $root 'version.json'), '{not json')
    Assert-Equal 'unreadable' (Get-InstalledProgramState -InstallLocation $root -KeyFound).state 'not JSON'
}

# The WSL guard (parent addition to AC-W3). Run records the commands instead of running them.
function New-FeatureRun {
    $calls = New-Object System.Collections.Generic.List[string]
    $run = { param([string]$File, [string[]]$Arguments, [int]$LimitSeconds) $calls.Add(('{0} {1}' -f (Split-Path -Leaf $File), ($Arguments -join ' '))); return 0 }.GetNewClosure()
    return @{ Calls = $calls; Run = $run }
}

Test-Case 'AC-W3 WSL that was on the PC before setup stays' {
    $layout = New-RemovalLayout 'ac-w3-wsl-before'
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ wsl_version_before_setup = '2.6.1.0' })
    $fake = New-FeatureRun
    $result = Remove-SetupFeatures -Layout $layout -ListDistros { @{ ok = $true; names = @() } } -Run $fake.Run
    Assert-Equal 'kept' $result.code
    Assert-Equal 0 $fake.Calls.Count 'nothing is uninstalled or turned off'
}

Test-Case 'AC-W3 WSL that setup installed stays while another distribution is registered' {
    $layout = New-RemovalLayout 'ac-w3-other-distro'
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ vmp_enabled_by_setup = $true; wsl_version_before_setup = 'none' })
    $fake = New-FeatureRun
    $result = Remove-SetupFeatures -Layout $layout -ListDistros { @{ ok = $true; names = @('SlateOps', 'Ubuntu-24.04') } } -Run $fake.Run
    Assert-Equal 'kept' $result.code
    Assert-Equal 'other_distribution' $result.values.reason
    Assert-Equal 0 $fake.Calls.Count 'the other distribution is not touched, and WSL stays'
}

Test-Case 'AC-W3 WSL and Virtual Machine Platform that setup turned on go when no other distribution is registered, with no restart' {
    $layout = New-RemovalLayout 'ac-w3-removed'
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ vmp_enabled_by_setup = $true; wsl_version_before_setup = 'none' })
    $fake = New-FeatureRun
    $result = Remove-SetupFeatures -Layout $layout -ListDistros { @{ ok = $true; names = @('SlateOps') } } -Run $fake.Run
    Assert-Equal 'removed' $result.code
    Assert-Equal @('wsl.exe --uninstall', 'dism.exe /Online /Disable-Feature /FeatureName:VirtualMachinePlatform /NoRestart /Quiet') @($fake.Calls)
    Assert-Equal $true $result.values.restart_needed 'Windows finishes at the next restart; setup does not restart'
}

Test-Case 'AC-W3 a distribution check that fails or is unclear keeps WSL and Virtual Machine Platform' {
    $layout = New-RemovalLayout 'ac-w3-check-failed'
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ vmp_enabled_by_setup = $true; wsl_version_before_setup = 'none' })
    foreach ($reader in @({ @{ ok = $false; names = @() } }, { throw 'registry_unreadable' })) {
        $fake = New-FeatureRun
        $result = Remove-SetupFeatures -Layout $layout -ListDistros $reader -Run $fake.Run
        Assert-Equal 'kept' $result.code
        Assert-Equal 'check_failed' $result.values.reason
        Assert-Equal 0 $fake.Calls.Count
    }
}

Test-Case 'AC-W3 the setup removal never deletes kept data: a kept reinstall returns the disk to kept\, a kept folder stays' {
    # A kept reinstall that failed after restore-kept: the disk is back in distro and kept.json
    # is still in kept\. The removal moves the disk back and leaves kept\ as it was.
    $layout = New-RemovalLayout 'ac-w3-kept'
    $dataRoot = Join-Path (Split-Path -Parent (Split-Path -Parent $layout.StateRoot)) 'Data\SlateOps'
    Write-JsonFile -Path $layout.StateFile -Value ([ordered]@{ schema_version = 1; data_root = $dataRoot; vhd_size_gb = 30 })
    foreach ($folder in @('distro', 'payload', 'kept')) { [void][System.IO.Directory]::CreateDirectory((Join-Path $dataRoot $folder)) }
    [System.IO.File]::WriteAllText((Join-Path $dataRoot 'kept\kept.json'), '{"version":"0.2.0"}')
    [System.IO.File]::WriteAllText((Join-Path $dataRoot 'distro\ext4.vhdx'), 'the kept data')
    [System.IO.File]::WriteAllText((Join-Path $dataRoot 'payload\slateops-engine-0.2.0.tar.gz'), 'x')
    $jobs = New-Object System.Collections.Generic.List[string]
    $exec = { param([string]$Job) $jobs.Add($Job); return @{ code = 'done'; exit_code = 0 } }.GetNewClosure()
    $result = Remove-SetupData -Layout $layout -ExecJob $exec
    Assert-Equal 'returned' $result.code (ConvertTo-JsonText $result)
    Assert-Equal 'the kept data' ([System.IO.File]::ReadAllText((Join-Path $dataRoot 'kept\ext4.vhdx'))) 'the disk is back in kept\'
    Assert-Equal '{"version":"0.2.0"}' ([System.IO.File]::ReadAllText((Join-Path $dataRoot 'kept\kept.json'))) 'kept.json is unchanged'
    Assert-Equal @('terminate-distro', 'unregister-distro') @($jobs)
    Assert-Equal $false (Test-Path -LiteralPath (Join-Path $dataRoot 'payload')) 'the parts of this run go'
    # The disk still in kept\ (restore-kept never ran): nothing in kept\ moves, the root stays.
    Remove-Item -LiteralPath (Join-Path $dataRoot 'distro') -Recurse -Force -ErrorAction SilentlyContinue
    $jobs.Clear()
    $again = Remove-SetupData -Layout $layout -ExecJob $exec
    Assert-Equal 'returned' $again.code (ConvertTo-JsonText $again)
    Assert-Equal 'the kept data' ([System.IO.File]::ReadAllText((Join-Path $dataRoot 'kept\ext4.vhdx')))
    Assert-Equal @('unregister-distro') @($jobs)
}

Test-Case 'R-5 any failure in the kept branch returns keep_failed and deletes nothing' {
    # Architect N-6, Security S97-8: an exception (a locked disk) or a failed unregister keeps
    # the state record, so the next start tries again; kept\ and distro\ stay.
    $layout = New-RemovalLayout 'r-5-kept'
    $dataRoot = Join-Path (Split-Path -Parent (Split-Path -Parent $layout.StateRoot)) 'Data\SlateOps'
    Write-JsonFile -Path $layout.StateFile -Value ([ordered]@{ schema_version = 1; data_root = $dataRoot; vhd_size_gb = 30 })
    foreach ($folder in @('distro', 'payload', 'kept')) { [void][System.IO.Directory]::CreateDirectory((Join-Path $dataRoot $folder)) }
    [System.IO.File]::WriteAllText((Join-Path $dataRoot 'kept\kept.json'), '{"version":"0.2.0"}')
    [System.IO.File]::WriteAllText((Join-Path $dataRoot 'kept\ext4.vhdx'), 'the kept data')
    $throws = Remove-SetupData -Layout $layout -ExecJob { param([string]$Job) throw 'exec_busy' }
    Assert-Equal 'keep_failed' $throws.code 'an exception'
    $refused = Remove-SetupData -Layout $layout -ExecJob { param([string]$Job) @{ code = 'failed'; exit_code = 1 } }
    Assert-Equal 'keep_failed' $refused.code 'unregister failed'
    Assert-Equal $true (Test-Path -LiteralPath (Join-Path $dataRoot 'distro')) 'distro stays while the distribution may still be registered'
    Assert-Equal 'the kept data' ([System.IO.File]::ReadAllText((Join-Path $dataRoot 'kept\ext4.vhdx')))
}

Test-Case 'R-7 the distribution check reads local and Microsoft Entra ID accounts' {
    # Security S97-9: S-1-12-1- is a Microsoft Entra ID user; its distributions count too.
    $rows = @(
        @('S-1-5-21-1004336348-1177238915-682003330-1001', $true), @('S-1-12-1-3570523188-1192226446-1520862853-1592452722', $true),
        @('S-1-5-18', $false), @('S-1-5-21-1004336348-1177238915-682003330-1001_Classes', $false), @('S-1-5-80-123', $false)
    )
    foreach ($row in $rows) { Assert-Equal $row[1] (Test-UserSid $row[0]) $row[0] }
}

Test-Case 'AC-W3 the setup removal has nothing to remove before the data folder step' {
    $layout = New-RemovalLayout 'ac-w3-no-data'
    $jobs = New-Object System.Collections.Generic.List[string]
    $result = Remove-SetupData -Layout $layout -ExecJob { param([string]$Job) $jobs.Add($Job); @{ code = 'done'; exit_code = 0 } }.GetNewClosure()
    Assert-Equal 'nothing' $result.code
    Assert-Equal 0 $jobs.Count
}

Test-Case 'AC-W1 S07 checks the chosen data folder on Next and writes nothing; the server work waits for Install' {
    $root = New-AdminOnlyFolder 'SlateOpsAcW1Data'
    try {
        $dataRoot = Join-Path $root 'SlateOps'
        Assert-Equal 'ready' (Test-DataFolderChoice -DataRoot $dataRoot).code 'a folder that does not exist yet'
        Assert-Equal $false (Test-Path -LiteralPath $dataRoot) 'the check creates nothing'
        [void][System.IO.Directory]::CreateDirectory($dataRoot)
        [System.IO.File]::WriteAllText((Join-Path $dataRoot 'notes.txt'), 'x')
        Assert-Equal 'not_empty' (Test-DataFolderChoice -DataRoot $dataRoot).code
        Remove-Item -LiteralPath (Join-Path $dataRoot 'notes.txt')
        [void][System.IO.Directory]::CreateDirectory((Join-Path $dataRoot 'kept'))
        Assert-Equal 'not_empty' (Test-DataFolderChoice -DataRoot $dataRoot).code 'kept data without the kept choice'
        Assert-Equal 'ready' (Test-DataFolderChoice -DataRoot $dataRoot -AllowKept).code 'kept data with "Use the kept data"'
        Assert-Equal 'path_invalid' (Test-DataFolderChoice -DataRoot 'D:\').code
    } finally { Remove-PathNoFollow -Path $root }
}
