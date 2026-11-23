# Report.ps1 - Save report on the Windows side (plan 10.6, DEC-0033; wizard spec S13, W8-6).
#
# Two steps, so the wizard can check the staged files for the email password that it holds
# before anything is packed (plan 10.6 item 3): New-ReportStaging copies the logs (10.1), the
# environment facts (10.4), the Windows part of the failure snapshot (10.5) and the Linux part
# (the engine's log-bundle, kept as one opaque file) into a staging folder, redacted;
# Complete-Report packs that folder into SlateOps-report-<run ID>.zip on the person's own
# desktop. A link is never followed, and a file that cannot be redacted is left out and listed.
# Windows PowerShell 5.1, ASCII only.

$SlateOpsReport = @{
    MaxFileBytes = 10MB
    TextNames    = '\.(log|txt|json)$'
    # Two days of Windows events cover a run and the restart before it (plan 10.5 item 6).
    EventDays    = 2
}

function Protect-ReportText {
    # The masking of 10.1 (registered values and secret patterns), then the patterns that only
    # the report needs: the recovery key format (8 groups of 4 base32 characters, engine
    # drive.py) and personal data (10.6 item 4): email addresses and the names of Windows users.
    param([AllowNull()][AllowEmptyString()][string]$Text, [string[]]$UserNames = @())
    if ($null -eq $Text -or $Text.Length -eq 0) { return $Text }
    $out = Protect-LogText $Text
    $out = [regex]::Replace($out, '\b[A-Z2-7]{4}(-[A-Z2-7]{4}){7}\b', '[recovery key]')
    $options = [System.Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
    $out = [regex]::Replace($out, '(?<![a-z0-9._%+-])[a-z0-9._%+-]{1,64}@[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63}){0,8}\.[a-z]{2,63}', '[email]', $options)
    $out = [regex]::Replace($out, '(\\Users\\)[^\\\s"]{1,64}', '$1[user]', $options)
    foreach ($name in @($UserNames | Where-Object { $_ -and $_.Length -ge 3 } | Sort-Object -Property Length -Descending)) {
        $out = [regex]::Replace($out, ('(?<![a-z0-9]){0}(?![a-z0-9])' -f [regex]::Escape($name)), '[user]', $options)
    }
    return $out
}

function Get-ReportUserNames {
    # The Windows user names that can appear in a log line: this process's user and the
    # signed-in user of the session.
    $names = @([Environment]::UserName)
    try { $session = Get-SessionUserName; if ($session) { $names += ($session -split '\\')[-1] } } catch { $null = $_ }
    return @($names | Select-Object -Unique)
}

function Add-ReportFile {
    # Copies one file into the staging folder under a flat name, redacted. Returns $true when it
    # was added; a link, a file that is too large or not text is left out and named in $LeftOut.
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$StagingDir,
        [Parameter(Mandatory = $true)][string]$Name,
        # AC-O7 (owner, rc.28): the list is empty until a file is left out (Windows PowerShell
        # refuses an empty collection for a Mandatory parameter without this).
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][System.Collections.Generic.List[string]]$LeftOut,
        [string[]]$UserNames = @()
    )
    $item = Get-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
    if ((-not $item) -or $item.PSIsContainer) { return $false }
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { $LeftOut.Add(('{0} (a link)' -f $Name)); return $false }
    if ($item.Length -gt $SlateOpsReport.MaxFileBytes) { $LeftOut.Add(('{0} (larger than 10 MB)' -f $Name)); return $false }
    if ($item.Name -notmatch $SlateOpsReport.TextNames) { $LeftOut.Add(('{0} (not a text file)' -f $Name)); return $false }
    try {
        $strict = New-Object System.Text.UTF8Encoding($false, $true)
        $text = $strict.GetString([System.IO.File]::ReadAllBytes($item.FullName))
    } catch {
        $LeftOut.Add(('{0} (not readable as text)' -f $Name)); return $false
    }
    $clean = Protect-ReportText -Text $text -UserNames $UserNames
    # A key block that the masking could not close is a hit that cannot be replaced.
    if ($clean -match 'PRIVATE KEY-----') { $LeftOut.Add(('{0} (holds a secret that cannot be removed)' -f $Name)); return $false }
    [System.IO.File]::WriteAllText((Join-Path $StagingDir $Name), $clean, (New-Object System.Text.UTF8Encoding($false)))
    return $true
}

