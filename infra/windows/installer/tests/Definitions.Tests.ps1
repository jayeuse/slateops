# Definitions.Tests.ps1 - AC-4: the account, task, .wslconfig and rule definitions keep the
# boot-test kit's values (infra/windows/boot-test/10-setup.ps1 and lib/svc-exec.ps1; REQ-0022
# E1, E2, E4, E5, E6) apart from names and paths; plus the resume, hosts, MSI and CA rules.

$script:TestCaPem = @'
-----BEGIN CERTIFICATE-----
MIIBiTCCATCgAwIBAgIUJMNxs0ydG8FSV9CbY1O3kZV5PDUwCgYIKoZIzj0EAwIw
IzEhMB8GA1UEAwwYU2xhdGUgT3BlcmF0aW9ucyBUZXN0IENBMB4XDTI2MTExNzA1
NDExOFoXDTM2MTExNDA1NDExOFowIzEhMB8GA1UEAwwYU2xhdGUgT3BlcmF0aW9u
cyBUZXN0IENBMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE5KdfDgEuUEWByIL7
rRZPy6I+wJfQtJ8pUNBNJE4ZcxqzMa/tsSSpfOrWj+S0u3BFfHP9B8CSOmPB2S0t
lIA4V6NCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMCAQYwHQYDVR0O
BBYEFGYcAV9Ry31mnnf/v6QLB6UaDtpjMAoGCCqGSM49BAMCA0cAMEQCIEM7uA+l
lmwPUnS8TOPotd/SeAwy4F2CmqRFd6jpsh8YAiAqcoDIu09WsjD5xEbm1Gykb9ye
r1FO4QiPZ7iALkS4Bg==
-----END CERTIFICATE-----
'@
$script:TestLeafPem = @'
-----BEGIN CERTIFICATE-----
MIIBajCCARGgAwIBAgIUAQa4tCyjAzdehoWqx0ScWiyjsxIwCgYIKoZIzj0EAwIw
IzEhMB8GA1UEAwwYU2xhdGUgT3BlcmF0aW9ucyBUZXN0IENBMB4XDTI2MTExNzA1
NDExOFoXDTI3MTIxOTA1NDExOFowGjEYMBYGA1UEAwwPb2ZmaWNlLXBjLmxvY2Fs
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE39F/MtciegA+S0i6n0h0T+aHAYWl
UcvI0cQETq3jnK0lAgmY4/oByz2F/LRCKSjCBOb+WrmEtX/9rOtUKMGqZaMsMCow
DAYDVR0TAQH/BAIwADAaBgNVHREEEzARgg9vZmZpY2UtcGMubG9jYWwwCgYIKoZI
zj0EAwIDRwAwRAIgG3xcYxnZ9QcPG17djkbuwlY0DBBirFEz1KtBE6vnPkkCID9n
3KGd18M0lD8LKMsKXgv95yA5Mjz2FmeTDmkQJBxB
-----END CERTIFICATE-----
'@

Test-Case 'AC-4 the boot task keeps the kit settings (W7-6)' {
    $definition = Get-StartTaskDefinition -ScriptsDir 'C:\ProgramData\SlateOps\scripts'
    $objects = New-TaskSettingsFromDefinition -Definition $definition
    $settings = $objects.Settings
    Assert-Equal 'PT0S' $settings.ExecutionTimeLimit
    Assert-Equal 999 $settings.RestartCount
    Assert-Equal 'PT1M' $settings.RestartInterval
    Assert-Equal 'IgnoreNew' ([string]$settings.MultipleInstances)
    Assert-Equal $false $settings.DisallowStartIfOnBatteries
    Assert-Equal $false $settings.StopIfGoingOnBatteries
    Assert-Equal $true $settings.StartWhenAvailable
    Assert-Equal 4 $settings.Priority
    Assert-Equal $false $settings.IdleSettings.StopOnIdleEnd
    Assert-Equal 'PT1M' $objects.Trigger.Repetition.Interval
    Assert-Equal 'MSFT_TaskBootTrigger' $objects.Trigger.CimClass.CimClassName
    Assert-Equal 'Limited' $definition.RunLevel
    Assert-Equal '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\ProgramData\SlateOps\scripts\start.ps1"' $objects.Action.Arguments
}

