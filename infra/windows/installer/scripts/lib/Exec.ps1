# Exec.ps1 - the \SlateOps\Exec boundary (plan 3.1, 3.2 rule 1, 6.2; kit lib/svc-exec.ps1).
#
# Service side (runs as slateops-svc from exec.ps1): read one request that only administrators
# can write, check it, run exactly one allow-listed job, and write the result. Data reaches the
# engine only on standard input, written to the process's raw input stream; no request field
# becomes a command, an argument or a path. The secret pipe channel is W8's.
# Administrator side (runs in setup): write the request, start the task, read the result as
# data with no JSON size limit (the log-bundle result can be 45 MiB).
# Windows PowerShell 5.1, ASCII only.

$SlateOpsExec = @{
    # Plan 6.2 allow-list plus resend-invitation (wizard spec section 12 item 11; Security
    # Engineer accepted it, TASK-0080). The engine refuses a job that it does not have yet.
    EngineJobs  = @('receive', 'prepare', 'prefetch', 'smtp-test', 'install', 'status', 'update', 'set-email',
        'set-backup-target', 'new-recovery-key', 'export-trust', 'log-bundle', 'prepare-uninstall', 'restore',
        'resend-invitation')
    # Windows-side work that must run as slateops-svc, because WSL distributions and .wslconfig
    # belong to the account that runs wsl.exe (kit design notes). Their paths come from the
    # administrator-only state file, never from the request.
    WindowsJobs = @('wslconfig', 'import-distro', 'wsl-facts')
    InputLimit  = 64KB          # engine core.py INPUT_LIMIT
    ReceiveRequestLimit = 4KB   # engine receive.py REQUEST_LIMIT
    StdoutCap   = 64MB          # above the 45 MiB log-bundle result (TASK-0083 carry)
    StderrCap   = 1MB           # plan 10.1 item 3
    KeepResults = 20
}

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

function Get-ExecRefusal {
    param([Parameter(Mandatory = $true)][string]$Code)
    return @{ ok = $false; code = $Code; message_key = ('exec.{0}' -f $Code) }
}

function Test-ExecRequest {
    # Checks the request text and the input bytes. Returns @{ ok; code; ... }. The request is
    # exactly {"request_id": <GUID>, "job": <one allow-listed name>, "run_id": <run ID>}.
    param(
        [AllowNull()][AllowEmptyString()][string]$RequestText,
        [AllowNull()][byte[]]$InputBytes
    )
    if (-not $RequestText) { return Get-ExecRefusal 'request_missing' }
    if ($RequestText.Length -gt 4096) { return Get-ExecRefusal 'request_invalid' }
    try { $request = ConvertFrom-JsonUnlimited $RequestText } catch { return Get-ExecRefusal 'request_invalid' }
    if (-not ($request -is [System.Collections.IDictionary])) { return Get-ExecRefusal 'request_invalid' }
    $keys = Get-OrdinalSorted @($request.Keys)
    if (($keys.Count -ne 3) -or (($keys -join ',') -cne 'job,request_id,run_id')) { return Get-ExecRefusal 'request_invalid' }
    $requestId = $request['request_id']
    $guid = [guid]::Empty
    if (-not (($requestId -is [string]) -and [guid]::TryParseExact($requestId, 'D', [ref]$guid))) { return Get-ExecRefusal 'request_invalid' }
    $job = $request['job']
    # One job name: a string, never a list, never two names (TASK-0083 carry).
    if (-not ($job -is [string])) { return (Get-ExecRefusal 'job_unknown') + @{ request_id = $requestId } }
    $class = $null
    if ($SlateOpsExec.EngineJobs -ccontains $job) { $class = 'engine' }
    elseif ($SlateOpsExec.WindowsJobs -ccontains $job) { $class = 'windows' }
    if (-not $class) { return (Get-ExecRefusal 'job_unknown') + @{ request_id = $requestId } }
    if (-not (Test-RunId $request['run_id'])) { return (Get-ExecRefusal 'run_id_invalid') + @{ request_id = $requestId; job = $job } }
    $bytes = $InputBytes
    if ($null -eq $bytes) { $bytes = New-Object byte[] 0 }
    if ($bytes.Length -gt $SlateOpsExec.InputLimit) { return (Get-ExecRefusal 'input_too_large') + @{ request_id = $requestId; job = $job } }
    if (($class -eq 'engine') -and ($bytes.Length -eq 0)) { return (Get-ExecRefusal 'input_missing') + @{ request_id = $requestId; job = $job } }
    return @{ ok = $true; code = 'accepted'; message_key = 'exec.accepted'; request_id = $requestId; job = $job; run_id = [string]$request['run_id']; job_class = $class; input = $bytes }
}

