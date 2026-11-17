# Facts.Tests.ps1 - AC-6: the environment facts (plan 10.4) come from fixed reads on this PC;
# BitLocker is read without key protectors; the Windows time zone maps to an IANA name through
# Windows' own ICU (CLDR windowsZones).

Test-Case 'AC-6 a Windows time zone ID maps to its CLDR IANA name' {
    $cases = [ordered]@{
        'Singapore Standard Time' = 'Asia/Singapore'
        'Pacific Standard Time'   = 'America/Los_Angeles'
        'GMT Standard Time'       = 'Europe/London'
    }
    foreach ($id in $cases.Keys) { Assert-Equal $cases[$id] (ConvertTo-IanaTimeZone -WindowsId $id) $id }
    Assert-Equal $null (ConvertTo-IanaTimeZone -WindowsId 'Not A Zone Standard Time')
    Assert-Equal $null (ConvertTo-IanaTimeZone -WindowsId '..\..\x')
}

Test-Case 'AC-6 P2-4 the facts of this PC hold the 10.4 sections, and BitLocker entries hold status fields only' {
    $facts = Get-EnvironmentFacts -SetupVersion '0.2.0' -DataDrive 'C:'
    foreach ($section in @('windows', 'processor', 'memory', 'volumes', 'network', 'proxy', 'power', 'time', 'restart_pending')) {
        Assert-True ($null -ne $facts[$section]) $section
    }
    Assert-True ($facts['time'].iana -match '^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$') ([string]$facts['time'].iana)
    foreach ($entry in @($facts['bitlocker'])) {
        if ($null -eq $entry) { continue }
        Assert-Equal @('conversion_status', 'encryption_method', 'mount_point', 'protection_status') (Get-OrdinalSorted @($entry.Keys))
    }
    $text = ConvertTo-JsonText $facts
    Assert-Equal $false ($text -match '(?i)keyprotector|recoverypassword')
}
