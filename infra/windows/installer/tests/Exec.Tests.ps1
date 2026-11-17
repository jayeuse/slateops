# Exec.Tests.ps1 - AC-2: Exec runs one allow-listed job, refuses everything else, and writes data
# only to the raw standard input of a fixed command line. A compiled stand-in program replaces
# wsl.exe: it reports its arguments and the SHA-256 of the bytes it read, or closes its input at
# once like a refusing receive.

$standInSource = @'
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
public static class StandIn
{
    static void Emit(string json)
    {
        byte[] data = Encoding.ASCII.GetBytes(json + "\n");
        Stream output = Console.OpenStandardOutput();
        output.Write(data, 0, data.Length);
        output.Flush();
    }
    public static int Main(string[] args)
    {
        string mode = Environment.GetEnvironmentVariable("SLATEOPS_STANDIN_MODE");
        if (mode == "close")
        {
            Console.OpenStandardInput().Close();
            Emit("{\"code\":\"payload_too_large\",\"message_key\":\"receive.payload_too_large\"}");
            return 2;
        }
        if (mode == "big")
        {
            Stream big = Console.OpenStandardOutput();
            byte[] block = new byte[1024 * 1024];
            for (int i = 0; i < block.Length; i++) { block[i] = (byte)'x'; }
            for (int i = 0; i < 3; i++) { big.Write(block, 0, block.Length); }
            big.Flush();
            return 0;
        }
        Stream input = Console.OpenStandardInput();
        SHA256 sha = SHA256.Create();
        byte[] buffer = new byte[65536];
        long total = 0;
        int read;
        while ((read = input.Read(buffer, 0, buffer.Length)) > 0) { sha.TransformBlock(buffer, 0, read, null, 0); total += read; }
        sha.TransformFinalBlock(buffer, 0, 0);
        string hex = BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
        if (mode == "key")
        {
            // W8: an install result with a recovery key, as the engine writes it (sorted keys).
            Emit("{\"bytes\":" + total + ",\"code\":\"installed\",\"recovery_key\":\"" + Environment.GetEnvironmentVariable("SLATEOPS_STANDIN_KEY") + "\",\"sha256\":\"" + hex + "\"}");
            return 0;
        }
        Emit("{\"code\":\"ok\",\"args\":\"" + string.Join(" ", args) + "\",\"bytes\":" + total + ",\"sha256\":\"" + hex + "\"}");
        return 0;
    }
}
'@
$script:StandIn = Join-Path (New-TestDirectory 'standin') 'standin.exe'
Add-Type -TypeDefinition $standInSource -Language CSharp -OutputAssembly $script:StandIn -OutputType ConsoleApplication

$script:RunId = 'install-20261117T032000Z-abc123'

function New-ExecLayout {
    param([Parameter(Mandatory = $true)][string]$Name)
    $root = New-TestDirectory $Name
    $layout = New-SlateOpsLayout -StateRoot (Join-Path $root 'ProgramData\SlateOps') -DataRoot (Join-Path $root 'Data\SlateOps')
    foreach ($path in @($layout.Requests, $layout.SvcOut, $layout.Payload, $layout.Scripts, $layout.State)) { [void][System.IO.Directory]::CreateDirectory($path) }
    return $layout
}

function Set-ExecRequest {
    param([hashtable]$Layout, [string]$RequestText, [byte[]]$InputBytes)
    [System.IO.File]::WriteAllText($Layout.RequestFile, $RequestText, (New-Object System.Text.UTF8Encoding($false)))
    if ($null -ne $InputBytes) { [System.IO.File]::WriteAllBytes($Layout.InputFile, $InputBytes) }
}

function Get-RequestText {
    param([string]$Job, [string]$RequestId = '0b9a1c64-6c2e-4f55-9b1e-2f0d3c7a8e11', [string]$RunId = $script:RunId)
    return ('{{"request_id":"{0}","job":"{1}","run_id":"{2}"}}' -f $RequestId, $Job, $RunId)
}