function Get-EngineArguments {
    # The fixed command line of an engine job: no shell, one job name, nothing from the request
    # apart from the allow-listed name (plan 3.1 Exec row).
    param([Parameter(Mandatory = $true)][string]$Job)
    if ($SlateOpsExec.EngineJobs -cnotcontains $Job) { throw 'Not an allow-listed engine job.' }
    return @('-d', $SlateOps.DistroName, '-u', 'root', '--exec', $SlateOps.EnginePath, $Job)
}

# ---------------------------------------------------------------------------
# receive: the setup payload as one tar stream (engine receive.py wire contract)
# ---------------------------------------------------------------------------

function Get-ReceivePartNames {
    # The members after request.json, in order: the signed manifest, its sigstore bundle, the
    # engine bundle and our two image archives (engine release.py names).
    param([Parameter(Mandatory = $true)][string]$Version)
    if (-not (Test-ReleaseVersion $Version)) { throw 'Not a release version.' }
    return @(
        'release-manifest.json',
        'release-manifest.json.sigstore.json',
        ('slateops-engine-{0}.tar.gz' -f $Version),
        ('slateops-server-{0}-amd64.oci.tar' -f $Version),
        ('slateops-caddy-{0}-amd64.oci.tar' -f $Version)
    )
}

function Test-ReceiveInput {
    # The receive input is the request.json member: exactly {run_id, setup_version}, with the
    # run ID of the Exec request.
    param([Parameter(Mandatory = $true)][byte[]]$InputBytes, [Parameter(Mandatory = $true)][string]$RunId)
    if ($InputBytes.Length -gt $SlateOpsExec.ReceiveRequestLimit) { return $null }
    try { $value = ConvertFrom-JsonUnlimited ([System.Text.Encoding]::UTF8.GetString($InputBytes)) } catch { return $null }
    if (-not ($value -is [System.Collections.IDictionary])) { return $null }
    if (((Get-OrdinalSorted @($value.Keys)) -join ',') -cne 'run_id,setup_version') { return $null }
    if ($value['run_id'] -cne $RunId) { return $null }
    if (-not (Test-ReleaseVersion $value['setup_version'])) { return $null }
    return [string]$value['setup_version']
}

function ConvertTo-OctalField {
    param([Parameter(Mandatory = $true)][long]$Value, [Parameter(Mandatory = $true)][int]$Digits)
    $text = [Convert]::ToString($Value, 8).PadLeft($Digits, '0')
    if ($text.Length -gt $Digits) { throw 'The value does not fit its tar field.' }
    return $text
}

function New-TarHeader {
    # One POSIX ustar header for a regular file: mode 0644, owner 0, time 0.
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][long]$Size)
    if (($Name.Length -eq 0) -or ($Name.Length -gt 99) -or ($Name -notmatch '^[A-Za-z0-9._-]+$')) { throw 'Not a valid member name.' }
    $header = New-Object byte[] 512
    $ascii = [System.Text.Encoding]::ASCII
    $put = {
        param([int]$Offset, [string]$Text)
        $data = $ascii.GetBytes($Text)
        [Array]::Copy($data, 0, $header, $Offset, $data.Length)
    }
    & $put 0 $Name
    & $put 100 ((ConvertTo-OctalField 420 7) + "`0")
    & $put 108 ((ConvertTo-OctalField 0 7) + "`0")
    & $put 116 ((ConvertTo-OctalField 0 7) + "`0")
    & $put 124 ((ConvertTo-OctalField $Size 11) + "`0")
    & $put 136 ((ConvertTo-OctalField 0 11) + "`0")
    & $put 148 '        '
    & $put 156 '0'
    & $put 257 ("ustar`0")
    & $put 263 '00'
    $sum = 0
    foreach ($b in $header) { $sum += $b }
    & $put 148 ((ConvertTo-OctalField $sum 6) + "`0 ")
    return , $header
}

