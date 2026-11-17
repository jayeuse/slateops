# Folders.Tests.ps1 - AC-3: the state and data trees get their access lists in the creating
# call, and the kit's safety check refuses a non-administrator owner, extra access entries and
# reparse points (plan W7-5, spec 4.1, W80-5).

$script:ServiceSid = New-TestUser 'slateops-w7svc'
$script:OtherSid = New-TestUser 'slateops-w7usr'

function New-TestStateLayout {
    param([Parameter(Mandatory = $true)][string]$Name)
    $parent = New-TestDirectory $Name
    return New-SlateOpsLayout -StateRoot (Join-Path $parent 'SlateOps') -DataRoot (Join-Path $parent 'Data')
}

function Get-ExplicitAllowSids {
    param([Parameter(Mandatory = $true)][string]$Path)
    $acl = Get-Acl -LiteralPath $Path
    return Get-OrdinalSorted @($acl.GetAccessRules($true, $false, [System.Security.Principal.SecurityIdentifier]) | Where-Object { $_.AccessControlType -eq 'Allow' } |
            ForEach-Object { $_.IdentityReference.Value } | Select-Object -Unique)
}

Test-Case 'AC-3 a new state tree is protected, holds every entry, and passes the check' {
    $layout = New-TestStateLayout 'tree-new'
    $problems = @(Initialize-ProtectedTree -Tree $layout.StateTree)
    Assert-Equal 0 $problems.Count ($problems -join '; ')
    Assert-Equal $true (Get-Acl -LiteralPath $layout.StateRoot).AreAccessRulesProtected
    Assert-Equal @('S-1-5-18', 'S-1-5-32-544') (Get-ExplicitAllowSids -Path $layout.StateRoot)
    foreach ($entry in @('scripts', 'state', 'requests', 'svc-out', 'logs\setup', 'logs\start', 'logs\exec')) {
        Assert-True (Test-Path -LiteralPath (Join-Path $layout.StateRoot $entry)) $entry
    }
}

Test-Case 'AC-3 the service account reads scripts, state and requests, and writes only svc-out, logs\start and logs\exec' {
    $layout = New-TestStateLayout 'tree-service'
    $problems = @(Initialize-ProtectedTree -Tree $layout.StateTree -ServiceSid $script:ServiceSid)
    Assert-Equal 0 $problems.Count ($problems -join '; ')
    $sidType = [System.Security.Principal.SecurityIdentifier]
    $expected = [ordered]@{ 'scripts' = 'ReadAndExecute, Synchronize'; 'requests' = 'ReadAndExecute, Synchronize'; 'svc-out' = 'Modify, Synchronize'; 'logs\exec' = 'Modify, Synchronize'; 'logs\setup' = '' }
    foreach ($entry in $expected.Keys) {
        $rules = @((Get-Acl -LiteralPath (Join-Path $layout.StateRoot $entry)).GetAccessRules($true, $true, $sidType) | Where-Object { $_.IdentityReference.Value -eq $script:ServiceSid })
        $rights = (Get-OrdinalSorted @($rules | ForEach-Object { [string]$_.FileSystemRights } | Select-Object -Unique)) -join ';'
        Assert-Equal $expected[$entry] $rights $entry
    }
}

Test-Case 'AC-3 a state folder that a non-administrator owns stops setup and gets no entries' {
    $layout = New-TestStateLayout 'tree-owner'
    [void][System.IO.Directory]::CreateDirectory($layout.StateRoot, (Get-ProtectedDirectorySecurity))
    $null = & icacls.exe $layout.StateRoot /setowner ('*{0}' -f $script:OtherSid) 2>&1
    Assert-Equal 0 $LASTEXITCODE 'icacls /setowner'
    Assert-Equal 'unsafe_owner' (Test-StateFolder -Layout $layout).code
    $problems = @(Initialize-ProtectedTree -Tree $layout.StateTree)
    Assert-True ($problems -contains ('root_owner:{0}' -f $script:OtherSid)) ($problems -join '; ')
    Assert-Equal $false (Test-Path -LiteralPath $layout.Scripts)
}