$script:StatusInput = [System.Text.Encoding]::UTF8.GetBytes('{"run_id":"install-20261117T032000Z-abc123","windows_part_version":"0.2.0","wsl_version":"3.0.3.0"}')

Test-Case 'AC-2 the request check accepts one allow-listed job and refuses the rest' {
    Assert-Equal 'accepted' (Test-ExecRequest -RequestText (Get-RequestText 'status') -InputBytes $script:StatusInput).code
    Assert-Equal 'accepted' (Test-ExecRequest -RequestText (Get-RequestText 'wsl-facts') -InputBytes $null).code
    $cases = [ordered]@{
        'unknown job'          = @((Get-RequestText 'shell'), 'job_unknown')
        'two job names'        = @((Get-RequestText 'status install'), 'job_unknown')
        'upper case'           = @((Get-RequestText 'STATUS'), 'job_unknown')
        'internal worker'      = @((Get-RequestText '_prefetch-worker'), 'job_unknown')
        'job list'             = @('{"request_id":"0b9a1c64-6c2e-4f55-9b1e-2f0d3c7a8e11","job":["status","install"],"run_id":"install-20261117T032000Z-abc123"}', 'job_unknown')
        'extra key'            = @('{"request_id":"0b9a1c64-6c2e-4f55-9b1e-2f0d3c7a8e11","job":"status","run_id":"install-20261117T032000Z-abc123","command":"cmd"}', 'request_invalid')
        'request id not GUID'  = @((Get-RequestText -Job 'status' -RequestId '..\..\x'), 'request_invalid')
        'run id not valid'     = @((Get-RequestText -Job 'status' -RunId 'check-20261117T032000Z-abc123'), 'run_id_invalid')
        'not JSON'             = @('status', 'request_invalid')
        'empty'                = @('', 'request_missing')
    }
    foreach ($name in $cases.Keys) {
        Assert-Equal $cases[$name][1] (Test-ExecRequest -RequestText $cases[$name][0] -InputBytes $script:StatusInput).code $name
    }
    Assert-Equal 'input_missing' (Test-ExecRequest -RequestText (Get-RequestText 'status') -InputBytes $null).code
    Assert-Equal 'input_too_large' (Test-ExecRequest -RequestText (Get-RequestText 'status') -InputBytes (New-Object byte[] 65537)).code
}

Test-Case 'AC-2 the allow-list is the plan 6.2 list plus resend-invitation, and the Windows-side jobs with the W8 pipe-test' {
    # Ordinal order (code points): "-" (0x2D) sorts before letters.
    Assert-Equal @('export-trust', 'install', 'log-bundle', 'new-recovery-key', 'prefetch', 'prepare', 'prepare-uninstall', 'receive', 'resend-invitation',
        'restore', 'set-backup-target', 'set-email', 'smtp-test', 'status', 'update') (Get-OrdinalSorted $SlateOpsExec.EngineJobs)
    Assert-Equal @('import-distro', 'import-kept', 'pipe-test', 'terminate-distro', 'unregister-distro', 'wsl-facts', 'wslconfig') (Get-OrdinalSorted $SlateOpsExec.WindowsJobs)
}

Test-Case 'AC-2 an engine job has one fixed command line with no shell' {
    Assert-Equal @('-d', 'SlateOps', '-u', 'root', '--exec', '/usr/local/bin/slateops-engine', 'status') (Get-EngineArguments -Job 'status')
    Assert-Throws { Get-EngineArguments -Job 'wslconfig' } 'Not an allow-listed*'
}

Test-Case 'AC-2 the tar header is a ustar header that Python tarfile reads (checksum 010323)' {
    $header = New-TarHeader -Name 'request.json' -Size 5
    $ascii = [System.Text.Encoding]::ASCII
    Assert-Equal 512 $header.Length
    Assert-Equal 'request.json' ($ascii.GetString($header, 0, 12))
    Assert-Equal "00000000005`0" ($ascii.GetString($header, 124, 12))
    Assert-Equal "010323`0 " ($ascii.GetString($header, 148, 8))
    Assert-Equal "ustar`000" ($ascii.GetString($header, 257, 8))
    Assert-Throws { New-TarHeader -Name '../etc/passwd' -Size 1 } 'Not a valid member name.'
}

