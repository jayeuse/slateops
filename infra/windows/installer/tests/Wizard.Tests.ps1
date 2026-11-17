# Wizard.Tests.ps1 - the W8 criteria that a Windows runner can prove (TASK-0094): the secret
# channel's service side (W8-2, W8-5, plan 3.2 checks 1 to 3), Save report (W8-6), the first
# screen (spec 4.1), the backup target rule, and the W7 re-check fixes N-1 and N-2. The pages
# themselves run only in the setup program (W14). Uses the stand-in program of Exec.Tests.ps1.

$pipeServerSource = @'
using System;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Threading.Tasks;
public static class TestPipeServer
{
    // The wizard's side, as the setup program builds it: one instance, first instance, owner
    // Administrators, the given principals only. Writes one input frame (unless input is
    // null) and reads one output frame (unless readOutput is false).
    public static Task<string> Start(string name, string[] sids, string input, bool readOutput)
    {
        PipeSecurity security = new PipeSecurity();
        security.SetOwner(new SecurityIdentifier("S-1-5-32-544"));
        foreach (string sid in sids)
        {
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(sid), PipeAccessRights.ReadWrite | PipeAccessRights.Synchronize, AccessControlType.Allow));
        }
        NamedPipeServerStream server = new NamedPipeServerStream(name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.WriteThrough, 65536, 65536, security);
        return Task.Run(() =>
        {
            try
            {
                Task wait = server.WaitForConnectionAsync();
                if (!wait.Wait(60000)) { return "no_client"; }
                if (input != null)
                {
                    byte[] data = Encoding.ASCII.GetBytes(input);
                    byte[] header = Encoding.ASCII.GetBytes(data.Length.ToString("D8"));
                    server.Write(header, 0, header.Length);
                    server.Write(data, 0, data.Length);
                    server.Flush();
                }
                if (!readOutput) { return ""; }
                byte[] head = new byte[8];
                int got = 0;
                while (got < 8) { int n = server.Read(head, got, 8 - got); if (n == 0) { return "closed"; } got += n; }
                int length = int.Parse(Encoding.ASCII.GetString(head));
                byte[] body = new byte[length];
                got = 0;
                while (got < length) { int n = server.Read(body, got, length - got); if (n == 0) { return "closed"; } got += n; }
                return Encoding.ASCII.GetString(body);
            }
            finally { server.Dispose(); }
        });
    }
}
'@
Add-Type -TypeDefinition $pipeServerSource -Language CSharp -ReferencedAssemblies @('System.Core')