function Write-TarMember {
    param(
        [Parameter(Mandatory = $true)][System.IO.Stream]$Stream,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][long]$Size,
        [Parameter(Mandatory = $true)][scriptblock]$WriteBody
    )
    $header = New-TarHeader -Name $Name -Size $Size
    $Stream.Write($header, 0, 512)
    & $WriteBody $Stream
    $pad = (512 - ($Size % 512)) % 512
    if ($pad -gt 0) { $Stream.Write((New-Object byte[] $pad), 0, [int]$pad) }
}

function Write-ReceiveStream {
    # Writes the receive tar stream: request.json, then each part from the payload folder, then
    # the two end blocks. Part names are fixed; a part that is missing, not a regular file or a
    # reparse point stops the job before any byte is written.
    param(
        [Parameter(Mandatory = $true)][System.IO.Stream]$Stream,
        [Parameter(Mandatory = $true)][byte[]]$RequestBytes,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$PayloadDir
    )
    $parts = @()
    foreach ($name in (Get-ReceivePartNames -Version $Version)) {
        $path = Join-Path $PayloadDir $name
        $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        if ((-not $item) -or $item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw (New-Object System.IO.FileNotFoundException('payload_part_missing'))
        }
        $parts += @{ name = $name; path = $path; size = [long]$item.Length }
    }
    Write-TarMember -Stream $Stream -Name 'request.json' -Size $RequestBytes.Length -WriteBody { param($s) $s.Write($RequestBytes, 0, $RequestBytes.Length) }
    foreach ($part in $parts) {
        Write-TarMember -Stream $Stream -Name $part.name -Size $part.size -WriteBody {
            param($s)
            $file = [System.IO.File]::Open($part.path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
            try {
                if ($file.Length -ne $part.size) { throw 'A payload part changed while it was sent.' }
                $file.CopyTo($s, 1MB)
            } finally { $file.Dispose() }
        }
    }
    $Stream.Write((New-Object byte[] 1024), 0, 1024)
}

# ---------------------------------------------------------------------------
# Running a process with data on its raw standard input
# ---------------------------------------------------------------------------

function Invoke-ProcessWithInput {
    # Starts FilePath with fixed arguments, drains standard output and standard error into files
    # on thread-pool tasks (so a large input cannot deadlock on a full output pipe), writes the
    # input with WriteInput to the raw input stream (never through the PowerShell pipeline), and
    # waits. A write that fails because the process closed its input is reported as pipe_closed
    # (a receive refusal closes standard input early; TASK-0083 carry).
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][scriptblock]$WriteInput,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [Parameter(Mandatory = $true)][string]$StderrPath
    )
    foreach ($argument in $ArgumentList) {
        if ($argument -notmatch '^[A-Za-z0-9/._-]+$') { throw 'An argument holds a character that needs quoting.' }
    }
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $FilePath
    $info.Arguments = ($ArgumentList -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    $outFile = [System.IO.File]::Open($StdoutPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    $errFile = [System.IO.File]::Open($StderrPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    $pipeClosed = $false
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        [void]$process.Start()
        $outTask = $process.StandardOutput.BaseStream.CopyToAsync($outFile)
        $errTask = $process.StandardError.BaseStream.CopyToAsync($errFile)
        $inStream = $process.StandardInput.BaseStream
        try {
            & $WriteInput $inStream
            $inStream.Flush()
        } catch {
            $inner = $_.Exception
            while ($inner -and -not ($inner -is [System.IO.IOException])) { $inner = $inner.InnerException }
            if (($inner -is [System.IO.IOException]) -and -not ($inner -is [System.IO.FileNotFoundException])) { $pipeClosed = $true }
            else { throw }
        } finally {
            try { $inStream.Dispose() } catch { $pipeClosed = $true }
        }
        $process.WaitForExit()
        $outTask.Wait()
        $errTask.Wait()
        $exitCode = $process.ExitCode
    } finally {
        $watch.Stop()
        $outFile.Dispose()
        $errFile.Dispose()
        $process.Dispose()
    }
    return @{ exit_code = $exitCode; pipe_closed = $pipeClosed; duration_ms = $watch.ElapsedMilliseconds }
}

function Limit-ErrorFile {
    # Cuts standard error to its cap and masks it (plan 10.1 item 3).
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $count = [math]::Min($bytes.Length, [int]$SlateOpsExec.StderrCap)
    $text = [System.Text.Encoding]::UTF8.GetString($bytes, 0, $count)
    [System.IO.File]::WriteAllText($Path, (Protect-LogText $text), (New-Object System.Text.UTF8Encoding($false)))
    return $count
}

function Get-EngineCode {
    # Reads only the safe code fields of the engine's one JSON object. Values of other fields
    # are never logged (the log-bundle body, the progress numbers).
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $value = ConvertFrom-JsonUnlimited ([System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8))
        if (-not ($value -is [System.Collections.IDictionary])) { return @{ code = 'output_invalid'; message_key = 'exec.output_invalid' } }
        $code = [string](Get-DictValue $value 'code')
        $key = [string](Get-DictValue $value 'message_key')
        if ($code -notmatch '^[a-z0-9_]{1,64}$') { $code = 'output_invalid' }
        if ($key -and ($key -notmatch '^[a-z0-9_.-]{1,96}$')) { $key = '' }
        return @{ code = $code; message_key = $key }
    } catch {
        return @{ code = 'output_invalid'; message_key = 'exec.output_invalid' }
    }
}

