# Mdns.ps1 - the address for PCs and phones (DEC-0039, TASK-0097): <label>.local, the label from
# the S08 short name, and our own mDNS responder for it (option B; the CI mdns-spike showed that
# Windows' own responder never answers for a registered name other than the computer name).
#
# The responder runs in the boot task's process (start.ps1, slateops-svc) on a thread of its own:
# it binds UDP 5353 beside Windows' responder, joins 224.0.0.251 on the gateway adapter, probes
# its name (RFC 6762 8.1), announces it (8.3) and answers A and ANY queries for it with that
# adapter's IPv4 (6). It checks the adapter again every 60 s; with no network it answers
# nothing; it stops when the process ends. It logs to the boot run log only, and never the
# addresses of the devices that ask. Windows PowerShell 5.1, ASCII only.

$SlateOpsMdns = @{
    Group          = '224.0.0.251'
    Port           = 5353
    # RFC 6762 10: 120 s for a record that names a host.
    Ttl            = 120
    RecheckMs      = 60000
    # RFC 6762 8.1: three probes 250 ms apart; 8.3: two announcements one second apart.
    ProbeCount     = 3
    ProbeWaitMs    = 250
    AnnounceCount  = 2
    AnnounceWaitMs = 1000
    ReceiveMs      = 1000
    # One summary line per hour with the number of answers, not one line per query.
    SummaryMs      = 3600000
}

function Test-AddressLabel {
    # The S08 short name as the label of <label>.local: the engine's short name rule
    # (answers.valid_identity: a-z and 0-9 in groups split by single hyphens) and the DNS label
    # rule (63 characters at most, not all digits, as Test-DnsLabel).
    param([AllowNull()][AllowEmptyString()][string]$Label)
    if (-not $Label) { return $false }
    if ($Label.Length -gt 63) { return $false }
    if ($Label -cnotmatch '^[a-z0-9]+(-[a-z0-9]+)*$') { return $false }
    if ($Label -match '^[0-9]+$') { return $false }
    return $true
}

function Get-InstallAddressLabel {
    # The label of the installation's address: host_label in install.json (written by
    # prepare-data at Install), else the hosts entry of an older install (hosts_name in
    # windows-changes.json, "<label>.local"); '' when neither passes the label rule. Every user
    # of the address reads it here: the hosts entry, the HTTPS check, Repair, the responder.
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    if (Test-Path -LiteralPath $Layout.StateFile -PathType Leaf) {
        try {
            $label = [string](Get-DictValue (Read-JsonFile -Path $Layout.StateFile) 'host_label')
            if (Test-AddressLabel $label) { return $label }
        } catch { $null = $_ }
    }
    $changes = Join-Path $Layout.State 'windows-changes.json'
    if (Test-Path -LiteralPath $changes -PathType Leaf) {
        try {
            $hostsName = [string](Get-DictValue (Read-JsonFile -Path $changes) 'hosts_name')
            if ($hostsName -match '^(?<label>[A-Za-z0-9-]+)\.local$') {
                $label = $Matches['label'].ToLowerInvariant()
                if (Test-AddressLabel $label) { return $label }
            }
        } catch { $null = $_ }
    }
    return ''
}

# ---------------------------------------------------------------------------
# DNS messages (RFC 1035, RFC 6762): one name, A records only
# ---------------------------------------------------------------------------

function ConvertTo-DnsName {
    param([Parameter(Mandatory = $true)][string]$Text)
    $bytes = New-Object System.Collections.Generic.List[byte]
    foreach ($label in $Text.TrimEnd('.').Split('.')) {
        $part = [System.Text.Encoding]::ASCII.GetBytes($label)
        $bytes.Add([byte]$part.Length)
        $bytes.AddRange($part)
    }
    $bytes.Add([byte]0)
    return , $bytes.ToArray()
}

function New-MdnsQuery {
    # One question, class IN; -Unicast sets the QU bit (RFC 6762 5.4). A probe (8.1) is a query
    # of type ANY with the record it wants in the authority section (-Ip).
    param([Parameter(Mandatory = $true)][string]$QueryName, [int]$Type = 1, [switch]$Unicast, [string]$Ip = '')
    $bytes = New-Object System.Collections.Generic.List[byte]
    $authority = $(if ($Ip) { 1 } else { 0 })
    $bytes.AddRange([byte[]](0, 0, 0, 0, 0, 1, 0, 0, 0, $authority, 0, 0))
    $bytes.AddRange((ConvertTo-DnsName $QueryName))
    $bytes.AddRange([byte[]](0, $Type))
    if ($Unicast) { $bytes.AddRange([byte[]](0x80, 1)) } else { $bytes.AddRange([byte[]](0, 1)) }
    if ($Ip) {
        $bytes.AddRange((ConvertTo-DnsName $QueryName))
        $bytes.AddRange([byte[]](0, 1, 0, 1, 0, 0, 0, $SlateOpsMdns.Ttl, 0, 4))
        $bytes.AddRange([System.Net.IPAddress]::Parse($Ip).GetAddressBytes())
    }
    return , $bytes.ToArray()
}