Test-Case 'AC-2 the receive stream holds request.json and the five fixed parts, padded, with two end blocks' {
    $payload = New-TestDirectory 'receive-stream'
    $sizes = @(10, 20, 30, 40, 50)
    $names = @(Get-ReceivePartNames -Version '0.2.0')
    for ($i = 0; $i -lt 5; $i++) { [System.IO.File]::WriteAllBytes((Join-Path $payload $names[$i]), (New-Object byte[] $sizes[$i])) }
    $memory = New-Object System.IO.MemoryStream
    $sink = @{ Stream = $memory; Process = $null; Written = [long]0 }
    Write-ReceiveStream -Sink $sink -RequestBytes ([System.Text.Encoding]::ASCII.GetBytes('hello')) -Version '0.2.0' -PayloadDir $payload
    Assert-Equal 7168 $sink.Written
    $bytes = $memory.ToArray()
    Assert-Equal 7168 $bytes.Length
    $ascii = [System.Text.Encoding]::ASCII
    Assert-Equal 'release-manifest.json' ($ascii.GetString($bytes, 1024, 21))
    Assert-Equal 'slateops-caddy-0.2.0-amd64.oci.tar' ($ascii.GetString($bytes, 5120, 34))
}

Test-Case 'AC-2 the receive input must name the run ID of the request and a release version' {
    $good = [System.Text.Encoding]::UTF8.GetBytes('{"run_id":"install-20261117T032000Z-abc123","setup_version":"0.2.0-rc.3"}')
    Assert-Equal '0.2.0-rc.3' (Test-ReceiveInput -InputBytes $good -RunId $script:RunId)
    Assert-Equal $null (Test-ReceiveInput -InputBytes $good -RunId 'install-20261117T032000Z-zzz999')
    $path = [System.Text.Encoding]::UTF8.GetBytes('{"run_id":"install-20261117T032000Z-abc123","setup_version":"../../x"}')
    Assert-Equal $null (Test-ReceiveInput -InputBytes $path -RunId $script:RunId)
}

Test-Case 'AC-2 an engine job gets its input bytes on standard input and nothing on the command line' {
    $layout = New-ExecLayout 'exec-status'
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText 'status') -InputBytes $script:StatusInput
    $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn
    Assert-Equal 'ok' $result.code
    Assert-Equal 0 $result.exit_code
    $output = Read-EngineOutput -Layout $layout -Result (Read-JsonFile -Path $layout.ResultFile)
    Assert-Equal '-d SlateOps -u root --exec /usr/local/bin/slateops-engine status' $output['args']
    Assert-Equal 99 $output['bytes']
    Assert-Equal '48c09f216dd9c823a6e5785d243dd13445734a950889ad8bbd917b8003163406' $output['sha256']
}

Test-Case 'AC-2 an unknown job is refused before any program starts' {
    $layout = New-ExecLayout 'exec-unknown'
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText 'powershell') -InputBytes $script:StatusInput
    $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn
    Assert-Equal 'job_unknown exec.job_unknown 2' ('{0} {1} {2}' -f $result.code, $result.message_key, $result.exit_code)
    Assert-Equal 0 @(Get-ChildItem -LiteralPath $layout.SvcOut -Filter '*.stdout.json').Count
    Assert-Equal 'job_unknown' (Read-JsonFile -Path $layout.ResultFile)['code']
}

Test-Case 'AC-2 receive streams the whole payload through the raw input stream' {
    $layout = New-ExecLayout 'exec-receive'
    $names = @(Get-ReceivePartNames -Version '0.2.0')
    foreach ($name in $names) { [System.IO.File]::WriteAllBytes((Join-Path $layout.Payload $name), (New-Object byte[] 1000)) }
    $request = [System.Text.Encoding]::UTF8.GetBytes('{"run_id":"install-20261117T032000Z-abc123","setup_version":"0.2.0"}')
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText 'receive') -InputBytes $request
    $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn
    Assert-Equal 'ok' $result.code
    Assert-Equal $false $result.pipe_closed
    $output = Read-EngineOutput -Layout $layout -Result (Read-JsonFile -Path $layout.ResultFile)
    Assert-Equal 9728 $output['bytes'] '512+512 request, 5 x (512+1024), 1024 end'
}

