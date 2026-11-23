# Address.Tests.ps1 - DEC-0039 (TASK-0097): the address for PCs and phones is <label>.local, the
# label from the S08 short name; our own mDNS responder in the boot task's process answers for
# it; one inbound UDP 5353 rule is recorded and removed with everything else. The responder
# tests drive the loop with fakes: no socket, no network, no clock.

Test-Case 'AC-A1 the address label follows the DNS label and short name rules' {
    $rows = @(
        @('riverside-learning', $true), @('a', $true), @('a1', $true), @(('a' * 63), $true),
        @(('a' * 64), $false), @('', $false), @('Riverside', $false), @('-river', $false), @('river-', $false),
        @('river--side', $false), @('river_side', $false), @('river.side', $false), @('12345', $false)
    )
    foreach ($row in $rows) { Assert-Equal $row[1] (Test-AddressLabel $row[0]) ('"{0}"' -f $row[0]) }
}

Test-Case 'AC-A2 the stored label comes from install.json, then from the hosts entry of an older install' {
    $root = New-TestDirectory 'ac-a2-label'
    $layout = New-SlateOpsLayout -StateRoot (Join-Path $root 'SlateOps')
    [void][System.IO.Directory]::CreateDirectory($layout.State)
    Assert-Equal '' (Get-InstallAddressLabel -Layout $layout) 'no record'
    Write-JsonFile -Path (Join-Path $layout.State 'windows-changes.json') -Value ([ordered]@{ hosts_name = 'office-pc.local' })
    Assert-Equal 'office-pc' (Get-InstallAddressLabel -Layout $layout) 'an older install: the hosts entry'
    Write-JsonFile -Path $layout.StateFile -Value ([ordered]@{ schema_version = 1; data_root = 'D:\SlateOps'; vhd_size_gb = 30; host_label = 'riverside' })
    Assert-Equal 'riverside' (Get-InstallAddressLabel -Layout $layout) 'install.json'
    Write-JsonFile -Path $layout.StateFile -Value ([ordered]@{ schema_version = 1; data_root = 'D:\SlateOps'; vhd_size_gb = 30; host_label = 'Not A Label' })
    Assert-Equal 'office-pc' (Get-InstallAddressLabel -Layout $layout) 'a label that fails the rules is not used'
}

Test-Case 'AC-A3 the responder answers an A or ANY query for its name only, to the group and, for QU, to the asker' {
    $query = New-MdnsQuery -QueryName 'riverside.local'
    Assert-Equal 'group' (Get-MdnsAction -Data $query -Name 'riverside.local') 'QM A query'
    Assert-Equal 'group unicast' (Get-MdnsAction -Data (New-MdnsQuery -QueryName 'RIVERSIDE.local' -Unicast) -Name 'riverside.local') 'QU, any case'
    Assert-Equal 'group' (Get-MdnsAction -Data (New-MdnsQuery -QueryName 'riverside.local' -Type 255) -Name 'riverside.local') 'ANY'
    Assert-Equal '' (Get-MdnsAction -Data (New-MdnsQuery -QueryName 'riverside.local' -Type 28) -Name 'riverside.local') 'AAAA: no IPv6 record'
    Assert-Equal '' (Get-MdnsAction -Data (New-MdnsQuery -QueryName 'other.local') -Name 'riverside.local') 'another name'
    Assert-Equal '' (Get-MdnsAction -Data (New-MdnsAnswer -QueryName 'riverside.local' -Ip '192.168.1.20') -Name 'riverside.local') 'a response'
    Assert-Equal '' (Get-MdnsAction -Data ([byte[]](1, 2, 3)) -Name 'riverside.local') 'not a DNS message'
    $answer = Get-DnsMessage -Data (New-MdnsAnswer -QueryName 'riverside.local' -Ip '192.168.1.20')
    Assert-Equal 'riverside.local 192.168.1.20' ('{0} {1}' -f $answer.addresses[0].name, $answer.addresses[0].ip)
}

Test-Case 'AC-A3 a response that gives the name another address is a conflict; ours is not' {
    Assert-Equal $true (Test-MdnsConflict -Data (New-MdnsAnswer -QueryName 'riverside.local' -Ip '192.168.1.99') -Name 'riverside.local' -Ip '192.168.1.20')
    Assert-Equal $false (Test-MdnsConflict -Data (New-MdnsAnswer -QueryName 'riverside.local' -Ip '192.168.1.20') -Name 'riverside.local' -Ip '192.168.1.20')
    Assert-Equal $false (Test-MdnsConflict -Data (New-MdnsAnswer -QueryName 'other.local' -Ip '192.168.1.99') -Name 'riverside.local' -Ip '192.168.1.20')
    Assert-Equal $false (Test-MdnsConflict -Data (New-MdnsQuery -QueryName 'riverside.local') -Name 'riverside.local' -Ip '192.168.1.20')
}