function New-MdnsAnswer {
    # One A record, cache-flush class, TTL 120 (RFC 6762 10.2): an announcement or an answer.
    param([Parameter(Mandatory = $true)][string]$QueryName, [Parameter(Mandatory = $true)][string]$Ip)
    $bytes = New-Object System.Collections.Generic.List[byte]
    $bytes.AddRange([byte[]](0, 0, 0x84, 0, 0, 0, 0, 1, 0, 0, 0, 0))
    $bytes.AddRange((ConvertTo-DnsName $QueryName))
    $bytes.AddRange([byte[]](0, 1, 0x80, 1, 0, 0, 0, $SlateOpsMdns.Ttl, 0, 4))
    $bytes.AddRange([System.Net.IPAddress]::Parse($Ip).GetAddressBytes())
    return , $bytes.ToArray()
}

function Read-DnsName {
    param([Parameter(Mandatory = $true)][byte[]]$Data, [Parameter(Mandatory = $true)][int]$Offset)
    $labels = New-Object System.Collections.Generic.List[string]
    $next = -1
    $pos = $Offset
    $jumps = 0
    while ($true) {
        if ($pos -ge $Data.Length) { throw 'dns_truncated' }
        $length = [int]$Data[$pos]
        if ($length -eq 0) { $pos++; break }
        if (($length -band 0xC0) -eq 0xC0) {
            if ($pos + 1 -ge $Data.Length) { throw 'dns_truncated' }
            if ($next -lt 0) { $next = $pos + 2 }
            $pos = (($length -band 0x3F) * 256) + [int]$Data[$pos + 1]
            $jumps++
            if ($jumps -gt 32) { throw 'dns_loop' }
            continue
        }
        if ($pos + 1 + $length -gt $Data.Length) { throw 'dns_truncated' }
        $labels.Add([System.Text.Encoding]::ASCII.GetString($Data, $pos + 1, $length))
        $pos += 1 + $length
    }
    if ($next -lt 0) { $next = $pos }
    return @{ name = ($labels.ToArray() -join '.'); next = $next }
}

function Get-DnsMessage {
    # @{ response; questions = @(@{name; type; unicast}); addresses = @(@{name; ip}) }. Throws on
    # a message that is not DNS.
    param([Parameter(Mandatory = $true)][byte[]]$Data)
    if ($Data.Length -lt 12) { throw 'dns_short' }
    $flags = ([int]$Data[2] * 256) + [int]$Data[3]
    $questionCount = ([int]$Data[4] * 256) + [int]$Data[5]
    $recordCount = (([int]$Data[6] * 256) + [int]$Data[7]) + (([int]$Data[8] * 256) + [int]$Data[9]) + (([int]$Data[10] * 256) + [int]$Data[11])
    if (($questionCount -gt 64) -or ($recordCount -gt 256)) { throw 'dns_counts' }
    $pos = 12
    $questions = @()
    for ($i = 0; $i -lt $questionCount; $i++) {
        $read = Read-DnsName -Data $Data -Offset $pos
        $pos = $read.next
        if ($pos + 4 -gt $Data.Length) { throw 'dns_truncated' }
        $type = ([int]$Data[$pos] * 256) + [int]$Data[$pos + 1]
        $unicast = (([int]$Data[$pos + 2] -band 0x80) -ne 0)
        $pos += 4
        $questions += , @{ name = $read.name; type = $type; unicast = $unicast }
    }
    $addresses = @()
    for ($i = 0; $i -lt $recordCount; $i++) {
        $read = Read-DnsName -Data $Data -Offset $pos
        $pos = $read.next
        if ($pos + 10 -gt $Data.Length) { throw 'dns_truncated' }
        $type = ([int]$Data[$pos] * 256) + [int]$Data[$pos + 1]
        $length = ([int]$Data[$pos + 8] * 256) + [int]$Data[$pos + 9]
        if ($pos + 10 + $length -gt $Data.Length) { throw 'dns_truncated' }
        if (($type -eq 1) -and ($length -eq 4)) { $addresses += , @{ name = $read.name; ip = ('{0}.{1}.{2}.{3}' -f $Data[$pos + 10], $Data[$pos + 11], $Data[$pos + 12], $Data[$pos + 13]) } }
        $pos += 10 + $length
    }
    return @{ response = (($flags -band 0x8000) -ne 0); questions = $questions; addresses = $addresses }
}