# ---------------------------------------------------------------------------
# The service side: one request, one job
# ---------------------------------------------------------------------------

function Invoke-ExecRequest {
    # Runs the request in the layout's requests folder. -WslPath exists for the tests, which
    # pass a stand-in program; exec.ps1 always uses System32\wsl.exe.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [string]$WslPath = (Get-WslExe)
    )
    $requestText = $null
    $inputBytes = $null
    if (Test-Path -LiteralPath $Layout.RequestFile -PathType Leaf) {
        $requestText = [System.IO.File]::ReadAllText($Layout.RequestFile, [System.Text.Encoding]::UTF8)
    }
    if (Test-Path -LiteralPath $Layout.InputFile -PathType Leaf) {
        $length = (Get-Item -LiteralPath $Layout.InputFile -Force).Length
        if ($length -le ($SlateOpsExec.InputLimit + 1)) { $inputBytes = [System.IO.File]::ReadAllBytes($Layout.InputFile) }
        else { $inputBytes = New-Object byte[] ($SlateOpsExec.InputLimit + 1) }
    }
    $check = Test-ExecRequest -RequestText $requestText -InputBytes $inputBytes
    $result = @{
        request_id = $(if ($check.ContainsKey('request_id')) { $check.request_id } else { '' })
        job        = $(if ($check.ContainsKey('job')) { $check.job } else { '' })
        job_class  = $(if ($check.ContainsKey('job_class')) { $check.job_class } else { '' })
        code       = $check.code
        message_key = $check.message_key
        exit_code  = 2
        pipe_closed = $false
        stdout_file = ''
        stdout_bytes = 0
        stdout_sha256 = ''
    }
    if (-not $check.ok) {
        Write-RunLog 'exec.request' 'WARN' ('refused: {0}' -f $check.code)
        Write-ExecResult -Layout $Layout -Result $result
        return $result
    }
    Write-RunLog ('exec.{0}' -f $check.job) 'INFO' ('request {0}, job {1} ({2}), input {3} bytes' -f $check.request_id, $check.job, $check.job_class, $check.input.Length)
    try {
        if ($check.job_class -eq 'engine') {
            $result = Invoke-EngineJob -Layout $Layout -Check $check -WslPath $WslPath -Result $result
        } else {
            $result = Invoke-WindowsJob -Layout $Layout -Check $check -WslPath $WslPath -Result $result
        }
    } catch {
        Write-RunLog ('exec.{0}' -f $check.job) 'ERROR' $_.Exception.Message
        $result.code = 'exec_failed'
        $result.message_key = 'exec.exec_failed'
        $result.exit_code = 3
        if ($_.Exception.Message -eq 'payload_part_missing') { $result.code = 'payload_part_missing'; $result.message_key = 'exec.payload_part_missing'; $result.exit_code = 2 }
    }
    Write-RunLog ('exec.{0}' -f $check.job) 'INFO' ('result {0}, exit code {1}' -f $result.code, $result.exit_code)
    Write-ExecResult -Layout $Layout -Result $result
    Remove-OldExecOutput -Layout $Layout
    return $result
}

