# Logging.Tests.ps1 - AC-5: run IDs, the 10.1 line format, command logging with arguments, exit
# code and duration, secret masking, output caps and log rotation.

Test-Case 'AC-5 a run ID matches the engine RUN_ID pattern and refuses other kinds' {
    $id = New-RunId -Kind 'install' -Time ([datetime]::new(2026, 11, 17, 3, 20, 0, [System.DateTimeKind]::Utc))
    Assert-True ($id -cmatch '^install-20261117T032000Z-[a-z0-9]{6}$') $id
    Assert-Equal $true (Test-RunId 'package-night-20261117T032000Z-abc123')
    Assert-Equal $false (Test-RunId 'check-20261117T032000Z-abc123') 'the engine has no "check" kind'
    Assert-Equal $false (Test-RunId 'install-20261117T032000Z-ABC123')
    Assert-Throws { New-RunId -Kind 'check' } 'Unknown run kind check.'
}

Test-Case 'AC-5 a log line holds the UTC time, the run ID, the step, the level and one line of text' {
    $line = Format-LogLine -RunId 'install-20261117T032000Z-abc123' -Step 'install.check' -Level 'INFO' -Message "first`r`nsecond" -Time ([datetime]::new(2026, 11, 17, 3, 20, 0, [System.DateTimeKind]::Utc))
    Assert-Equal '2026-11-17T03:20:00Z install-20261117T032000Z-abc123 install.check INFO first | second' $line
}

Test-Case 'AC-5 registered secrets and secret patterns never reach a log line' {
    Clear-LogSecret
    Register-LogSecret 'Tr0ub4dor&3-horse'
    $cases = [ordered]@{
        'a registered secret'   = @('password is Tr0ub4dor&3-horse now', 'password is [secret] now')
        'KEY=value'             = @('SMTP_PASSWORD=hunter22', 'SMTP_PASSWORD=[secret]')
        'quoted value'          = @('RESTIC_PASSWORD="two words"', 'RESTIC_PASSWORD=[secret]')
        'JSON secret field'     = @('{"smtp_password":"hunter22","host":"smtp.example.com"}', '{"smtp_password":"[secret]","host":"smtp.example.com"}')
        'connection string'     = @('postgres://slateops_owner:s3cret@db:5432/postgres', 'postgres://slateops_owner:[secret]@db:5432/postgres')
        'bearer token'          = @('Authorization: Bearer eyJhbGciOiJFUzI1NiJ9.e30.sig', 'Authorization: Bearer [secret]')
        'private key'           = @("-----BEGIN PRIVATE KEY-----`nMIGHAgEAMBMG`n-----END PRIVATE KEY-----", '[private key]')
        'BitLocker recovery'    = @('key 123456-123456-123456-123456-123456-123456-123456-123456 end', 'key [recovery password] end')
        'plain text stays'      = @('wsl.exe --import SlateOps D:\SlateOps\distro', 'wsl.exe --import SlateOps D:\SlateOps\distro')
    }
    foreach ($name in $cases.Keys) { Assert-Equal $cases[$name][1] (Protect-LogText $cases[$name][0]) $name }
    Assert-Throws { Register-LogSecret 'abc' } 'A registered secret must have at least 4 characters.'
    Clear-LogSecret
}