function Get-MdnsAction {
    # What a received packet asks of the responder: 'group' (answer to 224.0.0.251), 'group
    # unicast' (also to the asker, QU bit), or '' (not a query for Name of type A or ANY).
    param([Parameter(Mandatory = $true)][byte[]]$Data, [Parameter(Mandatory = $true)][string]$Name)
    try { $message = Get-DnsMessage -Data $Data } catch { return '' }
    if ($message.response) { return '' }
    $action = ''
    foreach ($question in $message.questions) {
        if (($question.name -ine $Name) -or (@(1, 255) -notcontains $question.type)) { continue }
        if ($question.unicast) { return 'group unicast' }
        $action = 'group'
    }
    return $action
}

function Test-MdnsConflict {
    # RFC 6762 8.2 (simplified): during probing, a response that gives Name an address other than
    # ours means another device holds the name.
    param([Parameter(Mandatory = $true)][byte[]]$Data, [Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][string]$Ip)
    try { $message = Get-DnsMessage -Data $Data } catch { return $false }
    if (-not $message.response) { return $false }
    foreach ($record in $message.addresses) {
        if (($record.name -ieq $Name) -and ($record.ip -ne $Ip)) { return $true }
    }
    return $false
}

# ---------------------------------------------------------------------------
# The responder loop. Every outside call is a parameter, so the tests drive it with fakes.
# ---------------------------------------------------------------------------

function Invoke-MdnsResponder {
    # GetAddress: the gateway adapter's IPv4, or $null with no network. OpenSocket(ip): an object
    # with Send(bytes, 'group' or 'address:port'), Receive(timeout ms) -> @{ data; remote } or
    # $null, and Close(). Clock: milliseconds. Sleep(ms). Until: True ends the loop. Log(level,
    # text).
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$GetAddress,
        [Parameter(Mandatory = $true)][scriptblock]$OpenSocket,
        [Parameter(Mandatory = $true)][scriptblock]$Clock,
        [Parameter(Mandatory = $true)][scriptblock]$Sleep,
        [Parameter(Mandatory = $true)][scriptblock]$Until,
        [Parameter(Mandatory = $true)][scriptblock]$Log
    )
    $current = $null
    $socket = $null
    $answering = $false
    $nextCheck = [long](& $Clock)
    $answered = 0
    $nextSummary = $nextCheck + $SlateOpsMdns.SummaryMs
    & $Log 'INFO' ('mDNS responder for {0} starts' -f $Name)
    try {
        while (-not (& $Until)) {
            $now = [long](& $Clock)
            if ($now -ge $nextSummary) {
                if ($answered -gt 0) { & $Log 'INFO' ('mDNS: answered {0} queries for {1} in the last hour' -f $answered, $Name) }
                $answered = 0
                $nextSummary = $now + $SlateOpsMdns.SummaryMs
            }
            if ($now -ge $nextCheck) {
                $nextCheck = $now + $SlateOpsMdns.RecheckMs
                $ip = $null
                try { $ip = & $GetAddress } catch { $ip = $null }
                if (-not $ip) { $ip = $null }
                if ($ip -ne $current) {
                    if ($socket) { & $socket.Close; $socket = $null }
                    $answering = $false
                    $current = $ip
                    if (-not $ip) { & $Log 'INFO' 'mDNS: no network; no answers until a network is back' }
                    else {
                        try { $socket = & $OpenSocket $ip }
                        catch {
                            & $Log 'WARN' ('mDNS: UDP 5353 not bound on {0}: {1}; trying again in a minute' -f $ip, $_.Exception.Message)
                            $socket = $null
                            $current = $null
                        }
                        if ($socket) {
                            $conflict = $false
                            for ($probe = 1; ($probe -le $SlateOpsMdns.ProbeCount) -and -not $conflict; $probe++) {
                                & $socket.Send (New-MdnsQuery -QueryName $Name -Type 255 -Unicast -Ip $ip) 'group'
                                $packet = & $socket.Receive $SlateOpsMdns.ProbeWaitMs
                                if ($packet -and (Test-MdnsConflict -Data $packet.data -Name $Name -Ip $ip)) { $conflict = $true }
                            }
                            if ($conflict) {
                                & $Log 'WARN' ('mDNS: another device answers for {0}; no answers from this PC; probing again in a minute' -f $Name)
                                & $socket.Close
                                $socket = $null
                                $current = $null
                            } else {
                                for ($announce = 1; $announce -le $SlateOpsMdns.AnnounceCount; $announce++) {
                                    if ($announce -gt 1) { & $Sleep $SlateOpsMdns.AnnounceWaitMs }
                                    & $socket.Send (New-MdnsAnswer -QueryName $Name -Ip $ip) 'group'
                                }
                                $answering = $true
                                & $Log 'INFO' ('mDNS: {0} is {1} on this network' -f $Name, $ip)
                            }
                        }
                    }
                }
            }
            if (-not $answering) { & $Sleep $SlateOpsMdns.ReceiveMs; continue }
            $packet = & $socket.Receive $SlateOpsMdns.ReceiveMs
            if (-not $packet) { continue }
            $action = Get-MdnsAction -Data $packet.data -Name $Name
            if (-not $action) { continue }
            $answer = New-MdnsAnswer -QueryName $Name -Ip $current
            & $socket.Send $answer 'group'
            if ($action -eq 'group unicast') { & $socket.Send $answer ([string]$packet.remote) }
            $answered++
        }
    } finally {
        if ($socket) { & $socket.Close }
    }
}

