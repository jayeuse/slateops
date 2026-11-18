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
    # Plan 6.2 allow-list. The engine refuses a job that it does not have yet. R-8 (DEC-0041):
    # resend-invitation is gone with the invitation of the first administrator.
    EngineJobs  = @('receive', 'prepare', 'prefetch', 'smtp-test', 'install', 'status', 'update', 'set-email',
        'set-backup-target', 'new-recovery-key', 'export-trust', 'log-bundle', 'prepare-uninstall', 'restore')
    # Windows-side work that must run as slateops-svc, because WSL distributions and .wslconfig
    # belong to the account that runs wsl.exe (kit design notes). Their paths come from the
    # administrator-only state file, never from the request.
    # W9: terminate-distro, unregister-distro (uninstall) and import-kept (reinstall with kept
    # data) also run as the account, because the distribution is registered for it.
    WindowsJobs = @('wslconfig', 'import-distro', 'wsl-facts', 'pipe-test', 'terminate-distro', 'unregister-distro', 'import-kept')
    # Plan 3.2 rule 3 and 6.1 (W8): the wizard's pipe \\.\pipe\SlateOps-<request ID> carries
    # the values below; they are never written to a Windows disk. pipe-test is the channel
    # self-test (plan F4d).
    # Input through the pipe: the SMTP password (smtp-test, set-email) and the answers (install,
    # plan 6.1). Output through the pipe: exactly the two jobs whose result holds the recovery
    # key (install, new-recovery-key; parent decision, TASK-0093 field recovery_key).
    PipeInputJobs  = @('smtp-test', 'set-email', 'install', 'pipe-test')
    # AC-W6 (DEC-0041): smtp-test answers with sent_to, the administrator's address (personal
    # data), so its output stays in memory too.
    PipeOutputJobs = @('install', 'new-recovery-key', 'pipe-test', 'smtp-test')
    PipeOutputCap = 1MB         # the install result with the CA certificate is about 4 KB
    PipeTimeoutMs = 60000
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
    # A pipe job's input never lies on a disk (W8-2): an input file for one is refused.
    $piped = $SlateOpsExec.PipeInputJobs -ccontains $job
    if ($piped -and ($bytes.Length -gt 0)) { return (Get-ExecRefusal 'input_on_disk') + @{ request_id = $requestId; job = $job } }
    if (($class -eq 'engine') -and (-not $piped) -and ($bytes.Length -eq 0)) { return (Get-ExecRefusal 'input_missing') + @{ request_id = $requestId; job = $job } }
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

function Write-InputBytes {
    # Writes bytes to the sink's stream in chunks of at most 1 MiB. .NET Framework (Windows
    # PowerShell 5.1) ignores ERROR_NO_DATA when the reader of a pipe is gone, so a write after
    # the process ended does not fail by itself: the sink checks the process before each chunk
    # and reports the early close as an IOException "input_closed" (a refusing receive closes
    # its input early; TASK-0083 carry). A sink without a process (tests) writes plainly.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Sink,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][byte[]]$Buffer,
        [int]$Count = -1
    )
    if ($Count -lt 0) { $Count = $Buffer.Length }
    $position = 0
    while ($position -lt $Count) {
        if ($Sink.Process -and $Sink.Process.HasExited) { throw (New-Object System.IO.IOException('input_closed')) }
        $size = [int][math]::Min(1MB, $Count - $position)
        $Sink.Stream.Write($Buffer, $position, $size)
        $position += $size
    }
    $Sink.Written = [long]$Sink.Written + $Count
}

function Write-TarMember {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Sink,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][long]$Size,
        [Parameter(Mandatory = $true)][scriptblock]$WriteBody
    )
    Write-InputBytes -Sink $Sink -Buffer (New-TarHeader -Name $Name -Size $Size)
    & $WriteBody $Sink
    $pad = (512 - ($Size % 512)) % 512
    if ($pad -gt 0) { Write-InputBytes -Sink $Sink -Buffer (New-Object byte[] $pad) }
}