Test-Case 'AC-5 a command is logged with its masked arguments, its exit code and its duration' {
    $dir = New-TestDirectory 'command-log'
    Clear-LogSecret
    Register-LogSecret 'S3cretValue'
    Start-RunLog -RunId 'install-20261117T032000Z-cmd001' -Directory $dir -NoConsole
    $run = Invoke-Logged -Step 'install.test' -FilePath 'cmd.exe' -ArgumentList @('/c', 'echo', 'S3cretValue', '&', 'exit', '3') -NoThrow
    Clear-LogSecret
    Assert-Equal 3 $run.ExitCode
    $lines = @(Get-Content -LiteralPath (Join-Path $dir 'install-20261117T032000Z-cmd001.log'))
    Assert-True ($lines[0] -match ' install-20261117T032000Z-cmd001 install\.test INFO > cmd\.exe /c echo \[secret\] & exit 3$') $lines[0]
    Assert-True ($lines[1] -match 'INFO   exit code 3, [0-9]+ ms, 1 output lines$') $lines[1]
    $output = Get-Content -LiteralPath (Join-Path $dir 'install-20261117T032000Z-cmd001\install.test.1.out.txt') -Raw
    Assert-Equal "[secret]" $output.Trim()
    Assert-Equal $false ((Get-Content -LiteralPath (Join-Path $dir 'install-20261117T032000Z-cmd001.log') -Raw).Contains('S3cretValue'))
    $script:Log.File = $null; $script:Log.StepDir = $null
}

Test-Case 'AC-5 an output file is cut at 1 MB' {
    $path = Join-Path (New-TestDirectory 'cap') 'out.txt'
    Assert-Equal 1048576 (Write-CappedFile -Path $path -Text ('x' * (2MB)))
    Assert-Equal 1048576 (Get-Item -LiteralPath $path).Length
}

Test-Case 'AC-5 rotation keeps the newest 20 runs and every install run' {
    $dir = New-TestDirectory 'rotation'
    [System.IO.File]::WriteAllText((Join-Path $dir 'install-20261101T000000Z-aaaaaa.log'), 'install')
    for ($i = 1; $i -le 25; $i++) {
        $name = 'maintenance-202611{0:D2}T000000Z-bbbbbb' -f $i
        [System.IO.File]::WriteAllText((Join-Path $dir ($name + '.log')), 'run')
        [void][System.IO.Directory]::CreateDirectory((Join-Path $dir $name))
    }
    $removed = Get-OrdinalSorted @(Invoke-LogRotation -Directory $dir)
    Assert-Equal @('maintenance-20261101T000000Z-bbbbbb', 'maintenance-20261102T000000Z-bbbbbb', 'maintenance-20261103T000000Z-bbbbbb',
        'maintenance-20261104T000000Z-bbbbbb', 'maintenance-20261105T000000Z-bbbbbb') $removed
    Assert-Equal $true (Test-Path -LiteralPath (Join-Path $dir 'install-20261101T000000Z-aaaaaa.log'))
    Assert-Equal $false (Test-Path -LiteralPath (Join-Path $dir 'maintenance-20261101T000000Z-bbbbbb'))
}

Test-Case 'AC-5 rotation also keeps a folder under its byte limit' {
    $dir = New-TestDirectory 'rotation-bytes'
    foreach ($day in @(1, 2, 3)) {
        [System.IO.File]::WriteAllText((Join-Path $dir ('package-night-202611{0:D2}T000000Z-cccccc.log' -f $day)), ('y' * 600))
    }
    $removed = @(Invoke-LogRotation -Directory $dir -MaxBytes 1000)
    Assert-Equal @('package-night-20261102T000000Z-cccccc', 'package-night-20261101T000000Z-cccccc') $removed
}

Test-Case 'AC-5 P2-1 run IDs and time stamps use the invariant culture (th-TH set in the same statement)' {
    $time = [datetime]::new(2026, 11, 17, 3, 20, 0, [System.DateTimeKind]::Utc)
    $values = & {
        [System.Threading.Thread]::CurrentThread.CurrentCulture = New-Object System.Globalization.CultureInfo('th-TH')
        Get-UtcStamp -Time $time
        New-RunId -Kind 'install' -Time $time
        Format-LogLine -RunId 'install-20261117T032000Z-abc123' -Step 'install.check' -Level 'INFO' -Message 'x' -Time $time
    }
    Assert-Equal '2026-11-17T03:20:00Z' $values[0]
    Assert-True ($values[1] -cmatch '^install-20261117T032000Z-[a-z0-9]{6}$') $values[1]
    Assert-Equal '2026-11-17T03:20:00Z install-20261117T032000Z-abc123 install.check INFO x' $values[2]
}