function New-MdnsSocket {
    # The real socket: UDP 5353 shared with Windows' responder (ReuseAddress, as the spike bound
    # it), joined to the group on the adapter address Ip, multicast sent from that adapter.
    param([Parameter(Mandatory = $true)][string]$Ip)
    $udp = New-Object System.Net.Sockets.UdpClient
    $udp.ExclusiveAddressUse = $false
    $udp.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::Socket, [System.Net.Sockets.SocketOptionName]::ReuseAddress, $true)
    $udp.Client.Bind((New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, $SlateOpsMdns.Port)))
    $local = [System.Net.IPAddress]::Parse($Ip)
    $udp.JoinMulticastGroup([System.Net.IPAddress]::Parse($SlateOpsMdns.Group), $local)
    $udp.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IP, [System.Net.Sockets.SocketOptionName]::MulticastInterface, $local.GetAddressBytes())
    $group = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($SlateOpsMdns.Group), $SlateOpsMdns.Port)
    return @{
        Send = {
            param([byte[]]$Data, [string]$To)
            if ($To -eq 'group') { $null = $udp.Send($Data, $Data.Length, $group); return }
            $parts = $To.Split(':')
            $null = $udp.Send($Data, $Data.Length, (New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($parts[0]), [int]$parts[1])))
        }.GetNewClosure()
        Receive = {
            param([int]$TimeoutMs)
            $udp.Client.ReceiveTimeout = $TimeoutMs
            $remote = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
            try { $data = $udp.Receive([ref]$remote) } catch { return $null }
            return @{ data = $data; remote = $remote.ToString() }
        }.GetNewClosure()
        Close = { $udp.Close() }.GetNewClosure()
    }
}

function Start-MdnsResponderThread {
    # start.ps1: the responder on a thread of the boot task's own process (a second runspace), so
    # the process that the firewall rule names is the one that answers, and the responder ends
    # with it. It logs to the same boot run log. Returns the PowerShell object, which the caller
    # keeps for the life of the process.
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$LogDir,
        [Parameter(Mandatory = $true)][string]$LibDir
    )
    if (-not (Test-AddressLabel $Label)) { throw 'label_invalid' }
    $worker = [PowerShell]::Create()
    $null = $worker.AddScript({
        param($LibDir, $RunId, $LogDir, $Name)
        foreach ($lib in @('Common', 'Checks', 'Mdns')) { . (Join-Path $LibDir ('{0}.ps1' -f $lib)) }
        Start-RunLog -RunId $RunId -Directory $LogDir -Append -NoConsole
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            Invoke-MdnsResponder -Name $Name `
                -GetAddress { $lan = Get-LanFact; if ($lan) { [string]$lan.address } else { $null } } `
                -OpenSocket { param([string]$Ip) New-MdnsSocket -Ip $Ip } `
                -Clock { $watch.ElapsedMilliseconds } `
                -Sleep { param([int]$Ms) Start-Sleep -Milliseconds $Ms } `
                -Until { $false } `
                -Log { param($Level, $Text) Write-RunLog 'boot.mdns' $Level $Text }
        } catch { Write-RunLog 'boot.mdns' 'ERROR' ('mDNS responder stopped: {0}' -f $_.Exception.Message) }
    }).AddArgument($LibDir).AddArgument($RunId).AddArgument($LogDir).AddArgument(('{0}.local' -f $Label))
    $null = $worker.BeginInvoke()
    return $worker
}