Test-Case 'AC-3 a folder that inherits from its parent, or allows another user, fails the check' {
    $layout = New-TestStateLayout 'tree-inherit'
    New-Item -ItemType Directory -Path $layout.StateRoot | Out-Null
    $problems = @(Get-TreeProblem -Tree $layout.StateTree)
    Assert-True ($problems -contains 'root_inherits') ($problems -join '; ')

    $other = New-TestStateLayout 'tree-extra-access'
    $null = Initialize-ProtectedTree -Tree $other.StateTree
    $null = & icacls.exe $other.Scripts /grant ('*{0}:(OI)(CI)M' -f $script:OtherSid) 2>&1
    $problems = @(Get-TreeProblem -Tree $other.StateTree)
    Assert-True ($problems -contains ('access:{0}:{1}' -f $other.Scripts, $script:OtherSid)) ($problems -join '; ')
}

Test-Case 'AC-3 the service account may not write a read entry' {
    $layout = New-TestStateLayout 'tree-svc-write'
    $null = Initialize-ProtectedTree -Tree $layout.StateTree -ServiceSid $script:ServiceSid
    $null = & icacls.exe $layout.Requests /grant ('*{0}:(OI)(CI)M' -f $script:ServiceSid) 2>&1
    $problems = @(Get-TreeProblem -Tree $layout.StateTree -ServiceSid $script:ServiceSid)
    Assert-True ($problems -contains ('access:{0}:{1}' -f $layout.Requests, $script:ServiceSid)) ($problems -join '; ')
}

Test-Case 'AC-3 a junction inside the tree fails the check, and a delete does not follow it' {
    $layout = New-TestStateLayout 'tree-junction'
    $null = Initialize-ProtectedTree -Tree $layout.StateTree
    $target = New-TestDirectory 'junction-target'
    [System.IO.File]::WriteAllText((Join-Path $target 'keep.txt'), 'keep')
    $link = Join-Path $layout.Scripts 'lib'
    $null = & cmd.exe /c mklink /J $link $target 2>&1
    $problems = @(Get-TreeProblem -Tree $layout.StateTree)
    Assert-True ($problems -contains ('reparse_point:{0}' -f $link)) ($problems -join '; ')
    Remove-PathNoFollow -Path $layout.Scripts
    Assert-Equal $true (Test-Path -LiteralPath (Join-Path $target 'keep.txt'))
}

Test-Case 'AC-3 a new data tree gives the service account modify on distro and read on payload' {
    $layout = New-TestStateLayout 'tree-data'
    $problems = @(Initialize-ProtectedTree -Tree $layout.DataTree -ServiceSid $script:ServiceSid)
    Assert-Equal 0 $problems.Count ($problems -join '; ')
    # The kit's design: the root is protected and holds Administrators and SYSTEM; an entry
    # folder inherits those two from the root only and adds the service account explicitly.
    $sidType = [System.Security.Principal.SecurityIdentifier]
    $distro = Get-Acl -LiteralPath $layout.Distro
    $effective = Get-OrdinalSorted @($distro.GetAccessRules($true, $true, $sidType) | Where-Object { $_.AccessControlType -eq 'Allow' } | ForEach-Object { $_.IdentityReference.Value } | Select-Object -Unique)
    Assert-Equal (Get-OrdinalSorted @('S-1-5-18', $script:ServiceSid, 'S-1-5-32-544')) $effective
    $inherited = Get-OrdinalSorted @($distro.GetAccessRules($false, $true, $sidType) | ForEach-Object { $_.IdentityReference.Value } | Select-Object -Unique)
    Assert-Equal @('S-1-5-18', 'S-1-5-32-544') $inherited 'inherited from the protected root only'
    Assert-Equal @($script:ServiceSid) (Get-ExplicitAllowSids -Path $layout.Distro)
    Assert-Equal 'Modify, Synchronize' ((@($distro.GetAccessRules($true, $false, $sidType) | Where-Object { $_.IdentityReference.Value -eq $script:ServiceSid }) | ForEach-Object { [string]$_.FileSystemRights }) -join ';')
    Assert-Equal 'ReadAndExecute, Synchronize' ((@((Get-Acl -LiteralPath $layout.Payload).GetAccessRules($true, $false, $sidType) | Where-Object { $_.IdentityReference.Value -eq $script:ServiceSid }) | ForEach-Object { [string]$_.FileSystemRights }) -join ';')
    Assert-Equal (Get-OrdinalSorted @('S-1-5-18', $script:ServiceSid, 'S-1-5-32-544')) (Get-ExplicitAllowSids -Path $layout.DataRoot) 'the root: Administrators, SYSTEM and the service account (read, this folder only)'
    Assert-Equal $true (Get-Acl -LiteralPath $layout.DataRoot).AreAccessRulesProtected
}