function Get-ReportFolderFiles {
    # The files below a folder, never through a link: a linked folder is not entered.
    param([Parameter(Mandatory = $true)][string]$Root)
    $out = New-Object System.Collections.Generic.List[object]
    $pending = New-Object System.Collections.Generic.Queue[string]
    $pending.Enqueue($Root)
    while ($pending.Count -gt 0) {
        $dir = $pending.Dequeue()
        foreach ($child in @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue)) {
            if ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                $out.Add(@{ path = $child.FullName; link = $true })
            } elseif ($child.PSIsContainer) {
                $pending.Enqueue($child.FullName)
            } else {
                $out.Add(@{ path = $child.FullName; link = $false })
            }
        }
    }
    return $out
}

function ConvertTo-ReportName {
    param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Prefix)
    $relative = $Path.Substring($Root.TrimEnd('\').Length).TrimStart('\')
    return ('{0}__{1}' -f $Prefix, ($relative -replace '[\\/:*?"<>|]', '__'))
}

function Get-WindowsSnapshotText {
    # Plan 10.5 items 6 and 7, Windows part: each \SlateOps\ task with its state, last run time
    # and last result (never its account), and the restart and installer events.
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('Tasks in \SlateOps\:')
    try {
        foreach ($task in @(Get-ScheduledTask -TaskPath $SlateOps.TaskPath -ErrorAction Stop)) {
            $info = Get-ScheduledTaskInfo -TaskPath $task.TaskPath -TaskName $task.TaskName
            $lines.Add(('  {0}: state {1}, last run {2}, last result 0x{3:X8}' -f $task.TaskName, $task.State, (Get-UtcStamp -Time $info.LastRunTime), [uint32]$info.LastTaskResult))
        }
    } catch { $lines.Add('  none, or not readable') }
    $since = (Get-Date).AddDays(-$SlateOpsReport.EventDays)
    $queries = @(
        @{ name = 'System restart and power events (41, 6008, 1074)'; filter = @{ LogName = 'System'; Id = @(41, 6008, 1074); StartTime = $since } },
        @{ name = 'Windows Installer events'; filter = @{ LogName = 'Application'; ProviderName = 'MsiInstaller'; StartTime = $since } }
    )
    foreach ($query in $queries) {
        $lines.Add(('{0}:' -f $query.name))
        try {
            foreach ($event in @(Get-WinEvent -FilterHashtable $query.filter -MaxEvents 50 -ErrorAction Stop)) {
                $message = ([string]$event.Message -replace '\s+', ' ')
                if ($message.Length -gt 400) { $message = $message.Substring(0, 400) }
                $lines.Add(('  {0} id {1} {2}: {3}' -f (Get-UtcStamp -Time $event.TimeCreated), $event.Id, $event.ProviderName, $message))
            }
        } catch { $lines.Add('  none') }
    }
    return ($lines -join "`r`n")
}

function New-ReportStaging {
    # Fills StagingDir (an empty folder inside the helper's own root). InnoLog and LinuxBundle
    # are copies inside the same root, or empty. Returns @{ files; left_out }.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][string]$StagingDir,
        [Parameter(Mandatory = $true)][string]$RunId,
        [string]$InnoLog = '',
        [string]$LinuxBundle = '',
        [string]$SetupVersion = '',
        [switch]$StateTrusted,
        # W8 correction 7: before S07 there is no state folder; the helper logs in its own folder.
        [switch]$StateAbsent,
        [string]$HelperLogs = '',
        [hashtable]$Facts = $null
    )
    [void][System.IO.Directory]::CreateDirectory($StagingDir)
    $users = @(Get-ReportUserNames)
    $leftOut = New-Object System.Collections.Generic.List[string]
    $added = 0
    if ($StateTrusted) {
        foreach ($part in @(@{ dir = $Layout.Logs; prefix = 'logs' }, @{ dir = $Layout.State; prefix = 'state' }, @{ dir = $Layout.SvcOut; prefix = 'svc-out' })) {
            if (-not (Test-Path -LiteralPath $part.dir)) { continue }
            foreach ($file in (Get-ReportFolderFiles -Root $part.dir)) {
                $name = ConvertTo-ReportName -Root $part.dir -Path $file.path -Prefix $part.prefix
                # Engine outputs stay out: the log-bundle result is the Linux part below.
                if ($name -match '\.stdout\.json$') { continue }
                if ($file.link) { $leftOut.Add(('{0} (a link)' -f $name)); continue }
                if (Add-ReportFile -Source $file.path -StagingDir $StagingDir -Name $name -LeftOut $leftOut -UserNames $users) { $added++ }
            }
        }
    } elseif ($StateAbsent) {
        $leftOut.Add('C:\ProgramData\SlateOps (not created yet)')
    } else {
        $leftOut.Add('C:\ProgramData\SlateOps (the folder failed the safety check; nothing was read from it)')
    }
    if ($HelperLogs -and (Test-Path -LiteralPath $HelperLogs)) {
        foreach ($file in (Get-ReportFolderFiles -Root $HelperLogs)) {
            $name = ConvertTo-ReportName -Root $HelperLogs -Path $file.path -Prefix 'setup-early'
            if ($file.link) { $leftOut.Add(('{0} (a link)' -f $name)); continue }
            if (Add-ReportFile -Source $file.path -StagingDir $StagingDir -Name $name -LeftOut $leftOut -UserNames $users) { $added++ }
        }
    }
    if ($InnoLog -and (Test-Path -LiteralPath $InnoLog -PathType Leaf)) {
        if (Add-ReportFile -Source $InnoLog -StagingDir $StagingDir -Name 'setup-program.log' -LeftOut $leftOut -UserNames $users) { $added++ }
    }
    if ($null -eq $Facts) { $Facts = Get-EnvironmentFacts -SetupVersion $SetupVersion }
    [System.IO.File]::WriteAllText((Join-Path $StagingDir 'facts.json'), (Protect-ReportText -Text (ConvertTo-JsonText $Facts) -UserNames $users), (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::WriteAllText((Join-Path $StagingDir 'windows-snapshot.txt'), (Protect-ReportText -Text (Get-WindowsSnapshotText) -UserNames $users), (New-Object System.Text.UTF8Encoding($false)))
    $linux = 'Linux part not reachable'
    if ($LinuxBundle -and (Test-Path -LiteralPath $LinuxBundle -PathType Leaf)) {
        $item = Get-Item -LiteralPath $LinuxBundle -Force
        if (-not ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            # Already redacted by the engine; kept as one opaque file (TASK-0083 carry).
            [System.IO.File]::Copy($item.FullName, (Join-Path $StagingDir 'linux-part.tar.gz'))
            $linux = ('Linux part: linux-part.tar.gz, {0} bytes' -f $item.Length)
        }
    }
    $summary = @(
        ('Slate Operations report {0}' -f $RunId),
        ('Setup version: {0}' -f $SetupVersion),
        ('Made at: {0}' -f (Get-UtcStamp)),
        $linux,
        ('Files: {0}' -f $added),
        'Left out:'
    ) + @($leftOut | ForEach-Object { '  ' + $_ })
    [System.IO.File]::WriteAllText((Join-Path $StagingDir 'report.txt'), (($summary -join "`r`n") + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
    return @{ files = $added; left_out = $leftOut.Count }
}

function Get-ReportDesktop {
    # The person's own desktop (plan 10.6 item 5), never the Public desktop.
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    $public = [Environment]::GetFolderPath('CommonDesktopDirectory')
    if ((-not $desktop) -or ($public -and ($desktop.TrimEnd('\') -ieq $public.TrimEnd('\')))) { throw 'desktop_unavailable' }
    return $desktop
}

function Complete-Report {
    # Packs the staging folder into SlateOps-report-<run ID>.zip in Destination (a new file;
    # an existing file or link is never written through). Returns the full path.
    param(
        [Parameter(Mandatory = $true)][string]$StagingDir,
        [Parameter(Mandatory = $true)][string]$RunId,
        [string]$Destination = (Get-ReportDesktop)
    )
    if (-not (Test-RunId $RunId)) { throw 'run_id_invalid' }
    $folder = Get-Item -LiteralPath $Destination -Force
    if ($folder.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'desktop_unavailable' }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $path = Join-Path $folder.FullName ('SlateOps-report-{0}.zip' -f $RunId)
    $stream = [System.IO.File]::Open($path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try {
        $zip = New-Object System.IO.Compression.ZipArchive($stream, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($file in @(Get-ChildItem -LiteralPath $StagingDir -Force -File)) {
                [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $file.Name)
            }
        } finally { $zip.Dispose() }
    } finally { $stream.Dispose() }
    Write-RunLog 'report.saved' 'INFO' ('report saved: {0}' -f $path)
    return $path
}