Test-Case 'AC-4 the Exec task keeps the kit settings and has no trigger' {
    $definition = Get-ExecTaskDefinition -ScriptsDir 'C:\ProgramData\SlateOps\scripts'
    $objects = New-TaskSettingsFromDefinition -Definition $definition
    Assert-Equal 'PT2H' $objects.Settings.ExecutionTimeLimit
    Assert-Equal 'IgnoreNew' ([string]$objects.Settings.MultipleInstances)
    Assert-Equal $false $objects.Settings.DisallowStartIfOnBatteries
    Assert-Equal $false $objects.Settings.StopIfGoingOnBatteries
    Assert-Equal $true $objects.Settings.StartWhenAvailable
    Assert-Equal $null $objects.Trigger
    Assert-Equal '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\ProgramData\SlateOps\scripts\exec.ps1"' $objects.Action.Arguments
}

Test-Case 'AC-4 the account is a hidden standard user with batch logon and the three deny rights' {
    $account = Get-AccountDefinition
    Assert-Equal 'slateops-svc' $account.Name
    Assert-Equal @('S-1-5-32-545') $account.Groups
    Assert-Equal @('SeBatchLogonRight', 'SeDenyInteractiveLogonRight', 'SeDenyRemoteInteractiveLogonRight', 'SeDenyNetworkLogonRight') $account.Rights
    Assert-Equal $true $account.Hidden
}