$script:SelfSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$script:PipeRequestId = '5f1c2a9e-3b7d-4c60-8e21-7a4b9d0c6e35'
# Known values that must never reach a file (plan 10.6 item 6).
$script:SeedPassword = 'W8-seeded-Pa55word-7c1d'
# Generated per run, so no secret-shaped literal sits in the repository (secret scan).
$script:SeedAlphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'  # base32, the engine's key format
$script:SeedKey = (1..8 | ForEach-Object { -join (1..4 | ForEach-Object { $script:SeedAlphabet[(Get-Random -Maximum $script:SeedAlphabet.Length)] }) }) -join '-'
$script:SeedPemBody = 'MIIE' + (-join (1..28 | ForEach-Object { 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'[(Get-Random -Maximum 62)] }))
$script:PemKind = 'PRIVATE' + ' KEY'

function Get-TreeText {
    # Every file below a folder, as one text, so a test can look for a seeded value anywhere.
    param([Parameter(Mandatory = $true)][string]$Root)
    $all = New-Object System.Text.StringBuilder
    foreach ($file in @(Get-ChildItem -LiteralPath $Root -Recurse -Force -File)) {
        [void]$all.Append([System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($file.FullName)))
    }
    return $all.ToString()
}

Test-Case 'W8-2 W8-5 a pipe job takes its input from the pipe, gives its output back through it, and writes neither to disk' {
    $layout = New-ExecLayout 'w8-pipe'
    $logDir = New-TestDirectory 'w8-pipe-logs'
    Start-RunLog -RunId $script:RunId -Directory $logDir -NoConsole
    $answers = '{"answers":{"admin_email":"maria@example.com"},"password":"' + $script:SeedPassword + '","run_id":"' + $script:RunId + '"}'
    $server = [TestPipeServer]::Start(('SlateOps-{0}' -f $script:PipeRequestId), @('S-1-5-32-544', $script:SelfSid), $answers, $true)
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText -Job 'install' -RequestId $script:PipeRequestId) -InputBytes $null
    $env:SLATEOPS_STANDIN_MODE = 'key'
    $env:SLATEOPS_STANDIN_KEY = $script:SeedKey
    try { $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn }
    finally { Remove-Item Env:\SLATEOPS_STANDIN_MODE; Remove-Item Env:\SLATEOPS_STANDIN_KEY }
    $output = $server.Result
    $sha = New-Object System.Security.Cryptography.SHA256Managed
    $expected = -join ($sha.ComputeHash([System.Text.Encoding]::ASCII.GetBytes($answers)) | ForEach-Object { $_.ToString('x2') })
    Assert-True ($output.Contains('"recovery_key":"' + $script:SeedKey + '"')) 'the key reaches the wizard through the pipe'
    Assert-True ($output.Contains('"sha256":"' + $expected + '"')) 'the engine read exactly the bytes the wizard sent'
    Assert-Equal 'installed' $result.code
    Assert-Equal $true $result.recovery_key_shown
    Assert-Equal ([long]$answers.Length) $result.pipe_input_bytes
    Assert-Equal '' $result.stdout_file 'no output file for a pipe job'
    $disk = (Get-TreeText -Root (Split-Path -Parent $layout.StateRoot)) + (Get-TreeText -Root $logDir)
    Assert-True (-not $disk.Contains($script:SeedPassword)) 'the password is on no Windows disk'
    Assert-True (-not $disk.Contains($script:SeedKey)) 'the recovery key is on no Windows disk'
    Assert-True ($disk.Contains('"recovery_key_shown":true')) 'the result file holds recovery_key_shown'
}

Test-Case 'W8-2 3.2 check 2 Exec refuses a pipe whose access list allows another principal, before it reads or runs anything' {
    $layout = New-ExecLayout 'w8-pipe-untrusted'
    $id = '6a2d3b0f-4c8e-4d71-9f32-8b5c0e1d7f46'
    $server = [TestPipeServer]::Start(('SlateOps-{0}' -f $id), @('S-1-5-32-544', $script:SelfSid, 'S-1-1-0'), $null, $false)
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText -Job 'smtp-test' -RequestId $id) -InputBytes $null
    $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn
    # Exec closes an untrusted pipe without reading it, so the server's write may fail with a
    # broken pipe; only Exec's answer matters here.
    try { $null = $server.Wait(5000) } catch { $null = $_ }
    Assert-Equal 'pipe_untrusted' $result.code
    Assert-Equal 0 @(Get-ChildItem -LiteralPath $layout.SvcOut -Filter '*.stdout.json').Count 'the engine never ran'
    Assert-Equal 'input_on_disk' (Test-ExecRequest -RequestText (Get-RequestText -Job 'smtp-test' -RequestId $id) -InputBytes ([System.Text.Encoding]::ASCII.GetBytes('{}'))).code
}

Test-Case 'W8-6 Save report holds no seeded secret or personal data, follows no link, and lists what it left out' {
    $parent = New-TestDirectory 'w8-report'
    $layout = New-SlateOpsLayout -StateRoot (Join-Path $parent 'SlateOps')
    $null = Initialize-ProtectedTree -Tree $layout.StateTree
    $seeded = @(
        ('SMTP_PASS={0}' -f $script:SeedPassword),
        'postgres://slateops_owner:Db-seeded-S3cret@db:5432/postgres',
        'Authorization: Bearer seededtoken0123456789',
        ('-----BEGIN {0}-----' -f $script:PemKind), $script:SeedPemBody, ('-----END {0}-----' -f $script:PemKind),
        '123456-234567-345678-456789-567890-678901-789012-890123',
        ('recovery {0}' -f $script:SeedKey),
        'invited maria.santos@example.com',
        'C:\Users\maria.santos\Downloads\SlateOpsSetup-0.2.0.exe'
    ) -join "`r`n"
    [System.IO.File]::WriteAllText((Join-Path $layout.StateRoot 'logs\setup\install-20261117T032000Z-abc123.log'), $seeded)
    $outside = New-TestDirectory 'w8-report-outside'
    [System.IO.File]::WriteAllText((Join-Path $outside 'secret.log'), 'OUTSIDE-SEEDED-SECRET')
    $null = & cmd.exe /c mklink /J (Join-Path $layout.StateRoot 'logs\setup\linked') $outside 2>&1
    $staging = Join-Path $parent 'staging'
    $made = New-ReportStaging -Layout $layout -StagingDir $staging -RunId 'report-20261117T040000Z-def456' -StateTrusted -Facts @{ note = 'test' }
    $desktop = New-TestDirectory 'w8-report-desktop'
    $zip = Complete-Report -StagingDir $staging -RunId 'report-20261117T040000Z-def456' -Destination $desktop
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
    $text = New-Object System.Text.StringBuilder
    try {
        foreach ($entry in $archive.Entries) {
            $reader = New-Object System.IO.StreamReader($entry.Open())
            try { [void]$text.Append($reader.ReadToEnd()) } finally { $reader.Dispose() }
        }
    } finally { $archive.Dispose() }
    $all = $text.ToString()
    foreach ($value in @($script:SeedPassword, 'Db-seeded-S3cret', 'seededtoken0123456789', $script:SeedPemBody, '123456-234567', $script:SeedKey, 'maria.santos', 'OUTSIDE-SEEDED-SECRET')) {
        Assert-True (-not $all.Contains($value)) ('the report holds {0}' -f $value)
    }
    Assert-True ($all.Contains('[email]') -and $all.Contains('[recovery key]')) 'placeholders replace the values'
    Assert-True ($all.Contains('logs__setup__linked (a link)')) 'the link is listed as left out'
    Assert-Equal ('SlateOps-report-report-20261117T040000Z-def456.zip') (Split-Path -Leaf $zip)
    Assert-True ($made.files -ge 1)
}

Test-Case 'W8-1 spec 4.1 the first screen follows the saved progress, then the installed version by SemVer precedence' {
    Assert-Equal -1 (Compare-ReleaseVersion -Left '0.2.0-rc.1' -Right '0.2.0-rc.2')
    Assert-Equal -1 (Compare-ReleaseVersion -Left '0.2.0-rc.9' -Right '0.2.0')
    Assert-Equal 1 (Compare-ReleaseVersion -Left '0.10.0' -Right '0.9.9')
    Assert-Equal 0 (Compare-ReleaseVersion -Left '0.2.0' -Right '0.2.0')
    Assert-Equal 'M05' (Get-SetupEntry -Progress $null -Installed '0.2.0-rc.1' -SetupVersion '0.2.0-rc.2').screen
    Assert-Equal 'M01' (Get-SetupEntry -Progress $null -Installed '0.2.0' -SetupVersion '0.2.0-rc.3').screen
    Assert-Equal 'M01' (Get-SetupEntry -Progress @{ stage = 'key_saved' } -Installed '0.2.0' -SetupVersion '0.2.0').screen
    Assert-Equal 'S14' (Get-SetupEntry -Progress @{ stage = 'install_finished' } -Installed '0.2.0' -SetupVersion '0.2.0').next
    Assert-Equal 'S01' (Get-SetupEntry -Progress $null).screen
}

Test-Case 'W8-1 the backup target is <drive>:\SlateOps-backups by the engine rule, never a root and never overlapping the data folder' {
    # Pairs, not a hash literal: its keys ignore case, and case is part of the rule.
    $cases = @(
        @('E:\SlateOps-backups', ''),
        @('E:\', 'backup_target_invalid'),
        @('e:\SlateOps-backups', 'backup_target_invalid'),
        @('E:\a\b\c\d\e\f\g\h\i', 'backup_target_invalid'),
        @('E:\CON', 'backup_target_invalid'),
        @('E:\name.', 'backup_target_invalid'),
        @('E:\..', 'backup_target_invalid'),
        @('E:\bad*name', 'backup_target_invalid'),
        @('D:\SlateOps', 'backup_target_overlaps_data'),
        @('D:\SlateOps\backups', 'backup_target_overlaps_data'),
        @('D:\SlateOps-backups', '')
    )
    foreach ($case in $cases) { Assert-Equal $case[1] (Get-BackupTargetProblem -Target $case[0] -DataRoot 'D:\SlateOps') $case[0] }
    Assert-Equal 'backup_target_overlaps_data' (Get-BackupTargetProblem -Target 'D:\Data' -DataRoot 'D:\Data\SlateOps')
}

Test-Case 'N-1 the C29 removal deletes a real kit folder that holds the kit account entries, and keeps its logs' {
    $name = 'slateops-w8kit'
    $sid = New-TestUser $name
    $root = Join-Path $script:TestRoot 'n-1-kit'
    $kit = @{ AccountName = $name; Root = $root; TaskPath = '\SlateOpsW8NoKit\'; RuleName = 'SlateOpsW8NoKit-rule'; HyperVRule = 'SlateOpsW8NoKit-hv' }
    $problems = @(Initialize-ProtectedTree -Tree (Get-KitTree -Kit $kit) -ServiceSid $sid)
    Assert-Equal 0 $problems.Count ($problems -join '; ')
    [System.IO.File]::WriteAllText((Join-Path $root 'kit\script.ps1'), 'kit')
    [System.IO.File]::WriteAllText((Join-Path $root 'logs\run.log'), 'log')
    $result = Remove-KitLeftovers -Kit $kit
    Assert-Equal 'removed' $result.code ('{0}' -f (ConvertTo-JsonText $result))
    Assert-Equal @('logs') @(Get-ChildItem -LiteralPath $root -Force | ForEach-Object { $_.Name })
    Assert-Equal $null (Get-LocalUser -Name $name -ErrorAction SilentlyContinue)
}

Test-Case 'N-2 import-distro keeps the data tree check but not the parent check that the service account cannot read' {
    $root = New-TestDirectory 'n-2-import'
    $layout = New-SlateOpsLayout -StateRoot (Join-Path $root 'ProgramData\SlateOps') -DataRoot (Join-Path $root 'Data\SlateOps')
    foreach ($path in @($layout.Requests, $layout.SvcOut, $layout.Scripts, $layout.State)) { [void][System.IO.Directory]::CreateDirectory($path) }
    $parent = Split-Path -Parent $layout.DataRoot
    [void][System.IO.Directory]::CreateDirectory($parent)
    # A folder above with an entry that the administrator-side check refuses: before N-2 the
    # job refused it; the job now leaves the folders above to that check.
    $null = & icacls.exe $parent /grant '*S-1-5-11:(OI)(CI)M' 2>&1
    $problems = @(Initialize-ProtectedTree -Tree $layout.DataTree -ServiceSid $script:SelfSid)
    Assert-Equal 0 $problems.Count ($problems -join '; ')
    $image = 'slateops-linux-0.2.0-amd64.tar.gz'
    $gz = Join-Path $layout.Payload $image
    $stream = [System.IO.File]::Create($gz)
    $zip = New-Object System.IO.Compression.GZipStream($stream, [System.IO.Compression.CompressionMode]::Compress)
    $bytes = [System.Text.Encoding]::ASCII.GetBytes('rootfs')
    $zip.Write($bytes, 0, $bytes.Length); $zip.Dispose(); $stream.Dispose()
    $hash = Get-FileSha256 -Path $gz
    Write-JsonFile -Path (Join-Path $layout.Scripts 'version.json') -Value ([ordered]@{ schema_version = 1; version = '0.2.0'; wsl_version = '3.0.5.0'; wsl_msi_sha256 = ('0' * 64); linux_image_sha256 = $hash })
    Write-JsonFile -Path $layout.StateFile -Value ([ordered]@{ schema_version = 1; data_root = $layout.DataRoot; vhd_size_gb = 32 })
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText -Job 'import-distro') -InputBytes $null
    $env:SLATEOPS_STANDIN_MODE = 'big'
    try { $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn }
    finally { Remove-Item Env:\SLATEOPS_STANDIN_MODE }
    Assert-Equal 'imported' $result.code
}

Test-Case 'W8-1 C16 and C17 (plan F1) decide from the mDNS facts; an unreadable value is Advice' {
    Assert-Equal 'fix name_in_use' ('{0} {1}' -f (Get-Check C16 @{ mdns_other = $true; dns_host_name = 'office-pc' }).class, (Get-Check C16 @{ mdns_other = $true; dns_host_name = 'office-pc' }).code)
    Assert-Equal 'office-pc.local' (Get-Check C16 @{ mdns_other = $true; dns_host_name = 'office-pc' }).values.address
    Assert-Equal 'pass' (Get-Check C16 @{ mdns_other = $false }).class
    Assert-Equal 'advice cannot_read' ('{0} {1}' -f (Get-Check C16 @{}).class, (Get-Check C16 @{}).code)
    $ok = @{ dns_client_running = $true; multicast_off = $false; private_rule = 'MDNS-In-UDP-Private-Active'; private_rule_enabled = $true; rule_from_policy = $false }
    Assert-Equal 'pass' (Get-Check C17 @{ mdns = $ok }).class
    $off = $ok.Clone(); $off.private_rule_enabled = $false
    Assert-Equal 'fix rule_off' ('{0} {1}' -f (Get-Check C17 @{ mdns = $off }).class, (Get-Check C17 @{ mdns = $off }).code)
    $policy = $off.Clone(); $policy.rule_from_policy = $true
    Assert-Equal 'policy' (Get-Check C17 @{ mdns = $policy }).code
    $multicast = $ok.Clone(); $multicast.multicast_off = $true
    Assert-Equal 'policy' (Get-Check C17 @{ mdns = $multicast }).code
    Assert-Equal 'advice cannot_read' ('{0} {1}' -f (Get-Check C17 @{}).class, (Get-Check C17 @{}).code)
}

# --- W8 correction 1 (TASK-0094): one test per fix that a Windows runner can show ---

Test-Case 'W8 correction 2 the smtp-test discard goes through the pipe and reaches the engine; an input file stays refused' {
    $layout = New-ExecLayout 'w8c-discard'
    $id = '7b3e4c1a-5d9f-4e82-a043-9c6d1e2f8a57'
    $discard = '{"run_id":"' + $script:RunId + '","mode":"discard"}'
    $server = [TestPipeServer]::Start(('SlateOps-{0}' -f $id), @('S-1-5-32-544', $script:SelfSid), $discard, $false)
    Set-ExecRequest -Layout $layout -RequestText (Get-RequestText -Job 'smtp-test' -RequestId $id) -InputBytes $null
    $result = Invoke-ExecRequest -Layout $layout -WslPath $script:StandIn
    try { $null = $server.Wait(5000) } catch { $null = $_ }
    $sha = New-Object System.Security.Cryptography.SHA256Managed
    $expected = -join ($sha.ComputeHash([System.Text.Encoding]::ASCII.GetBytes($discard)) | ForEach-Object { $_.ToString('x2') })
    Assert-Equal 'ok' $result.code
    Assert-Equal ([long]$discard.Length) $result.pipe_input_bytes
    $output = Read-EngineOutput -Layout $layout -Result $result
    Assert-Equal $expected ([string]$output['sha256']) 'the engine read exactly the discard request'
    Assert-Equal 'input_on_disk' (Test-ExecRequest -RequestText (Get-RequestText -Job 'smtp-test' -RequestId $id) -InputBytes ([System.Text.Encoding]::ASCII.GetBytes($discard))).code
}

Test-Case 'W8 correction 4 a resume after Continue later runs the background preparation again unless it finished' {
    Assert-Equal $false (Get-SetupEntry -Progress @{ stage = 'continue_later' }).background_done
    Assert-Equal $true (Get-SetupEntry -Progress @{ stage = 'continue_later'; background_done = $true }).background_done
    Assert-Equal 'S08' (Get-SetupEntry -Progress @{ stage = 'continue_later' }).next
}

Test-Case 'W8 correction 5 a task that could not sign in the account is named by its last result' {
    Assert-Equal $true (Test-TaskLogonFailure -LastResult 2147943727) '0x8007052F'
    Assert-Equal $true (Test-TaskLogonFailure -LastResult 2147943785) '0x80070569'
    Assert-Equal $true (Test-TaskLogonFailure -LastResult -2147023569) '0x8007052F as a signed value'
    Assert-Equal $false (Test-TaskLogonFailure -LastResult 267011) 'SCHED_S_TASK_HAS_NOT_RUN'
    Assert-Equal $false (Test-TaskLogonFailure -LastResult 0)
}

Test-Case 'W8 correction 7 Save report before S07 holds the helper logs and names a state folder that does not exist yet' {
    $parent = New-TestDirectory 'w8c-early-report'
    $layout = New-SlateOpsLayout -StateRoot (Join-Path $parent 'SlateOps')
    $early = New-TestDirectory 'w8c-early-report-logs'
    [System.IO.File]::WriteAllText((Join-Path $early 'install-20261117T032000Z-abc123.log'), 'check.c05 INFO stop too_small')
    $staging = Join-Path $parent 'staging'
    $null = New-ReportStaging -Layout $layout -StagingDir $staging -RunId 'report-20261117T040000Z-early1' -StateAbsent -HelperLogs $early -Facts @{ note = 'x' }
    Assert-True (Test-Path -LiteralPath (Join-Path $staging 'setup-early__install-20261117T032000Z-abc123.log')) 'the early helper log is in the report'
    $summary = [System.IO.File]::ReadAllText((Join-Path $staging 'report.txt'))
    Assert-True ($summary.Contains('C:\ProgramData\SlateOps (not created yet)')) $summary
    Assert-True (-not $summary.Contains('failed the safety check')) $summary
}