Test-Case 'AC-2 a receive that closes its input early is a refusal, with the engine code' {
    $layout = New-ExecLayout 'exec-receive-closed'
    $names = @(Get-ReceivePartNames -Version '0.2.0')
    foreach ($name in $names) { [System.IO.File]::WriteAllBytes((Join-Path $layout.Payload $name), (New-Object byte[] (4MB))) }
    $request = [System.Text.Encoding]::UTF8.GetBytes('{"run_id":"install-20261117T032000Z-abc123","setup_version":"0.2.0"}')
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText 'receive') -InputBytes $request
    $env:SLATEOPS_STANDIN_MODE = 'close'
    try { $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn } finally { Remove-Item Env:\SLATEOPS_STANDIN_MODE }
    Assert-Equal $true $result.pipe_closed
    Assert-Equal 'payload_too_large receive.payload_too_large 2' ('{0} {1} {2}' -f $result.code, $result.message_key, $result.exit_code)
}

Test-Case 'AC-2 receive with a missing part stops before the engine starts' {
    $layout = New-ExecLayout 'exec-receive-missing'
    $request = [System.Text.Encoding]::UTF8.GetBytes('{"run_id":"install-20261117T032000Z-abc123","setup_version":"0.2.0"}')
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText 'receive') -InputBytes $request
    $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn
    Assert-Equal 'payload_part_missing' $result.code
    Assert-Equal 0 @(Get-ChildItem -LiteralPath $layout.SvcOut -Filter '*.stdout.json').Count
}

Test-Case 'AC-2 the administrator side refuses an output file that changed after Exec measured it' {
    $layout = New-ExecLayout 'exec-changed'
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText 'status') -InputBytes $script:StatusInput
    $null = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn
    $result = Read-JsonFile -Path $layout.ResultFile
    [System.IO.File]::AppendAllText((Join-Path $layout.SvcOut $result['stdout_file']), ' ')
    Assert-Throws { Read-EngineOutput -Layout $layout -Result $result } 'output_changed'
}

Test-Case 'AC-2 a JSON text above the 2 MB limit of Windows PowerShell 5.1 parses' {
    $text = '{"code":"ok","bundle_base64":"' + ('A' * (3MB)) + '"}'
    $value = ConvertFrom-JsonUnlimited $text
    Assert-Equal 3145728 $value['bundle_base64'].Length
}