function Invoke-EngineJob {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][hashtable]$Check,
        [Parameter(Mandatory = $true)][string]$WslPath,
        [Parameter(Mandatory = $true)][hashtable]$Result
    )
    $job = $Check.job
    $version = $null
    if ($job -eq 'receive') {
        $version = Test-ReceiveInput -InputBytes $Check.input -RunId $Check.run_id
        if (-not $version) {
            $Result.code = 'input_invalid'; $Result.message_key = 'exec.input_invalid'; $Result.exit_code = 2
            return $Result
        }
        # Every part must exist before the engine starts (no half stream for a missing file).
        foreach ($name in (Get-ReceivePartNames -Version $version)) {
            $path = Join-Path $Layout.Payload $name
            $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
            if ((-not $item) -or $item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                $Result.code = 'payload_part_missing'; $Result.message_key = 'exec.payload_part_missing'; $Result.exit_code = 2
                return $Result
            }
        }
    }
    $stdout = Join-Path $Layout.SvcOut ('{0}.stdout.json' -f $Check.request_id)
    $stderr = Join-Path $Layout.SvcOut ('{0}.stderr.txt' -f $Check.request_id)
    $arguments = Get-EngineArguments -Job $job
    Write-RunLog ('exec.{0}' -f $job) 'INFO' ('> {0} {1}' -f (Split-Path -Leaf $WslPath), ($arguments -join ' '))
    $inputBytes = $Check.input
    $payload = $Layout.Payload
    if ($job -eq 'receive') {
        $writer = { param($stream) Write-ReceiveStream -Stream $stream -RequestBytes $inputBytes -Version $version -PayloadDir $payload }
    } else {
        $writer = { param($stream) $stream.Write($inputBytes, 0, $inputBytes.Length) }
    }
    $env:WSL_UTF8 = '1'
    $run = Invoke-ProcessWithInput -FilePath $WslPath -ArgumentList $arguments -WriteInput $writer -StdoutPath $stdout -StderrPath $stderr
    $errBytes = Limit-ErrorFile -Path $stderr
    $outItem = Get-Item -LiteralPath $stdout -Force
    $Result.exit_code = $run.exit_code
    $Result.pipe_closed = [bool]$run.pipe_closed
    $Result.stdout_bytes = [long]$outItem.Length
    Write-RunLog ('exec.{0}' -f $job) 'INFO' ('  exit code {0}, {1} ms, stdout {2} bytes, stderr {3} bytes, input closed early {4}' -f $run.exit_code, $run.duration_ms, $outItem.Length, $errBytes, $run.pipe_closed)
    if ($outItem.Length -gt $SlateOpsExec.StdoutCap) {
        Remove-PathNoFollow -Path $stdout
        $Result.code = 'output_too_large'; $Result.message_key = 'exec.output_too_large'; $Result.exit_code = 3
        return $Result
    }
    $Result.stdout_file = Split-Path -Leaf $stdout
    $Result.stdout_sha256 = Get-FileSha256 -Path $stdout
    $engine = Get-EngineCode -Path $stdout
    $Result.code = $engine.code
    $Result.message_key = $engine.message_key
    if ($run.pipe_closed -and ($run.exit_code -eq 0)) {
        # The engine stopped reading but reports success: never trust a half-sent payload.
        $Result.code = 'input_not_read'; $Result.message_key = 'exec.input_not_read'; $Result.exit_code = 3
    }
    return $Result
}

function Write-ExecResult {
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][hashtable]$Result)
    $Result.finished_at = Get-UtcStamp
    Write-JsonFile -Path $Layout.ResultFile -Value $Result
}