function Write-ReceiveStream {
    # Writes the receive tar stream: request.json, then each part from the payload folder, then
    # the two end blocks. Part names are fixed; a part that is missing, not a regular file or a
    # reparse point stops the job before any byte is written.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Sink,
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
    Write-TarMember -Sink $Sink -Name 'request.json' -Size $RequestBytes.Length -WriteBody { param($target) Write-InputBytes -Sink $target -Buffer $RequestBytes }
    foreach ($part in $parts) {
        Write-TarMember -Sink $Sink -Name $part.name -Size $part.size -WriteBody {
            param($target)
            $file = [System.IO.File]::Open($part.path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
            try {
                if ($file.Length -ne $part.size) { throw 'A payload part changed while it was sent.' }
                $buffer = New-Object byte[] (1MB)
                while (($read = $file.Read($buffer, 0, $buffer.Length)) -gt 0) { Write-InputBytes -Sink $target -Buffer $buffer -Count $read }
            } finally { $file.Dispose() }
        }
    }
    Write-InputBytes -Sink $Sink -Buffer (New-Object byte[] 1024)
}

# ---------------------------------------------------------------------------
# Running a process with data on its raw standard input
# ---------------------------------------------------------------------------

function Start-ProcessWithoutPreamble {
    # .NET Framework's Process.Start wraps the redirected input in a StreamWriter with
    # Console.InputEncoding and sets AutoFlush, which writes that encoding's preamble at once.
    # With console code page 65001 that is a UTF-8 byte order mark (3 bytes) before the first
    # JSON byte, and the engine refuses the request (second Windows CI run). For the start only,
    # the console input encoding is UTF-8 without a preamble; setup refuses to start the process
    # when a preamble would still be written.
    param([Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process)
    $previous = $null
    try {
        $current = [Console]::InputEncoding
        if ($current.GetPreamble().Length -gt 0) {
            $previous = $current
            [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
        }
    } catch { $previous = $null }
    try {
        $encoding = $null
        try { $encoding = [Console]::InputEncoding } catch { $encoding = $null }
        if (($null -ne $encoding) -and ($encoding.GetPreamble().Length -gt 0)) { throw 'input_encoding_preamble' }
        [void]$Process.Start()
    } finally {
        if ($null -ne $previous) { try { [Console]::InputEncoding = $previous } catch { $null = $_ } }
    }
}

function Initialize-CappedCopyType {
    # A copy on a thread-pool task that keeps at most "cap" bytes and reads the rest of the
    # stream without keeping it, so the child never blocks on a full pipe and no file grows past
    # its cap (S91-8). Returns the number of bytes the stream gave. Windows PowerShell cannot
    # run a script block on a thread-pool thread, so this is C#.
    if ('SlateOpsSetup.CappedCopy' -as [type]) { return }
    $source = @'
using System;
using System.IO;
using System.Threading.Tasks;
namespace SlateOpsSetup
{
    public static class CappedCopy
    {
        public static Task<long> Start(Stream source, Stream target, long cap)
        {
            return Task.Run(() =>
            {
                byte[] buffer = new byte[81920];
                long total = 0;
                int read;
                while ((read = source.Read(buffer, 0, buffer.Length)) > 0)
                {
                    // W14-D5: each chunk reaches the file at once, so the wizard reads the
                    // engine's progress line while the job runs.
                    if (total < cap) { target.Write(buffer, 0, (int)Math.Min((long)read, cap - total)); target.Flush(); }
                    total += read;
                }
                target.Flush();
                return total;
            });
        }
    }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp
}

function Initialize-PipeBridgeType {
    # The service side of the secret channel (plan 3.2 rule 3, checks 1 to 3; 11.1 W8 cell).
    # Secret bytes move only inside this type, through .NET stream calls: never through the
    # PowerShell pipeline, script text, output or a file. Frame: 8 ASCII digits with the length,
    # then the bytes; one frame each way.
    if ('SlateOpsSetup.PipeBridge' -as [type]) { return }
    $source = @'
using System;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
namespace SlateOpsSetup
{
    public sealed class PipeBridge : IDisposable
    {
        const string Administrators = "S-1-5-32-544";
        NamedPipeClientStream pipe;
        int timeoutMs;
        public long InputBytes;
        public long OutputBytes;

        // Check 2, through the handle: the owner is Administrators, and every entry allows only
        // Administrators or this account. Returns null, or the reason (for the log).
        public static string TrustProblem(PipeSecurity security, string selfSid)
        {
            IdentityReference owner = security.GetOwner(typeof(SecurityIdentifier));
            if (owner == null || owner.Value != Administrators) { return "owner"; }
            AuthorizationRuleCollection rules = security.GetAccessRules(true, true, typeof(SecurityIdentifier));
            if (rules.Count == 0) { return "no_entries"; }
            foreach (PipeAccessRule rule in rules)
            {
                string sid = rule.IdentityReference.Value;
                if (rule.AccessControlType != AccessControlType.Allow) { return "deny_entry"; }
                if (sid != Administrators && sid != selfSid) { return "other_principal"; }
            }
            return null;
        }

        public static PipeBridge Open(string requestId, int timeoutMs)
        {
            Guid parsed;
            if (!Guid.TryParseExact(requestId, "D", out parsed)) { throw new IOException("pipe_name_invalid"); }
            // Only the rights the transfer needs: read, write, read the access list. (InOut would
            // ask for GENERIC_WRITE, which includes the right to create a pipe instance.)
            PipeAccessRights rights = PipeAccessRights.ReadData | PipeAccessRights.WriteData | PipeAccessRights.ReadPermissions | PipeAccessRights.Synchronize;
            NamedPipeClientStream client = new NamedPipeClientStream(".", "SlateOps-" + parsed.ToString("D"), rights, PipeOptions.Asynchronous, TokenImpersonationLevel.Identification, HandleInheritability.None);
            try { client.Connect(timeoutMs); }
            catch (TimeoutException) { client.Dispose(); throw new IOException("pipe_unavailable"); }
            string self = WindowsIdentity.GetCurrent().User.Value;
            if (TrustProblem(client.GetAccessControl(), self) != null) { client.Dispose(); throw new IOException("pipe_untrusted"); }
            PipeBridge bridge = new PipeBridge();
            bridge.pipe = client;
            bridge.timeoutMs = timeoutMs;
            return bridge;
        }

        void ReadExactly(byte[] buffer, int count)
        {
            int done = 0;
            while (done < count)
            {
                Task<int> read = pipe.ReadAsync(buffer, done, count - done);
                if (!read.Wait(timeoutMs)) { throw new IOException("pipe_timeout"); }
                if (read.Result == 0) { throw new IOException("pipe_closed"); }
                done += read.Result;
            }
        }

        byte[] ReadFrame(int limit)
        {
            byte[] header = new byte[8];
            ReadExactly(header, 8);
            int length = 0;
            foreach (byte b in header)
            {
                if (b < (byte)'0' || b > (byte)'9') { throw new IOException("pipe_frame_invalid"); }
                length = length * 10 + (b - (byte)'0');
            }
            if (length < 1 || length > limit) { throw new IOException("pipe_frame_invalid"); }
            byte[] data = new byte[length];
            ReadExactly(data, length);
            return data;
        }

        void WriteFrame(byte[] data, int count)
        {
            byte[] header = Encoding.ASCII.GetBytes(count.ToString("D8"));
            pipe.Write(header, 0, header.Length);
            pipe.Write(data, 0, count);
            pipe.Flush();
            pipe.WaitForPipeDrain();
            OutputBytes = count;
        }

        // The wizard's one input frame into the process's raw standard input.
        public long CopyInputTo(Stream target, int limit)
        {
            byte[] data = ReadFrame(limit);
            try { target.Write(data, 0, data.Length); target.Flush(); InputBytes = data.Length; }
            finally { Array.Clear(data, 0, data.Length); }
            return InputBytes;
        }

        // The process's whole standard output as the one output frame; the buffer is cleared.
        public long SendOutput(MemoryStream output)
        {
            byte[] data = output.GetBuffer();
            try { WriteFrame(data, (int)output.Length); }
            finally { Array.Clear(data, 0, data.Length); }
            return OutputBytes;
        }

        // pipe-test (plan F4d): the SHA-256 of the wizard's random value goes back.
        public string AnswerHash(int limit)
        {
            byte[] data = ReadFrame(limit);
            InputBytes = data.Length;
            string hex;
            using (SHA256 sha = SHA256.Create()) { hex = BitConverter.ToString(sha.ComputeHash(data)).Replace("-", "").ToLowerInvariant(); }
            Array.Clear(data, 0, data.Length);
            byte[] answer = Encoding.ASCII.GetBytes("{\"code\":\"pipe_ok\",\"sha256\":\"" + hex + "\"}");
            WriteFrame(answer, answer.Length);
            return hex;
        }

        // The safe code of the engine output, and whether it holds a recovery key; the value of
        // the key is never read out of the buffer.
        public static string SafeCode(MemoryStream output)
        {
            string text = Encoding.ASCII.GetString(output.GetBuffer(), 0, (int)Math.Min(output.Length, 65536L));
            Match match = Regex.Match(text, "\"code\":\"([a-z0-9_]{1,64})\"");
            return match.Success ? match.Groups[1].Value : "output_invalid";
        }

        public static bool HasRecoveryKey(MemoryStream output)
        {
            byte[] needle = Encoding.ASCII.GetBytes("\"recovery_key\":\"");
            byte[] data = output.GetBuffer();
            for (long i = 0; i + needle.Length <= output.Length; i++)
            {
                int j = 0;
                while (j < needle.Length && data[i + j] == needle[j]) { j++; }
                if (j == needle.Length) { return true; }
            }
            return false;
        }

        public void Dispose() { if (pipe != null) { pipe.Dispose(); pipe = null; } }
    }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp -ReferencedAssemblies @('System.Core')
}

function Invoke-ProcessWithInput {
    # Starts FilePath with fixed arguments, copies standard output and standard error into files
    # on thread-pool tasks with their caps applied while reading (so a large input cannot
    # deadlock on a full output pipe, and no file passes its cap), gives WriteInput a sink
    # (@{ Stream; Process; Written }) for the raw input stream (never the PowerShell pipeline;
    # Write-InputBytes writes to it), and waits. Only Write-InputBytes' "input_closed" (the
    # process ended before it read all input: a receive refusal, TASK-0083 carry) counts as
    # pipe_closed; any other error is thrown (P3-3).
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][scriptblock]$WriteInput,
        [string]$StdoutPath = '',
        [Parameter(Mandatory = $true)][string]$StderrPath,
        [long]$StdoutCap = $SlateOpsExec.StdoutCap,
        [long]$StderrCap = $SlateOpsExec.StderrCap,
        # A pipe job's output stays in memory (W8-5); StdoutPath is then not created.
        [System.IO.Stream]$StdoutStream = $null
    )
    foreach ($argument in $ArgumentList) {
        if ($argument -notmatch '^[A-Za-z0-9/._-]+$') { throw 'An argument holds a character that needs quoting.' }
    }
    Initialize-CappedCopyType
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
    if ($StdoutStream) { $outFile = $StdoutStream }
    else { $outFile = [System.IO.File]::Open($StdoutPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write) }
    # W14-D5: other processes may read standard error while the job runs (the wizard shows the
    # engine's progress lines, spec 7.6); nobody else may write it.
    $errFile = [System.IO.File]::Open($StderrPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    $pipeClosed = $false
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        Start-ProcessWithoutPreamble -Process $process
        $outTask = [SlateOpsSetup.CappedCopy]::Start($process.StandardOutput.BaseStream, $outFile, $StdoutCap)
        $errTask = [SlateOpsSetup.CappedCopy]::Start($process.StandardError.BaseStream, $errFile, $StderrCap)
        $inStream = $process.StandardInput.BaseStream
        $sink = @{ Stream = $inStream; Process = $process; Written = [long]0 }
        try {
            & $WriteInput $sink
            $inStream.Flush()
        } catch {
            $inner = $_.Exception
            while ($inner -and -not (($inner -is [System.IO.IOException]) -and ($inner.Message -eq 'input_closed'))) { $inner = $inner.InnerException }
            if ($inner) { $pipeClosed = $true } else { throw }
        } finally {
            # .NET Framework ignores a closed pipe on the final flush; nothing to report here.
            try { $inStream.Dispose() } catch { $null = $_ }
        }
        $process.WaitForExit()
        $stdoutTotal = $outTask.Result
        $stderrTotal = $errTask.Result
        $exitCode = $process.ExitCode
    } finally {
        $watch.Stop()
        if (-not $StdoutStream) { $outFile.Dispose() }
        $errFile.Dispose()
        $process.Dispose()
    }
    return @{ exit_code = $exitCode; pipe_closed = $pipeClosed; duration_ms = $watch.ElapsedMilliseconds; stdout_total = [long]$stdoutTotal; stderr_total = [long]$stderrTotal }
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
        # TASK-0097 AC-2 (Architect U-1): exec.ps1 builds the layout with no data root; the data
        # folder comes from the administrator-only state file, as for the Windows-side jobs.
        $state = Read-InstallState -Layout $Layout
        Set-LayoutDataRoot -Layout $Layout -DataRoot $state.data_root
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
    if (($SlateOpsExec.PipeInputJobs -ccontains $job) -or ($SlateOpsExec.PipeOutputJobs -ccontains $job)) { return Invoke-PipedEngineJob -Layout $Layout -Check $Check -WslPath $WslPath -Result $Result }
    $stdout = Join-Path $Layout.SvcOut ('{0}.stdout.json' -f $Check.request_id)
    $stderr = Join-Path $Layout.SvcOut ('{0}.stderr.txt' -f $Check.request_id)
    $arguments = Get-EngineArguments -Job $job
    Write-RunLog ('exec.{0}' -f $job) 'INFO' ('> {0} {1}' -f (Split-Path -Leaf $WslPath), ($arguments -join ' '))
    $inputBytes = $Check.input
    $payload = $Layout.Payload
    if ($job -eq 'receive') {
        $writer = { param($sink) Write-ReceiveStream -Sink $sink -RequestBytes $inputBytes -Version $version -PayloadDir $payload }
    } else {
        $writer = { param($sink) Write-InputBytes -Sink $sink -Buffer $inputBytes }
    }
    $env:WSL_UTF8 = '1'
    $run = Invoke-ProcessWithInput -FilePath $WslPath -ArgumentList $arguments -WriteInput $writer -StdoutPath $stdout -StderrPath $stderr
    $errBytes = Limit-ErrorFile -Path $stderr
    $outItem = Get-Item -LiteralPath $stdout -Force
    $Result.exit_code = $run.exit_code
    $Result.pipe_closed = [bool]$run.pipe_closed
    $Result.stdout_bytes = [long]$outItem.Length
    Write-RunLog ('exec.{0}' -f $job) 'INFO' ('  exit code {0}, {1} ms, stdout {2} bytes, stderr {3} bytes, input closed early {4}' -f $run.exit_code, $run.duration_ms, $outItem.Length, $errBytes, $run.pipe_closed)
    if (($run.stdout_total -gt $SlateOpsExec.StdoutCap) -or ($outItem.Length -gt $SlateOpsExec.StdoutCap)) {
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

function Invoke-PipedEngineJob {
    # A job with a pipe side (W8-2, W8-5). Input: the wizard's one frame goes to the engine's
    # standard input (PipeInputJobs), else the request's input file. Output: the engine's
    # standard output stays in memory and goes back as the one output frame (PipeOutputJobs);
    # the step log and the result hold only byte counts, the safe code and recovery_key_shown
    # (plan 10.1 item 3). Other output goes to its svc-out file as for every job.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Layout,
        [Parameter(Mandatory = $true)][hashtable]$Check,
        [Parameter(Mandatory = $true)][string]$WslPath,
        [Parameter(Mandatory = $true)][hashtable]$Result
    )
    $job = $Check.job
    $step = 'exec.{0}' -f $job
    $pipeIn = $SlateOpsExec.PipeInputJobs -ccontains $job
    $pipeOut = $SlateOpsExec.PipeOutputJobs -ccontains $job
    Initialize-PipeBridgeType
    try { $bridge = [SlateOpsSetup.PipeBridge]::Open($Check.request_id, $SlateOpsExec.PipeTimeoutMs) }
    catch {
        $code = Get-PipeErrorCode $_.Exception
        Write-RunLog $step 'FAIL' ('secret channel: {0}' -f $code)
        $Result.code = $code; $Result.message_key = ('exec.{0}' -f $code); $Result.exit_code = 3
        return $Result
    }
    $memory = New-Object System.IO.MemoryStream
    try {
        $stdout = Join-Path $Layout.SvcOut ('{0}.stdout.json' -f $Check.request_id)
        $stderr = Join-Path $Layout.SvcOut ('{0}.stderr.txt' -f $Check.request_id)
        $arguments = Get-EngineArguments -Job $job
        Write-RunLog $step 'INFO' ('> {0} {1} (secret channel: input {2}, output {3})' -f (Split-Path -Leaf $WslPath), ($arguments -join ' '), $pipeIn, $pipeOut)
        $limit = [int]$SlateOpsExec.InputLimit
        $inputBytes = $Check.input
        if ($pipeIn) { $writer = { param($sink) [void]$bridge.CopyInputTo($sink.Stream, $limit) } }
        else { $writer = { param($sink) Write-InputBytes -Sink $sink -Buffer $inputBytes } }
        $streams = @{ StdoutPath = $stdout }
        if ($pipeOut) { $streams = @{ StdoutStream = $memory; StdoutCap = $SlateOpsExec.PipeOutputCap } }
        $env:WSL_UTF8 = '1'
        try {
            $run = Invoke-ProcessWithInput -FilePath $WslPath -ArgumentList $arguments -WriteInput $writer -StderrPath $stderr @streams
        } catch {
            $code = Get-PipeErrorCode $_.Exception
            Write-RunLog $step 'FAIL' ('secret channel: {0}' -f $code)
            $Result.code = $code; $Result.message_key = ('exec.{0}' -f $code); $Result.exit_code = 3
            return $Result
        }
        $errBytes = Limit-ErrorFile -Path $stderr
        $Result.exit_code = $run.exit_code
        $Result.pipe_closed = [bool]$run.pipe_closed
        $Result.pipe_input_bytes = [long]$bridge.InputBytes
        if ($pipeOut) {
            if ($run.stdout_total -gt $SlateOpsExec.PipeOutputCap) {
                $Result.code = 'output_too_large'; $Result.message_key = 'exec.output_too_large'; $Result.exit_code = 3
                return $Result
            }
            $Result.code = [SlateOpsSetup.PipeBridge]::SafeCode($memory)
            $Result.message_key = ('{0}.{1}' -f $job, $Result.code)
            $Result.recovery_key_shown = [SlateOpsSetup.PipeBridge]::HasRecoveryKey($memory)
            try { [void]$bridge.SendOutput($memory) }
            catch { Write-RunLog $step 'WARN' ('secret channel: output not delivered ({0})' -f (Get-PipeErrorCode $_.Exception)) }
            $Result.pipe_output_bytes = [long]$bridge.OutputBytes
        } else {
            $outItem = Get-Item -LiteralPath $stdout -Force
            if ($outItem.Length -gt $SlateOpsExec.StdoutCap) {
                Remove-PathNoFollow -Path $stdout
                $Result.code = 'output_too_large'; $Result.message_key = 'exec.output_too_large'; $Result.exit_code = 3
                return $Result
            }
            $Result.stdout_file = Split-Path -Leaf $stdout
            $Result.stdout_bytes = [long]$outItem.Length
            $Result.stdout_sha256 = Get-FileSha256 -Path $stdout
            $engine = Get-EngineCode -Path $stdout
            $Result.code = $engine.code
            $Result.message_key = $engine.message_key
        }
        Write-RunLog $step 'INFO' ('  exit code {0}, {1} ms, pipe input {2} bytes, pipe output {3} bytes, stderr {4} bytes, recovery key shown {5}' -f $run.exit_code, $run.duration_ms, $bridge.InputBytes, $bridge.OutputBytes, $errBytes, ($Result['recovery_key_shown'] -eq $true))
        return $Result
    } finally {
        [Array]::Clear($memory.GetBuffer(), 0, $memory.GetBuffer().Length)
        $memory.Dispose()
        $bridge.Dispose()
    }
}

function Get-PipeErrorCode {
    # The safe code of a secret-channel error (the innermost IOException message of the bridge).
    param([Parameter(Mandatory = $true)][System.Exception]$Exception)
    $inner = $Exception
    while ($inner) {
        if (($inner -is [System.IO.IOException]) -and ($inner.Message -match '^pipe_[a-z_]{1,32}$')) { return $inner.Message }
        $inner = $inner.InnerException
    }
    return 'pipe_failed'
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
            $path = Join-Path (Get-UserProfilePath) '.wslconfig'
            $lines = Get-WslConfigText -VhdSizeGB $state.vhd_size_gb
            [System.IO.File]::WriteAllText($path, (($lines -join "`r`n") + "`r`n"), [System.Text.Encoding]::ASCII)
            foreach ($line in $lines) { Write-RunLog $step 'INFO' ('  {0}' -f $line) }
            $Result.code = 'written'
        }
        'import-distro' {
            $state = Read-InstallState -Layout $Layout
            Set-LayoutDataRoot -Layout $Layout -DataRoot $state.data_root
            $setup = Read-SetupVersion -Path (Join-Path $Layout.Scripts 'version.json')
            # S91-2: the data tree right before the read. N-2: this account cannot read the access
            # list of an administrator-only folder above the data folder, so the folders above are
            # checked on the administrator side (at selection and right before the copy); only
            # their trusted owners can change them after that.
            $own = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $problems = @(Get-TreeProblem -Tree $Layout.DataTree -ServiceSid $own)
            if ($problems.Count -gt 0) {
                foreach ($problem in $problems) { Write-RunLog $step 'FAIL' $problem }
                $Result.code = 'data_folder_parent_unsafe'; $Result.exit_code = 3; $Result.message_key = 'exec.data_folder_parent_unsafe'; return $Result
            }
            $list = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList @('--list', '--quiet') -NoThrow
            if (@($list.Output | Where-Object { $_.Trim() -eq $SlateOps.DistroName }).Count -gt 0) {
                $Result.code = 'already_imported'
            } else {
                $image = Join-Path $Layout.Payload $setup.linux_image_name
                $tar = Join-Path $Layout.Distro 'rootfs.tar'
                # S91-2: one handle on the image, shared for reading only (no write, no delete or
                # rename), held from the hash through the decompression, so the bytes unpacked are
                # the bytes hashed. The plain tar goes into distro, which only this account and
                # administrators can write. (A stream import with "-" would know the hash only
                # after WSL has registered the distribution.)
                $handle = [System.IO.File]::Open($image, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
                try {
                    $hash = Get-StreamSha256 -Stream $handle
                    Write-RunLog $step 'INFO' ('  SHA-256 of {0}: {1}' -f $setup.linux_image_name, $hash)
                    if ($hash -ne $setup.linux_image_sha256) { $Result.code = 'image_hash_mismatch'; $Result.exit_code = 3; $Result.message_key = 'exec.image_hash_mismatch'; return $Result }
                    [void]$handle.Seek(0, [System.IO.SeekOrigin]::Begin)
                    Expand-GzipStream -Source $handle -Destination $tar
                } finally { $handle.Dispose() }
                try {
                    $import = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList @('--import', $SlateOps.DistroName, $Layout.Distro, $tar, '--version', '2') -NoThrow
                } finally { Remove-PathNoFollow -Path $tar }
                if ($import.ExitCode -ne 0) { $Result.code = 'import_failed'; $Result.exit_code = 3; $Result.message_key = 'exec.import_failed'; return $Result }
                $Result.code = 'imported'
            }
        }
        'pipe-test' {
            # Plan F4d: the channel self-test before the first secret. The random value's
            # SHA-256 goes back; the value is never logged.
            Initialize-PipeBridgeType
            $bridge = $null
            try {
                $bridge = [SlateOpsSetup.PipeBridge]::Open($Check.request_id, $SlateOpsExec.PipeTimeoutMs)
                [void]$bridge.AnswerHash(4096)
                Write-RunLog $step 'INFO' ('  secret channel: input {0} bytes, output {1} bytes' -f $bridge.InputBytes, $bridge.OutputBytes)
                $Result.code = 'pipe_ok'
            } catch {
                $Result.code = Get-PipeErrorCode $_.Exception; $Result.exit_code = 3; $Result.message_key = ('exec.{0}' -f $Result.code)
                Write-RunLog $step 'FAIL' ('secret channel: {0}' -f $Result.code)
            } finally { if ($bridge) { $bridge.Dispose() } }
        }
        'terminate-distro' {
            # Uninstall (plan 9.1): the distribution stops before its disk moves.
            $run = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList @('--terminate', $SlateOps.DistroName) -NoThrow
            if ($run.ExitCode -eq 0) { $Result.code = 'terminated' } else { $Result.code = 'terminate_failed'; $Result.exit_code = 3; $Result.message_key = 'exec.terminate_failed' }
        }
        'unregister-distro' {
            # Uninstall (plan 9.1, F3): with "Keep my data" the disk is moved out of distro first.
            $run = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList @('--unregister', $SlateOps.DistroName) -NoThrow
            if ($run.ExitCode -eq 0) { $Result.code = 'unregistered' } else { $Result.code = 'unregister_failed'; $Result.exit_code = 3; $Result.message_key = 'exec.unregister_failed' }
        }
        'import-kept' {
            # Reinstall with kept data (plan 9.2 step 3): register the kept disk where it is. The
            # data tree is checked right before, as for import-distro.
            $state = Read-InstallState -Layout $Layout
            Set-LayoutDataRoot -Layout $Layout -DataRoot $state.data_root
            $own = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $problems = @(Get-TreeProblem -Tree $Layout.DataTree -ServiceSid $own)
            if ($problems.Count -gt 0) {
                foreach ($problem in $problems) { Write-RunLog $step 'FAIL' $problem }
                $Result.code = 'data_folder_parent_unsafe'; $Result.exit_code = 3; $Result.message_key = 'exec.data_folder_parent_unsafe'; return $Result
            }
            # W9 review item 1: a resume after this step finds the distribution registered, as
            # import-distro does.
            $list = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList @('--list', '--quiet') -NoThrow
            if (@($list.Output | Where-Object { $_.Trim() -eq $SlateOps.DistroName }).Count -gt 0) {
                $Result.code = 'already_imported'
            } else {
                $disk = Join-Path $Layout.Distro 'ext4.vhdx'
                $run = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList @('--import-in-place', $SlateOps.DistroName, $disk) -NoThrow
                if ($run.ExitCode -eq 0) { $Result.code = 'imported' } else { $Result.code = 'import_failed'; $Result.exit_code = 3; $Result.message_key = 'exec.import_failed' }
            }
        }
        'wsl-facts' {
            foreach ($arguments in @(@('--version'), @('--status'), @('--list', '--verbose'))) {
                $null = Invoke-Logged -Step $step -FilePath $WslPath -ArgumentList $arguments -NoThrow
            }
            $config = Join-Path (Get-UserProfilePath) '.wslconfig'
            if (Test-Path -LiteralPath $config) {
                foreach ($line in (Get-Content -LiteralPath $config)) { Write-RunLog $step 'INFO' ('  .wslconfig: {0}' -f $line) }
            } else { Write-RunLog $step 'WARN' '  .wslconfig is missing' }
            $Result.code = 'recorded'
        }
    }
    if (-not $Result.message_key -or ($Result.message_key -like 'exec.accepted')) { $Result.message_key = ('exec.{0}.{1}' -f $Check.job, $Result.code) }
    if ($Result.exit_code -eq 2 -and ($Result.code -in @('written', 'already_imported', 'imported', 'recorded', 'pipe_ok', 'terminated', 'unregistered'))) { $Result.exit_code = 0 }
    return $Result
}

function Get-StreamSha256 {
    param([Parameter(Mandatory = $true)][System.IO.Stream]$Stream)
    $sha = New-Object System.Security.Cryptography.SHA256Managed
    try { return (-join ($sha.ComputeHash($Stream) | ForEach-Object { $_.ToString('x2') })) } finally { $sha.Dispose() }
}

function Expand-GzipStream {
    # Kit step: wsl --import gets a plain tar. The caller owns the source handle.
    param([Parameter(Mandatory = $true)][System.IO.Stream]$Source, [Parameter(Mandatory = $true)][string]$Destination)
    $gzip = New-Object System.IO.Compression.GZipStream($Source, [System.IO.Compression.CompressionMode]::Decompress, $true)
    $out = [System.IO.File]::Open($Destination, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try { $gzip.CopyTo($out, 1MB) } finally { $out.Dispose(); $gzip.Dispose() }
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
        # W8: the wizard makes the request ID of a pipe job, because it creates the pipe
        # \\.\pipe\SlateOps-<request ID> before the job starts (plan 3.2 check 1).
        [string]$RequestId = '',
        [switch]$NoStart
    )
    if (($SlateOpsExec.EngineJobs -cnotcontains $Job) -and ($SlateOpsExec.WindowsJobs -cnotcontains $Job)) { throw 'Not an allow-listed job.' }
    if (-not (Test-RunId $RunId)) { throw 'Not a run ID.' }
    if (-not $NoStart) {
        $task = Get-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.ExecTaskName -ErrorAction Stop
        if ($task.State -eq 'Running') { throw 'exec_busy' }
    }
    # W14-D8: PowerShell variable names ignore case, so a local $requestId would overwrite the
    # parameter $RequestId and every job would run under a new random ID that the wizard never
    # sees (and its pipe would never connect). The local name differs from every parameter.
    $submitId = [guid]::NewGuid().ToString('D')
    if ($RequestId) {
        $parsed = [guid]::Empty
        if (-not [guid]::TryParseExact($RequestId, 'D', [ref]$parsed)) { throw 'request_id_invalid' }
        $submitId = $parsed.ToString('D')
    }
    foreach ($path in @($Layout.RequestFile, $Layout.InputFile)) { if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path } }
    [System.IO.File]::WriteAllBytes($Layout.InputFile, $InputBytes)
    Write-JsonFile -Path $Layout.RequestFile -Value ([ordered]@{ request_id = $submitId; job = $Job; run_id = $RunId })
    Write-RunLog ('exec.submit.{0}' -f $Job) 'INFO' ('request {0}, input {1} bytes' -f $submitId, $InputBytes.Length)
    if (-not $NoStart) { Start-ScheduledTask -TaskPath $SlateOps.TaskPath -TaskName $SlateOps.ExecTaskName }
    return $submitId
}

function Test-TaskLogonFailure {
    # Plan 10.7 "The service account cannot sign in": the task's last result is 0x8007052F
    # (logon failure: user name or password) or 0x80070569 (logon type not granted).
    param([long]$LastResult)
    # Decimal: PowerShell reads 0x8007052F as a negative Int32. The mask turns either form of
    # the task result into the unsigned value.
    return @([long]2147943727, [long]2147943785) -contains ($LastResult -band 4294967295L)
}

function Get-ExecResult {
    # Returns the result of the request, or $null while it has none. The service account writes
    # svc-out; this side reads it as data and never follows a link there.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$RequestId)
    if (-not (Test-Path -LiteralPath $Layout.ResultFile -PathType Leaf)) { return $null }
    try { $value = Read-JsonFile -Path $Layout.ResultFile } catch { return $null }
    if (-not ($value -is [System.Collections.IDictionary])) { return $null }
    if ([string](Get-DictValue $value 'request_id') -cne $RequestId) { return $null }
    # S91-3: the request is spent once its result is read; a later start of the task finds none.
    foreach ($path in @($Layout.RequestFile, $Layout.InputFile)) { if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path } }
    return $value
}

function Remove-EngineOutput {
    # AC-W6: the engine's status output names the administrator's address (admin_email); once
    # the safe values are read, the output file leaves svc-out, so no log or report holds it.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Result)
    $name = [string](Get-DictValue $Result 'stdout_file')
    if ($name -notmatch '^[0-9a-f-]{36}\.stdout\.json$') { return }
    $path = Join-Path $Layout.SvcOut $name
    if (Test-Path -LiteralPath $path) { Remove-PathNoFollow -Path $path }
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
    # S91-8: the cap again on this side, before the file is read into memory.
    if ($item.Length -gt $SlateOpsExec.StdoutCap) { throw 'output_too_large' }
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