Test-Case 'AC-3 the data folder path is an absolute folder on a drive letter with no relative parts' {
    foreach ($good in @('D:\SlateOps', 'E:\Business data\SlateOps')) { Assert-Equal $true (Test-DataRootPath $good) $good }
    foreach ($bad in @('D:\', 'D:SlateOps', '\\server\share\SlateOps', 'D:\..\Windows', 'D:\a\.\b', 'D:\SlateOps\', 'D:\Slate"Ops', 'D:\x.')) { Assert-Equal $false (Test-DataRootPath $bad) $bad }
}

function New-AdminOnlyFolder {
    # A test folder on the system drive that only Administrators and SYSTEM control, owned by
    # Administrators: the folder above a test data folder, with nothing else wrong.
    param([Parameter(Mandatory = $true)][string]$Name)
    $path = Join-Path $env:SystemDrive ('{0}-{1}' -f $Name, ([guid]::NewGuid().ToString('N').Substring(0, 8)))
    [void][System.IO.Directory]::CreateDirectory($path, (Get-ProtectedDirectorySecurity))
    $null = & icacls.exe $path /setowner '*S-1-5-32-544' 2>&1
    $script:SystemDriveFolders.Add($path)
    return $path
}
$script:SystemDriveFolders = New-Object System.Collections.Generic.List[string]

try {
    Test-Case 'AC-3 S91-2 the default data folder on a drive root passes the parent check' {
        Assert-Equal 0 @(Get-FolderParentProblem -Path ('{0}\SlateOps' -f $env:SystemDrive)).Count (@(Get-FolderParentProblem -Path ('{0}\SlateOps' -f $env:SystemDrive)) -join '; ')
        $safe = New-AdminOnlyFolder 'SlateOpsW7Safe'
        Assert-Equal 0 @(Get-FolderParentProblem -Path (Join-Path $safe 'SlateOps')).Count (@(Get-FolderParentProblem -Path (Join-Path $safe 'SlateOps')) -join '; ')
    }

    Test-Case 'AC-3 S91-2 a data folder under a junction is refused' {
        $base = New-AdminOnlyFolder 'SlateOpsW7Junction'
        $target = New-TestDirectory 's91-2-target'
        $link = Join-Path $base 'link'
        $null = & cmd.exe /c mklink /J $link $target 2>&1
        $problems = @(Get-FolderParentProblem -Path (Join-Path $link 'SlateOps'))
        Assert-True ($problems -contains ('reparse_point:{0}' -f $link)) ($problems -join '; ')
        $layout = New-SlateOpsLayout -StateRoot (Join-Path (New-TestDirectory 's91-2-state') 'SlateOps')
        $result = Initialize-DataFolder -Layout $layout -DataRoot (Join-Path $link 'SlateOps')
        Assert-Equal 'data_folder_parent_unsafe setup.data.data_folder_parent_unsafe reparse_point' ('{0} {1} {2}' -f $result.code, $result.message_key, $result.values.reason)
        Assert-Equal $false (Test-Path -LiteralPath (Join-Path $target 'SlateOps')) 'nothing is created behind the junction'
    }

    Test-Case 'AC-3 S91-2 a folder above the data folder that Authenticated Users can modify is refused' {
        $base = New-AdminOnlyFolder 'SlateOpsW7Open'
        $open = Join-Path $base 'open'
        [void][System.IO.Directory]::CreateDirectory($open)
        $null = & icacls.exe $open /grant '*S-1-5-11:(OI)(CI)M' 2>&1
        $problems = @(Get-FolderParentProblem -Path (Join-Path $open 'SlateOps'))
        Assert-True ($problems -contains ('rights:{0}:S-1-5-11' -f $open)) ($problems -join '; ')
    }

    Test-Case 'AC-3 S91-1 the C29 removal stops at a junction kit folder and deletes nothing behind it' {
        $target = New-TestDirectory 's91-1-remove-target'
        foreach ($folder in @('kit', 'distro', 'logs')) { [void][System.IO.Directory]::CreateDirectory((Join-Path $target $folder)) }
        [System.IO.File]::WriteAllText((Join-Path $target 'kit\keep.txt'), 'keep')
        $link = Join-Path $script:TestRoot 's91-1-remove-kit'
        $null = & cmd.exe /c mklink /J $link $target 2>&1
        $kit = @{ AccountName = 'slateops-w7nokit'; Root = $link; TaskPath = '\SlateOpsW7NoKit\'; RuleName = 'SlateOpsW7NoKit-rule'; HyperVRule = 'SlateOpsW7NoKit-hv' }
        $result = Remove-KitLeftovers -Kit $kit
        Assert-Equal 'kit_folder_unsafe check.c29.unknown_parts' ('{0} {1}' -f $result.code, $result.message_key)
        Assert-Equal $true (Test-Path -LiteralPath (Join-Path $target 'kit\keep.txt'))
        Assert-Equal $true (Test-Path -LiteralPath (Join-Path $target 'distro'))
    }
} finally {
    foreach ($path in $script:SystemDriveFolders) { try { Remove-PathNoFollow -Path $path } catch { Write-Host ('cleanup: {0}' -f $_.Exception.Message) } }
}

Test-Case 'AC-3 P2-3 the recorded service SID keeps the state folder safe after a partial service step' {
    $layout = New-TestStateLayout 'p2-3-recorded'
    $problems = @(Initialize-ProtectedTree -Tree $layout.StateTree -ServiceSid $script:ServiceSid)
    Assert-Equal 0 $problems.Count ($problems -join '; ')
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ account_sid = $script:ServiceSid })
    Assert-Equal 'unsafe' (Test-StateFolder -Layout $layout).code 'without the SID the account entries are unknown'
    Assert-Equal $script:ServiceSid (Get-RecordedServiceSid -Layout $layout)
    Assert-Equal 'safe' (Test-StateFolder -Layout $layout -ServiceSid (Get-RecordedServiceSid -Layout $layout)).code
    Remove-ServiceAccess -Tree $layout.StateTree -Sid $script:ServiceSid
    $left = @(Get-TreeProblem -Tree $layout.StateTree)
    Assert-Equal 0 $left.Count ($left -join '; ')
}

Test-Case 'AC-3 S91-5 an existing folder never gets the service entry again; Grant-ServiceAccess gives it once' {
    $layout = New-TestStateLayout 's91-5-grants'
    $null = Initialize-ProtectedTree -Tree $layout.StateTree
    $before = (Get-Acl -LiteralPath $layout.Scripts).Sddl
    $null = Initialize-ProtectedTree -Tree $layout.StateTree -ServiceSid $script:ServiceSid
    Assert-Equal $before (Get-Acl -LiteralPath $layout.Scripts).Sddl 'an existing folder keeps its access list'
    $problems = @(Grant-ServiceAccess -Tree $layout.StateTree -ServiceSid $script:ServiceSid)
    Assert-Equal 0 $problems.Count ($problems -join '; ')
    $granted = (Get-Acl -LiteralPath $layout.Scripts).Sddl
    Assert-True ($granted -ne $before) 'Grant-ServiceAccess adds the entry'
    $null = Grant-ServiceAccess -Tree $layout.StateTree -ServiceSid $script:ServiceSid
    Assert-Equal $granted (Get-Acl -LiteralPath $layout.Scripts).Sddl 'a second grant changes nothing'
}