function Remove-OldExecOutput {
    # Keeps the output files of the newest 20 requests in svc-out.
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $files = @(Get-ChildItem -LiteralPath $Layout.SvcOut -Force -File | Where-Object { $_.Name -match '^[0-9a-f-]{36}\.(stdout\.json|stderr\.txt|out\.txt)$' } | Sort-Object -Property LastWriteTimeUtc -Descending)
    $ids = @()
    foreach ($file in $files) {
        $id = $file.Name.Substring(0, 36)
        if ($ids -notcontains $id) { $ids += $id }
        if ($ids.IndexOf($id) -ge $SlateOpsExec.KeepResults) { Remove-PathNoFollow -Path $file.FullName }
    }
}

# ---------------------------------------------------------------------------
# Windows-side jobs as slateops-svc
# ---------------------------------------------------------------------------

function Get-WslConfigText {
    # The kit's .wslconfig (lib/svc-exec.ps1 Write-WslConfig), with the plan's disk size.
    # networkingMode=mirrored; DNS tunneling keeps its default (no key). vmIdleTimeout=-1 and
    # [general] instanceIdleTimeout=-1 are both needed (WSL issue 13291, kit design notes).
    param([int]$MemoryGB = $SlateOps.WslMemoryGB, [Parameter(Mandatory = $true)][int]$VhdSizeGB)
    if (($VhdSizeGB -lt 16) -or ($VhdSizeGB -gt 4096)) { throw 'The disk size is outside 16 to 4096 GB.' }
    return @(
        '# Written by Slate Operations setup for the account slateops-svc.',
        '[wsl2]',
        ('memory={0}GB' -f $MemoryGB),
        'vmIdleTimeout=-1',
        'networkingMode=mirrored',
        ('defaultVhdSize={0}GB' -f $VhdSizeGB),
        '',
        '[general]',
        'instanceIdleTimeout=-1'
    )
}

function Read-InstallState {
    # The administrator-only state file (state\install.json): the data folder and the disk
    # size. The service account reads it; a request never names a path.
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $value = Read-JsonFile -Path $Layout.StateFile
    if (-not ($value -is [System.Collections.IDictionary])) { throw 'state_invalid' }
    $root = [string](Get-DictValue $value 'data_root')
    if (-not (Test-DataRootPath $root)) { throw 'state_invalid' }
    $size = Get-DictValue $value 'vhd_size_gb'
    if (-not ($size -is [int])) { throw 'state_invalid' }
    return @{ data_root = $root; vhd_size_gb = [int]$size }
}

function Test-DataRootPath {
    # An absolute folder on a drive letter, not a drive root, with no relative parts.
    param([AllowNull()][string]$Path)
    if (-not $Path) { return $false }
    if ($Path.Length -gt 200) { return $false }
    if ($Path -notmatch '^[A-Za-z]:\\[^<>:"/|?*\x00-\x1f]+$') { return $false }
    foreach ($part in ($Path.Substring(3) -split '\\')) {
        if (($part -eq '') -or ($part -eq '.') -or ($part -eq '..') -or $part.EndsWith(' ') -or $part.EndsWith('.')) { return $false }
    }
    return $true
}

function Read-SetupVersion {
    # version.json next to the scripts (administrator-only; W8's build writes it): the release
    # version, the pinned WSL MSI, and the Linux image with its SHA-256, all compiled in.
    param([Parameter(Mandatory = $true)][string]$Path)
    $value = Read-JsonFile -Path $Path
    if (-not ($value -is [System.Collections.IDictionary])) { throw 'version_invalid' }
    if ((Get-DictValue $value 'schema_version') -ne 1) { throw 'version_invalid' }
    if (-not (Test-ReleaseVersion (Get-DictValue $value 'version'))) { throw 'version_invalid' }
    foreach ($key in @('wsl_msi_sha256', 'linux_image_sha256')) {
        if ([string](Get-DictValue $value $key) -cnotmatch '^[0-9a-f]{64}$') { throw 'version_invalid' }
    }
    if ([string](Get-DictValue $value 'wsl_version') -notmatch '^[0-9]{1,4}(\.[0-9]{1,6}){3}$') { throw 'version_invalid' }
    return @{
        version            = [string]$value['version']
        wsl_version        = [version][string]$value['wsl_version']
        wsl_msi_sha256     = [string]$value['wsl_msi_sha256']
        linux_image_sha256 = [string]$value['linux_image_sha256']
        linux_image_name   = ('slateops-linux-{0}-amd64.tar.gz' -f $value['version'])
        wsl_msi_name       = ('wsl.{0}.x64.msi' -f $value['wsl_version'])
    }
}