# A fake network for Invoke-MdnsResponder: the adapter address per minute, the packets that
# arrive, and every packet sent and socket opened, on a clock that only the loop moves.
function New-FakeNet {
    param([string[]]$Addresses, [System.Collections.ArrayList]$Incoming)
    $net = @{ Now = 0; Sent = (New-Object System.Collections.Generic.List[string]); Opened = (New-Object System.Collections.Generic.List[string]); Closed = 0 }
    # A closure sees no function of the test runner's scope, so the parser goes in as a value.
    $net.Parse = ${function:Get-DnsMessage}
    $net.Clock = { $net.Now }.GetNewClosure()
    $net.Sleep = { param([int]$Ms) $net.Now += $Ms }.GetNewClosure()
    $net.GetAddress = { $minute = [int][math]::Floor($net.Now / 60000); if ($minute -lt $Addresses.Count) { $Addresses[$minute] } else { $Addresses[-1] } }.GetNewClosure()
    $net.OpenSocket = {
        param([string]$Ip)
        # GetNewClosure copies only the variables of this scope, so the inner blocks get local
        # copies of the fake network and its queue.
        $net = $net
        $Incoming = $Incoming
        $net.Opened.Add($Ip)
        return @{
            Send = { param([byte[]]$Data, [string]$To) $message = & $net.Parse -Data $Data; $kind = $(if ($message.response) { 'answer' } else { 'probe' }); $net.Sent.Add(('{0} {1} {2}' -f $kind, $To, $(if ($message.addresses.Count) { $message.addresses[0].ip } else { '' })).Trim()) }.GetNewClosure()
            Receive = { param([int]$TimeoutMs) $net.Now += $TimeoutMs; if ($Incoming.Count -gt 0) { $packet = $Incoming[0]; $Incoming.RemoveAt(0); return $packet } return $null }.GetNewClosure()
            Close = { $net.Closed++ }.GetNewClosure()
        }
    }.GetNewClosure()
    return $net
}

Test-Case 'AC-A3 the responder probes three times, announces twice, then answers a query' {
    $incoming = New-Object System.Collections.ArrayList
    $net = New-FakeNet -Addresses @('192.168.1.20') -Incoming $incoming
    $null = $incoming.Add($null); $null = $incoming.Add($null); $null = $incoming.Add($null)
    $null = $incoming.Add(@{ data = (New-MdnsQuery -QueryName 'riverside.local' -Unicast); remote = '192.168.1.50:5353' })
    Invoke-MdnsResponder -Name 'riverside.local' -GetAddress $net.GetAddress -OpenSocket $net.OpenSocket -Clock $net.Clock -Sleep $net.Sleep -Until { $net.Now -ge 20000 }.GetNewClosure() -Log { param($Level, $Text) }
    Assert-Equal @('192.168.1.20') @($net.Opened)
    Assert-Equal @('probe group 192.168.1.20', 'probe group 192.168.1.20', 'probe group 192.168.1.20', 'answer group 192.168.1.20', 'answer group 192.168.1.20', 'answer group 192.168.1.20', 'answer 192.168.1.50:5353 192.168.1.20') @($net.Sent)
    Assert-Equal 1 $net.Closed 'the socket closes when the loop ends'
}

Test-Case 'AC-A3 the responder re-checks the adapter every minute: a new address is probed and announced, no network means no answer' {
    $incoming = New-Object System.Collections.ArrayList
    $net = New-FakeNet -Addresses @('192.168.1.20', $null, '10.0.0.7') -Incoming $incoming
    Invoke-MdnsResponder -Name 'riverside.local' -GetAddress $net.GetAddress -OpenSocket $net.OpenSocket -Clock $net.Clock -Sleep $net.Sleep -Until { $net.Now -ge 150000 }.GetNewClosure() -Log { param($Level, $Text) }
    Assert-Equal @('192.168.1.20', '10.0.0.7') @($net.Opened) 'one socket per address; none while there is no network'
    Assert-Equal 2 $net.Closed
    $announced = @($net.Sent | Where-Object { $_ -like 'answer group *' })
    Assert-Equal @('answer group 192.168.1.20', 'answer group 192.168.1.20', 'answer group 10.0.0.7', 'answer group 10.0.0.7') $announced
}