Test-Case 'AC-4 setup never reuses an existing slateops-svc account' {
    $layout = New-SlateOpsLayout -StateRoot (Join-Path (New-TestDirectory 'reuse') 'SlateOps')
    $null = New-TestUser 'slateops-svc'
    $result = Install-ServiceAccountAndTasks -Layout $layout
    Assert-Equal 'account_exists' $result.code
    Assert-Equal $null (Get-ScheduledTask -TaskPath '\SlateOps\' -ErrorAction SilentlyContinue)
    Remove-LocalUser -Name 'slateops-svc'
}

Test-Case 'AC-4 .wslconfig holds the kit values, mirrored networking and the disk size, and leaves DNS tunneling at its default' {
    $expected = @(
        '# Written by Slate Operations setup for the account slateops-svc.',
        '[wsl2]',
        'memory=6GB',
        'vmIdleTimeout=-1',
        'networkingMode=mirrored',
        'defaultVhdSize=120GB',
        '',
        '[general]',
        'instanceIdleTimeout=-1'
    )
    Assert-Equal $expected (Get-WslConfigText -VhdSizeGB 120)
    Assert-Throws { Get-WslConfigText -VhdSizeGB 8 } 'The disk size is outside*'
}

Test-Case 'AC-4 the disk limit is 90 percent of the free space, between 16 and 1024 GB' {
    Assert-Equal 90 (Get-VhdSizeGB -FreeBytes ([long]100 * 1GB))
    Assert-Equal 16 (Get-VhdSizeGB -FreeBytes ([long]10 * 1GB))
    Assert-Equal 1024 (Get-VhdSizeGB -FreeBytes ([long]4000 * 1GB))
}

Test-Case 'AC-4 the firewall rules open TCP 443 and 80 on the Private profile from the local network only' {
    $rules = Get-FirewallRuleDefinition -Cidr '192.168.1.0/24'
    Assert-Equal 'Private LocalSubnet Inbound Allow TCP' ('{0} {1} {2} {3} {4}' -f $rules.Windows.Profile, $rules.Windows.RemoteAddress, $rules.Windows.Direction, $rules.Windows.Action, $rules.Windows.Protocol)
    Assert-Equal @('443', '80') $rules.Windows.LocalPort
    Assert-Equal '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90} Private 192.168.1.0/24' ('{0} {1} {2}' -f $rules.HyperV.VMCreatorId, $rules.HyperV.Profiles, $rules.HyperV.RemoteAddresses)
    Assert-Equal '192.168.1.0/24' (ConvertTo-NetworkCidr -Address '192.168.1.23' -PrefixLength 24)
    Assert-Throws { Get-FirewallRuleDefinition -Cidr 'Any' } 'Not an IPv4 network.'
}

Test-Case 'AC-4 the hosts entry is one marked line that a second run does not repeat' {
    $existing = "# Copyright`r`n127.0.0.1 localhost`r`n"
    $once = Get-HostsContent -Existing $existing -HostName 'office-pc.local'
    Assert-Equal "# Copyright`r`n127.0.0.1 localhost`r`n127.0.0.1 office-pc.local # Slate Operations`r`n" $once
    Assert-Equal $once (Get-HostsContent -Existing $once -HostName 'office-pc.local')
    Assert-Equal "# Copyright`r`n127.0.0.1 localhost`r`n127.0.0.1 new-pc.local # Slate Operations`r`n" (Get-HostsContent -Existing $once -HostName 'new-pc.local')
    Assert-Throws { Get-HostsContent -Existing '' -HostName 'evil.com' } 'Not a .local name.'
}

Test-Case 'AC-4 the resume starts the original setup file through Explorer, so Windows asks for administrator approval' {
    Assert-Equal ('"{0}\explorer.exe" "D:\Downloads\SlateOpsSetup-0.2.0.exe"' -f $env:SystemRoot) (Get-ResumeCommand -SetupPath 'D:\Downloads\SlateOpsSetup-0.2.0.exe')
    Assert-Throws { Get-ResumeCommand -SetupPath 'D:\x" /evil "y.exe' } 'Not a setup file path.'
}

Test-Case 'AC-4 the first screen comes from the saved progress only (spec 4.1)' {
    $cases = [ordered]@{
        'check_restart'    = 'S02'
        'feature_restart'  = 'S06 S07'
        'continue_later'   = 'S06 S08'
        'install_started'  = 'S06 S12'
        'install_finished' = 'S06 S14'
    }
    Assert-Equal 'S01' (Get-SetupEntry -Progress $null).screen
    foreach ($stage in $cases.Keys) {
        $entry = Get-SetupEntry -Progress @{ stage = $stage }
        Assert-Equal $cases[$stage] (('{0} {1}' -f $entry.screen, $entry.next).Trim()) $stage
    }
    Assert-Equal 'S09' (Get-SetupEntry -Progress @{ stage = 'install_started'; email_discarded = $true }).next
}

Test-Case 'AC-4 the saved progress holds the stage, the run ID and true or false marks only' {
    $layout = New-SlateOpsLayout -StateRoot (Join-Path (New-TestDirectory 'progress') 'SlateOps')
    $null = Initialize-ProtectedTree -Tree $layout.StateTree
    Save-SetupProgress -Layout $layout -Stage 'feature_restart' -RunId 'install-20261117T032000Z-abc123'
    $saved = Read-SetupProgress -Layout $layout
    Assert-Equal @('run_id', 'saved_at', 'schema_version', 'stage') @($saved.Keys | Sort-Object)
    Assert-Throws { Save-SetupProgress -Layout $layout -Stage 'install_started' -RunId 'install-20261117T032000Z-abc123' -Marks @{ admin_email = 'maria@example.com' } } 'A mark is true or false.'
    Assert-Throws { Save-SetupProgress -Layout $layout -Stage 'anything' -RunId 'install-20261117T032000Z-abc123' } 'Unknown stage.'
}

Test-Case 'AC-4 the MSI exit codes map to the plan 10.7 outcomes' {
    Assert-Equal 'installed restart_needed busy failed' ('{0} {1} {2} {3}' -f (Get-MsiOutcome 0), (Get-MsiOutcome 3010), (Get-MsiOutcome 1618), (Get-MsiOutcome 1603))
}

Test-Case 'AC-4 only a self-signed CA certificate is trusted, and its security code matches the engine format' {
    $ca = ConvertFrom-PemCertificate -Pem $script:TestCaPem
    Assert-Equal $true (Test-CaCertificate -Certificate $ca)
    Assert-Equal 'B8:19:44:7B:92:E3:03:F3:01:1D:53:80:1F:CC:BE:B5:14:0F:35:B1:0F:18:5C:D0:F2:74:25:EC:BC:FF:04:95' (Get-CaSecurityCode -Certificate $ca)
    Assert-Equal $false (Test-CaCertificate -Certificate (ConvertFrom-PemCertificate -Pem $script:TestLeafPem))
    $layout = New-SlateOpsLayout -StateRoot (Join-Path (New-TestDirectory 'ca') 'SlateOps')
    Assert-Equal 'certificate_invalid' (Install-TrustedCa -Layout $layout -Pem $script:TestLeafPem).code
    Assert-Equal 'certificate_invalid' (Install-TrustedCa -Layout $layout -Pem 'not a certificate').code
}