function Invoke-WindowsJob {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][hashtable]$Check,
        [Parameter(Mandatory = $true)][string]$WslPath,
        [Parameter(Mandatory = $true)][hashtable]$Result
    )
    $step = 'exec.{0}' -f $Check.job
    $env:WSL_UTF8 = '1'
    switch ($Check.job) {
        'wslconfig' {
            $state = Read-InstallState -Layout $Layout
            $path = Join-Path $env:USERPROFILE '.wslconfig'
            $lines = Get-WslConfigText -VhdSizeGB $state.vhd_size_gb
            [System.IO.File]::WriteAllText($path, (($lines -join "`r`n") + "`r`n"), [System.Text.Encoding]::ASCII)
            foreach ($line in $lines) { Write-RunLog $step 'INFO' ('  {0}' -f $line) }
            $Result.code = 'written'
        }
        'import-distro' {
            $state = Read-InstallState -Layout $Layout
            Set-LayoutDataRoot -Layout $Layout -DataRoot $state.data_root
            $setup = Read-SetupVersion -Path (Join-Path $Layout.Scripts 'version.json')
            $list = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList @('--list', '--quiet') -NoThrow
            if (@($list.Output | Where-Object { $_.Trim() -eq $SlateOps.DistroName }).Count -gt 0) {
                $Result.code = 'already_imported'
            } else {
                $image = Join-Path $Layout.Payload $setup.linux_image_name
                $tar = Join-Path $Layout.Distro 'rootfs.tar'
                # Checked right before the import (plan 4.1 page 4a, 5.2).
                $hash = Get-FileSha256 -Path $image
                Write-RunLog $step 'INFO' ('  SHA-256 of {0}: {1}' -f $setup.linux_image_name, $hash)
                if ($hash -ne $setup.linux_image_sha256) { $Result.code = 'image_hash_mismatch'; $Result.exit_code = 3; $Result.message_key = 'exec.image_hash_mismatch'; return $Result }
                Expand-GzipFile -Source $image -Destination $tar
                try {
                    $import = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList @('--import', $SlateOps.DistroName, $Layout.Distro, $tar, '--version', '2') -NoThrow
                } finally { Remove-PathNoFollow -Path $tar }
                if ($import.ExitCode -ne 0) { $Result.code = 'import_failed'; $Result.exit_code = 3; $Result.message_key = 'exec.import_failed'; return $Result }
                $Result.code = 'imported'
            }
        }
        'wsl-facts' {
            foreach ($arguments in @(@('--version'), @('--status'), @('--list', '--verbose'))) {
                $null = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList $arguments -NoThrow
            }
            $config = Join-Path $env:USERPROFILE '.wslconfig'
            if (Test-Path -LiteralPath $config) {
                foreach ($line in (Get-Content -LiteralPath $config)) { Write-RunLog $step 'INFO' ('  .wslconfig: {0}' -f $line) }
            } else { Write-RunLog $step 'WARN' '  .wslconfig is missing' }
            $Result.code = 'recorded'
        }
    }
    if (-not $Result.message_key -or ($Result.message_key -like 'exec.accepted')) { $Result.message_key = ('exec.{0}.{1}' -f $Check.job, $Result.code) }
    if ($Result.exit_code -eq 2 -and ($Result.code -in @('written', 'already_imported', 'imported', 'recorded'))) { $Result.exit_code = 0 }
    return $Result
}