Test-Case 'AC-O7 an empty UDP packet neither stops the responder nor counts as a conflict' {
    Assert-Equal '' (Get-MdnsAction -Data ([byte[]]@()) -Name 'riverside.local') 'an empty packet is not a query'
    Assert-Equal $false (Test-MdnsConflict -Data ([byte[]]@()) -Name 'riverside.local' -Ip '192.168.1.20')
    $incoming = New-Object System.Collections.ArrayList
    $net = New-FakeNet -Addresses @('192.168.1.20') -Incoming $incoming
    # An empty packet while probing, two quiet probes, an empty packet while answering, then a query.
    $null = $incoming.Add(@{ data = [byte[]]@(); remote = '192.168.1.66:5353' }); $null = $incoming.Add($null); $null = $incoming.Add($null)
    $null = $incoming.Add(@{ data = [byte[]]@(); remote = '192.168.1.66:5353' })
    $null = $incoming.Add(@{ data = (New-MdnsQuery -QueryName 'riverside.local' -Unicast); remote = '192.168.1.50:5353' })
    $lines = New-Object System.Collections.Generic.List[string]
    Invoke-MdnsResponder -Name 'riverside.local' -GetAddress $net.GetAddress -OpenSocket $net.OpenSocket -Clock $net.Clock -Sleep $net.Sleep -Until { $net.Now -ge 20000 }.GetNewClosure() -Log { param($Level, $Text) $lines.Add(('{0} {1}' -f $Level, $Text)) }.GetNewClosure()
    Assert-Equal @('probe group 192.168.1.20', 'probe group 192.168.1.20', 'probe group 192.168.1.20', 'answer group 192.168.1.20', 'answer group 192.168.1.20', 'answer group 192.168.1.20', 'answer 192.168.1.50:5353 192.168.1.20') @($net.Sent) ($lines -join ' | ')
}

Test-Case 'AC-A3 a conflict during probing means no announcement and no answer until the next check' {
    $incoming = New-Object System.Collections.ArrayList
    $net = New-FakeNet -Addresses @('192.168.1.20') -Incoming $incoming
    $null = $incoming.Add(@{ data = (New-MdnsAnswer -QueryName 'riverside.local' -Ip '192.168.1.99'); remote = '192.168.1.99:5353' })
    $null = $incoming.Add(@{ data = (New-MdnsQuery -QueryName 'riverside.local'); remote = '192.168.1.50:5353' })
    $lines = New-Object System.Collections.Generic.List[string]
    Invoke-MdnsResponder -Name 'riverside.local' -GetAddress $net.GetAddress -OpenSocket $net.OpenSocket -Clock $net.Clock -Sleep $net.Sleep -Until { $net.Now -ge 30000 }.GetNewClosure() -Log { param($Level, $Text) $lines.Add(('{0} {1}' -f $Level, $Text)) }.GetNewClosure()
    Assert-Equal 0 @($net.Sent | Where-Object { $_ -like 'answer*' }).Count 'no answer for a name that another device holds'
    Assert-True (@($lines | Where-Object { $_ -like 'WARN *another device*' }).Count -ge 1) ($lines -join ' | ')
}

Test-Case 'AC-A4 the mDNS rule allows inbound UDP 5353 to this PowerShell only, on Private networks, from the local subnet' {
    $definition = Get-FirewallRuleDefinition -Cidr '192.168.1.0/24'
    $rule = $definition.Mdns
    Assert-Equal 'SlateOps-mDNS-In-UDP' $rule.Name
    Assert-Equal 'Inbound UDP 5353 Private LocalSubnet Allow' ('{0} {1} {2} {3} {4} {5}' -f $rule.Direction, $rule.Protocol, $rule.LocalPort, $rule.Profile, $rule.RemoteAddress, $rule.Action)
    Assert-Equal (Join-Path $SlateOpsPaths.System32 'WindowsPowerShell\v1.0\powershell.exe') $rule.Program
    Assert-Equal @('SlateOps-TCP-443-80', 'SlateOps-mDNS-In-UDP') @(Get-FirewallRecordNames -Definition $definition) 'both rules go into firewall_rules, so every removal path deletes them'
}

Test-Case 'AC-A5 the PC check has no C15 and no C30; the name probe runs on S08' {
    Assert-Equal $false (@($SlateOpsCheck.RequirementIds) -contains 'C15')
    $facts = @{ os_build = 22631 }
    $ids = @(Invoke-PcCheck -Facts $facts -PinnedWsl ([version]'2.6.1.0') | ForEach-Object { $_.id })
    foreach ($id in @('C15', 'C16', 'C30')) { Assert-Equal $false ($ids -contains $id) $id }
    Assert-Equal 27 $ids.Count
}