Test-Case 'AC-2 the log bundle is stored as one opaque file only when its size and SHA-256 match' {
    $dir = New-TestDirectory 'bundle'
    $output = @{ code = 'ok'; bundle_base64 = 'YWJj'; bundle_size = 3; bundle_sha256 = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad' }
    $saved = Save-LogBundle -Output $output -DestinationPath (Join-Path $dir 'linux.tar.gz')
    Assert-Equal 3 $saved.bytes
    Assert-Equal 'abc' ([System.IO.File]::ReadAllText((Join-Path $dir 'linux.tar.gz')))
    $wrong = @{ code = 'ok'; bundle_base64 = 'YWJj'; bundle_size = 3; bundle_sha256 = ('0' * 64) }
    Assert-Throws { Save-LogBundle -Output $wrong -DestinationPath (Join-Path $dir 'other.tar.gz') } 'bundle_invalid'
    Assert-Equal $false (Test-Path -LiteralPath (Join-Path $dir 'other.tar.gz'))
}

Test-Case 'AC-2 the result serializer unwraps cmdlet output, flattens a PSCustomObject and refuses other objects' {
    # Windows PowerShell 5.1's JavaScriptSerializer stops on a PSObject-wrapped value with a
    # circular reference (first Windows CI run); Split-Path returns such a wrapped string.
    $wrapped = [ordered]@{ stdout_file = (Split-Path -Leaf 'C:\x\0b9a1c64-6c2e-4f55-9b1e-2f0d3c7a8e11.stdout.json'); bytes = [long]99 }
    Assert-Equal '{"stdout_file":"0b9a1c64-6c2e-4f55-9b1e-2f0d3c7a8e11.stdout.json","bytes":99}' (ConvertTo-JsonText $wrapped)
    $custom = [ordered]@{ item = [pscustomobject]@{ name = 'wsl'; version = [version]'3.0.3.0' }; list = @('a', (Split-Path -Leaf 'C:\b')) }
    Assert-Equal '{"item":{"name":"wsl","version":"3.0.3.0"},"list":["a","b"]}' (ConvertTo-JsonText $custom)
    Assert-Throws { ConvertTo-JsonText @{ file = (Get-Item -LiteralPath $env:SystemRoot) } } 'json_unsupported_type'
}

Test-Case 'AC-2 the request key check sorts by code points, not by culture' {
    Assert-Equal @('import-distro', 'wsl-facts', 'wslconfig') (Get-OrdinalSorted @('wslconfig', 'wsl-facts', 'import-distro'))
    Assert-Equal 'accepted' (Test-ExecRequest -RequestText '{"run_id":"install-20261117T032000Z-abc123","job":"wsl-facts","request_id":"0b9a1c64-6c2e-4f55-9b1e-2f0d3c7a8e11"}' -InputBytes $null).code
}

Test-Case 'AC-2 S91-8 standard output stops at its cap while it is read, and the total is reported' {
    $dir = New-TestDirectory 's91-8-cap'
    $env:SLATEOPS_STANDIN_MODE = 'big'
    try {
        $run = Invoke-ProcessWithInput -FilePath $script:StandIn -ArgumentList @('status') -WriteInput { param($sink) $null = $sink } `
            -StdoutPath (Join-Path $dir 'out.json') -StderrPath (Join-Path $dir 'err.txt') -StdoutCap 1048576
    } finally { Remove-Item Env:\SLATEOPS_STANDIN_MODE }
    Assert-Equal 3145728 $run.stdout_total
    Assert-Equal 1048576 (Get-Item -LiteralPath (Join-Path $dir 'out.json')).Length
}

Test-Case 'AC-2 P3-3 only an early end of the process counts as a closed input; another IO error is thrown' {
    $dir = New-TestDirectory 'p3-3-io'
    Assert-Throws {
        $null = Invoke-ProcessWithInput -FilePath $script:StandIn -ArgumentList @('status') -WriteInput { param($sink) throw (New-Object System.IO.IOException('disk_failed')) } `
            -StdoutPath (Join-Path $dir 'out.json') -StderrPath (Join-Path $dir 'err.txt')
    } '*disk_failed*'
}

Test-Case 'AC-2 S91-3 the request and its input are removed once the result is read' {
    $layout = New-ExecLayout 's91-3-spent'
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText 'status') -InputBytes $script:StatusInput
    $null = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn
    $result = Get-ExecResult -Layout $layout -RequestId '0b9a1c64-6c2e-4f55-9b1e-2f0d3c7a8e11'
    Assert-Equal 'ok' (Get-DictValue $result 'code')
    Assert-Equal $false (Test-Path -LiteralPath $layout.RequestFile)
    Assert-Equal $false (Test-Path -LiteralPath $layout.InputFile)
}

Test-Case 'AC-2 P2-2 a helper result file starts with the code, whatever order the result had' {
    $result = @{ values = @{ verdict = 'ready' }; message_key = 'check.verdict.ready'; code = 'ready' }
    $text = ConvertTo-HelperResultText -Result $result -Action 'check' -RunId 'install-20261117T032000Z-abc123'
    Assert-True ($text.StartsWith('{"code":"ready","message_key":"check.verdict.ready",')) $text
}