function Expand-GzipFile {
    # Kit function: wsl --import gets a plain tar.
    param([Parameter(Mandatory = $true)][string]$Source, [Parameter(Mandatory = $true)][string]$Destination)
    $in = [System.IO.File]::OpenRead($Source)
    try {
        $gzip = New-Object System.IO.Compression.GZipStream($in, [System.IO.Compression.CompressionMode]::Decompress)
        $out = [System.IO.File]::Open($Destination, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
        try { $gzip.CopyTo($out, 1MB) } finally { $out.Dispose(); $gzip.Dispose() }
    } finally { $in.Dispose() }
}

# ---------------------------------------------------------------------------
# The administrator side
# ---------------------------------------------------------------------------

function Submit-ExecRequest {
    # Writes the input, then the request, then starts the task (kit Invoke-SvcJob). The task
    # runs one job at a time (MultipleInstances IgnoreNew), so a running task is refused here.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][string]$Job,
        [Parameter(Mandatory = $true)][string]$RunId,
        [byte[]]$InputBytes = (New-Object byte[] 0),
        [switch]$NoStart
    )
    if (($SlateOpsExec.EngineJobs -cnotcontains $Job) -and ($SlateOpsExec.WindowsJobs -cnotcontains $Job)) { throw 'Not an allow-listed job.' }
    if (-not (Test-RunId $RunId)) { throw 'Not a run ID.' }
    if (-not $NoStart) {
        $task = Get-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.ExecTaskName -ErrorAction Stop
        if ($task.State -eq 'Running') { throw 'exec_busy' }
    }
    $requestId = [guid]::NewGuid().ToString('D')
    foreach ($path in @($Layout.RequestFile, $Layout.InputFile)) { if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path } }
    [System.IO.File]::WriteAllBytes($Layout.InputFile, $InputBytes)
    Write-JsonFile -Path $Layout.RequestFile -Value ([ordered]@{ request_id = $requestId; job = $Job; run_id = $RunId })
    Write-RunLog ('exec.submit.{0}' -f $Job) 'INFO' ('request {0}, input {1} bytes' -f $requestId, $InputBytes.Length)
    if (-not $NoStart) { Start-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.ExecTaskName }
    return $requestId
}

function Get-ExecResult {
    # Returns the result of the request, or $null while it has none. The service account writes
    # svc-out; this side reads it as data and never follows a link there.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$RequestId)
    if (-not (Test-Path -LiteralPath $Layout.ResultFile -PathType Leaf)) { return $null }
    try { $value = Read-JsonFile -Path $Layout.ResultFile } catch { return $null }
    if (-not ($value -is [System.Collections.IDictionary])) { return $null }
    if ([string](Get-DictValue $value 'request_id') -cne $RequestId) { return $null }
    return $value
}

function Read-EngineOutput {
    # Parses the engine's one JSON object with no size limit, after checking that the file is
    # the one Exec measured (size and SHA-256).
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Result)
    $name = [string](Get-DictValue $Result 'stdout_file')
    if ($name -notmatch '^[0-9a-f-]{36}\.stdout\.json$') { throw 'output_missing' }
    $path = Join-Path $Layout.SvcOut $name
    $item = Get-Item -LiteralPath $path -Force
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'output_invalid' }
    if (($item.Length -ne [long](Get-DictValue $Result 'stdout_bytes')) -or ((Get-FileSha256 -Path $path) -ne [string](Get-DictValue $Result 'stdout_sha256'))) { throw 'output_changed' }
    return ConvertFrom-JsonUnlimited ([System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8))
}

function Save-LogBundle {
    # Stores the log-bundle .tar.gz as one opaque file at a path that the caller chose (never a
    # name from Linux), after checking its size and SHA-256. Logs only those two values.
    param(
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Output,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )
    $encoded = [string](Get-DictValue $Output 'bundle_base64')
    $expectedSha = [string](Get-DictValue $Output 'bundle_sha256')
    $expectedSize = Get-DictValue $Output 'bundle_size'
    if (($expectedSha -cnotmatch '^[0-9a-f]{64}$') -or (-not ($expectedSize -is [int] -or $expectedSize -is [long]))) { throw 'bundle_invalid' }
    try { $bytes = [Convert]::FromBase64String($encoded) } catch { throw 'bundle_invalid' }
    if ($bytes.Length -ne [long]$expectedSize) { throw 'bundle_invalid' }
    $sha = New-Object System.Security.Cryptography.SHA256Managed
    try { $actual = -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) } finally { $sha.Dispose() }
    if ($actual -ne $expectedSha) { throw 'bundle_invalid' }
    $file = [System.IO.File]::Open($DestinationPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try { $file.Write($bytes, 0, $bytes.Length) } finally { $file.Dispose() }
    Write-RunLog 'report.linux_bundle' 'INFO' ('stored {0} bytes, SHA-256 {1}' -f $bytes.Length, $actual)
    return @{ bytes = $bytes.Length; sha256 = $actual }
}
