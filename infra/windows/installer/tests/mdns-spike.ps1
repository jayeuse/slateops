<#
mdns-spike.ps1 - the DEC-0039 CI spike (TASK-0097): can a limited account, run by a scheduled
task as slateops-svc is, announce a host name that is not the computer name?

Check 1 (the design): the account calls DnsServiceRegister (dnsapi.dll, through a small C#
wrapper for DnsServiceConstructInstance, DnsServiceRegister and DnsServiceDeRegister) for
slateops-ci-<tag>.local with the runner's IPv4 address and holds the registration. The
administrator side then asks for the name with Resolve-DnsName, with System.Net.Dns (the
getaddrinfo path that browsers use) and with raw mDNS queries (QU: the answer comes back to the
asking port; QM: the answer goes to 224.0.0.251:5353, where a listener of this side takes it),
which accept this PC's own answer.
Check 2 (the fallback): a small responder in the same account binds UDP 5353 next to Windows'
own responder, joins 224.0.0.251 and answers for slateops-ci-<tag>-fb.local. The administrator
side asks once with no firewall rule and once with one inbound UDP 5353 rule for the program
(the fallback's one new rule).
Control: the same queries for this runner's own computer name, so a runner that answers no mDNS
query at all shows as INCONCLUSIVE, not as FAIL.

Verdicts per check: PASS (same PC only; a second LAN device proves the design), FAIL, or
INCONCLUSIVE, with the evidence. A verdict never fails the job: exit code 1 only when the spike
itself could not run (the account, the tasks, the folders).

It creates a local account and two scheduled tasks, so it runs only on a GitHub Actions Windows
runner, as an administrator. The account's random password reaches only Register-ScheduledTask;
it is never printed or stored. It is not a *.Tests.ps1 file, so run-tests.ps1 never runs it.

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File mdns-spike.ps1

The tasks run this same file with -Role register or -Role responder.
Windows PowerShell 5.1, ASCII only.
#>
[CmdletBinding()]
param(
    [ValidateSet('', 'register', 'responder')][string]$Role = '',
    [string]$Name = '',
    [string]$Address = '',
    [int]$InterfaceIndex = 0,
    [string]$OutDir = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$MdnsGroup = '224.0.0.251'

# ---------------------------------------------------------------------------
# DNS messages (RFC 1035, RFC 6762): only what the spike needs
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
    # One question, type A, class IN; -Unicast sets the QU bit (RFC 6762 5.4).
    param([Parameter(Mandatory = $true)][string]$QueryName, [switch]$Unicast)
    $bytes = New-Object System.Collections.Generic.List[byte]
    $bytes.AddRange([byte[]](0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0))
    $bytes.AddRange((ConvertTo-DnsName $QueryName))
    $bytes.AddRange([byte[]](0, 1))
    if ($Unicast) { $bytes.AddRange([byte[]](0x80, 1)) } else { $bytes.AddRange([byte[]](0, 1)) }
    return , $bytes.ToArray()
}

function New-MdnsAnswer {
    # One A record, cache-flush class, TTL 120 (RFC 6762 10.2).
    param([Parameter(Mandatory = $true)][string]$QueryName, [Parameter(Mandatory = $true)][string]$Ip)
    $bytes = New-Object System.Collections.Generic.List[byte]
    $bytes.AddRange([byte[]](0, 0, 0x84, 0, 0, 0, 0, 1, 0, 0, 0, 0))
    $bytes.AddRange((ConvertTo-DnsName $QueryName))
    $bytes.AddRange([byte[]](0, 1, 0x80, 1, 0, 0, 0, 120, 0, 4))
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
            if ($next -lt 0) { $next = $pos + 2 }
            $pos = (($length -band 0x3F) * 256) + [int]$Data[$pos + 1]
            $jumps++
            if ($jumps -gt 32) { throw 'dns_loop' }
            continue
        }
        $labels.Add([System.Text.Encoding]::ASCII.GetString($Data, $pos + 1, $length))
        $pos += 1 + $length
    }
    if ($next -lt 0) { $next = $pos }
    return @{ name = ($labels.ToArray() -join '.'); next = $next }
}

function Get-DnsMessage {
    # @{ response; questions = @(@{name; type; unicast}); addresses = @(@{name; ip}) }
    param([Parameter(Mandatory = $true)][byte[]]$Data)
    if ($Data.Length -lt 12) { throw 'dns_short' }
    $flags = ([int]$Data[2] * 256) + [int]$Data[3]
    $questionCount = ([int]$Data[4] * 256) + [int]$Data[5]
    $recordCount = (([int]$Data[6] * 256) + [int]$Data[7]) + (([int]$Data[8] * 256) + [int]$Data[9]) + (([int]$Data[10] * 256) + [int]$Data[11])
    $pos = 12
    $questions = @()
    for ($i = 0; $i -lt $questionCount; $i++) {
        $read = Read-DnsName -Data $Data -Offset $pos
        $pos = $read.next
        $type = ([int]$Data[$pos] * 256) + [int]$Data[$pos + 1]
        $unicast = (([int]$Data[$pos + 2] -band 0x80) -ne 0)
        $pos += 4
        $questions += @{ name = $read.name; type = $type; unicast = $unicast }
    }
    $addresses = @()
    for ($i = 0; $i -lt $recordCount; $i++) {
        $read = Read-DnsName -Data $Data -Offset $pos
        $pos = $read.next
        $type = ([int]$Data[$pos] * 256) + [int]$Data[$pos + 1]
        $length = ([int]$Data[$pos + 8] * 256) + [int]$Data[$pos + 9]
        if (($type -eq 1) -and ($length -eq 4)) { $addresses += @{ name = $read.name; ip = ('{0}.{1}.{2}.{3}' -f $Data[$pos + 10], $Data[$pos + 11], $Data[$pos + 12], $Data[$pos + 13]) } }
        $pos += 10 + $length
    }
    return @{ response = (($flags -band 0x8000) -ne 0); questions = $questions; addresses = $addresses }
}

function Get-SocketErrorText {
    param([Parameter(Mandatory = $true)]$ErrorRecord)
    $exception = $ErrorRecord.Exception
    while ($null -ne $exception) {
        if ($exception -is [System.Net.Sockets.SocketException]) { return ('{0} ({1})' -f $exception.SocketErrorCode, $exception.ErrorCode) }
        $exception = $exception.InnerException
    }
    return $ErrorRecord.Exception.Message
}

function New-Mdns5353Socket {
    # A shared UDP 5353 socket joined to the mDNS group on one interface address.
    param([Parameter(Mandatory = $true)][string]$Ip)
    $udp = New-Object System.Net.Sockets.UdpClient
    $udp.ExclusiveAddressUse = $false
    $udp.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::Socket, [System.Net.Sockets.SocketOptionName]::ReuseAddress, $true)
    $udp.Client.Bind((New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 5353)))
    $udp.JoinMulticastGroup([System.Net.IPAddress]::Parse($MdnsGroup), [System.Net.IPAddress]::Parse($Ip))
    return $udp
}

# ---------------------------------------------------------------------------
# The task side: runs as the limited account
# ---------------------------------------------------------------------------

function Write-RoleLog {
    param([Parameter(Mandatory = $true)][string]$Text)
    $line = '{0} {1}' -f ([DateTime]::UtcNow.ToString('o')), $Text
    [System.IO.File]::AppendAllText((Join-Path $OutDir ('{0}.log' -f $Role)), $line + "`r`n", [System.Text.Encoding]::ASCII)
}

if ($Role -eq 'register') {
    try {
        Write-RoleLog ('start as {0}' -f [Security.Principal.WindowsIdentity]::GetCurrent().Name)
        $source = @'
using System;
using System.Net;
using System.Runtime.InteropServices;
using System.Threading;

namespace SlateOpsSpike
{
    public static class Mdns
    {
        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        public delegate void Complete(uint status, IntPtr context, IntPtr instance);

        [StructLayout(LayoutKind.Sequential)]
        private struct RegisterRequest
        {
            public uint Version;
            public uint InterfaceIndex;
            public IntPtr ServiceInstance;
            public IntPtr Callback;
            public IntPtr Context;
            public IntPtr Credentials;
            public int UnicastEnabled;
        }

        [DllImport("dnsapi.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr DnsServiceConstructInstance(string serviceName, string hostName, IntPtr ip4, IntPtr ip6,
            ushort port, ushort priority, ushort weight, uint propertiesCount, IntPtr keys, IntPtr values);
        [DllImport("dnsapi.dll")] private static extern uint DnsServiceRegister(IntPtr request, IntPtr cancel);
        [DllImport("dnsapi.dll")] private static extern uint DnsServiceDeRegister(IntPtr request, IntPtr cancel);
        [DllImport("dnsapi.dll")] private static extern void DnsServiceFreeInstance(IntPtr instance);

        // Kept for the life of the process: the callback, the request and the address.
        private static readonly Complete Callback = OnComplete;
        private static IntPtr request = IntPtr.Zero;
        private static IntPtr address = IntPtr.Zero;
        public static readonly ManualResetEvent Done = new ManualResetEvent(false);
        public static uint LastStatus = 0xFFFFFFFF;

        private static void OnComplete(uint status, IntPtr context, IntPtr instance)
        {
            LastStatus = status;
            if (instance != IntPtr.Zero) { DnsServiceFreeInstance(instance); }
            Done.Set();
        }

        // DNS_REQUEST_PENDING (9506) means the registration started; the callback gives the status.
        public static uint Register(string serviceName, string hostName, string ip, uint interfaceIndex, ushort port)
        {
            byte[] bytes = IPAddress.Parse(ip).GetAddressBytes();
            address = Marshal.AllocHGlobal(4);
            Marshal.Copy(bytes, 0, address, 4);
            IntPtr instance = DnsServiceConstructInstance(serviceName, hostName, address, IntPtr.Zero, port, 0, 0, 0, IntPtr.Zero, IntPtr.Zero);
            if (instance == IntPtr.Zero) { return 0xFFFFFFFE; }
            RegisterRequest value = new RegisterRequest();
            value.Version = 1;
            value.InterfaceIndex = interfaceIndex;
            value.ServiceInstance = instance;
            value.Callback = Marshal.GetFunctionPointerForDelegate(Callback);
            request = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(RegisterRequest)));
            Marshal.StructureToPtr(value, request, false);
            Done.Reset();
            return DnsServiceRegister(request, IntPtr.Zero);
        }

        public static uint DeRegister()
        {
            Done.Reset();
            return DnsServiceDeRegister(request, IntPtr.Zero);
        }
    }
}
'@
        Add-Type -TypeDefinition $source -Language CSharp
        $service = '{0}._http._tcp.local' -f $Name.Split('.')[0]
        $call = [SlateOpsSpike.Mdns]::Register($service, $Name, $Address, [uint32]$InterfaceIndex, [uint16]443)
        Write-RoleLog ('register call {0} (9506 = DNS_REQUEST_PENDING) for {1} host {2} address {3} interface {4}' -f $call, $service, $Name, $Address, $InterfaceIndex)
        if ([SlateOpsSpike.Mdns]::Done.WaitOne(30000)) { Write-RoleLog ('register callback status {0}' -f [SlateOpsSpike.Mdns]::LastStatus) }
        else { Write-RoleLog 'register callback none in 30 s' }
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        while ((-not (Test-Path -LiteralPath (Join-Path $OutDir 'stop-register'))) -and ($watch.Elapsed.TotalSeconds -lt 300)) { Start-Sleep -Milliseconds 500 }
        $call = [SlateOpsSpike.Mdns]::DeRegister()
        Write-RoleLog ('deregister call {0}' -f $call)
        if ([SlateOpsSpike.Mdns]::Done.WaitOne(10000)) { Write-RoleLog ('deregister callback status {0}' -f [SlateOpsSpike.Mdns]::LastStatus) }
        else { Write-RoleLog 'deregister callback none in 10 s' }
        Write-RoleLog 'end'
    } catch { Write-RoleLog ('error {0}' -f $_.Exception.Message) }
    exit 0
}

if ($Role -eq 'responder') {
    try {
        Write-RoleLog ('start as {0}' -f [Security.Principal.WindowsIdentity]::GetCurrent().Name)
        try { $udp = New-Mdns5353Socket -Ip $Address }
        catch {
            Write-RoleLog ('bind failed {0}' -f (Get-SocketErrorText $_))
            exit 0
        }
        Write-RoleLog 'bound UDP 5353 and joined 224.0.0.251'
        $udp.Client.ReceiveTimeout = 1000
        $group = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($MdnsGroup), 5353)
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        while ((-not (Test-Path -LiteralPath (Join-Path $OutDir 'stop-responder'))) -and ($watch.Elapsed.TotalSeconds -lt 300)) {
            $remote = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
            try { $data = $udp.Receive([ref]$remote) } catch { continue }
            try { $message = Get-DnsMessage -Data $data } catch { Write-RoleLog ('received {0} bytes from {1}, not parsed' -f $data.Length, $remote); continue }
            if ($message.response) { continue }
            foreach ($question in $message.questions) {
                $mine = ($question.name -ieq $Name) -and (@(1, 255) -contains $question.type)
                Write-RoleLog ('received query from {0} for {1} type {2} unicast {3}{4}' -f $remote, $question.name, $question.type, $question.unicast, $(if ($mine) { ' (target)' } else { '' }))
                if (-not $mine) { continue }
                $answer = New-MdnsAnswer -QueryName $Name -Ip $Address
                $null = $udp.Send($answer, $answer.Length, $group)
                if ($question.unicast) { $null = $udp.Send($answer, $answer.Length, $remote) }
                Write-RoleLog ('answered {0} with {1}' -f $Name, $Address)
            }
        }
        $udp.Close()
        Write-RoleLog 'end'
    } catch { Write-RoleLog ('error {0}' -f $_.Exception.Message) }
    exit 0
}

# ---------------------------------------------------------------------------
# The administrator side
# ---------------------------------------------------------------------------

if (($env:GITHUB_ACTIONS -ne 'true') -or (-not $env:RUNNER_TEMP)) {
    Write-Host 'FAIL  mdns-spike.ps1 runs only on a GitHub Actions Windows runner: it creates a local account.'
    exit 1
}

$script:Clock = [System.Diagnostics.Stopwatch]::StartNew()
function Write-Line {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    Write-Host ('[{0,6:N1}s] {1}' -f ($script:Clock.Elapsed.TotalSeconds), $Text)
}

function Invoke-MdnsQuery {
    # Sends one query from an own port and collects answers for $QueryName for WaitMs from that port
    # (QU answers) and from a shared 5353 listener (QM answers). Returns @{ ips; responders; note }.
    param([Parameter(Mandatory = $true)][string]$QueryName, [Parameter(Mandatory = $true)][string]$Ip, [switch]$Unicast, [int]$WaitMs = 3000)
    $ips = New-Object System.Collections.Generic.List[string]
    $responders = New-Object System.Collections.Generic.List[string]
    $note = ''
    $sender = New-Object System.Net.Sockets.UdpClient((New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($Ip), 0)))
    $listener = $null
    try {
        $sender.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IP, [System.Net.Sockets.SocketOptionName]::MulticastInterface, [System.Net.IPAddress]::Parse($Ip).GetAddressBytes())
        $sender.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IP, [System.Net.Sockets.SocketOptionName]::MulticastTimeToLive, 255)
        $sender.MulticastLoopback = $true
        try { $listener = New-Mdns5353Socket -Ip $Ip } catch { $note = 'QM listener not bound: ' + (Get-SocketErrorText $_) }
        $query = New-MdnsQuery -QueryName $QueryName -Unicast:$Unicast
        $null = $sender.Send($query, $query.Length, (New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($MdnsGroup), 5353)))
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        while ($watch.ElapsedMilliseconds -lt $WaitMs) {
            $got = $false
            foreach ($socket in @($sender, $listener)) {
                if (($null -eq $socket) -or ($socket.Available -le 0)) { continue }
                $got = $true
                $remote = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
                $data = $socket.Receive([ref]$remote)
                try { $message = Get-DnsMessage -Data $data } catch { continue }
                if (-not $message.response) { continue }
                foreach ($record in $message.addresses) {
                    if ($record.name -ieq $QueryName) {
                        $ips.Add($record.ip)
                        $responders.Add([string]$remote)
                    }
                }
            }
            if (-not $got) { Start-Sleep -Milliseconds 50 }
        }
    } finally {
        $sender.Close()
        if ($null -ne $listener) { $listener.Close() }
    }
    return @{ ips = @($ips.ToArray() | Select-Object -Unique); responders = @($responders.ToArray() | Select-Object -Unique); note = $note }
}

function Test-Name {
    # Every resolver path for one name. Returns the list of evidence lines and whether any path
    # gave the expected address.
    param([Parameter(Mandatory = $true)][string]$QueryName, [Parameter(Mandatory = $true)][string]$Ip, [string]$Expected = '')
    $lines = New-Object System.Collections.Generic.List[string]
    $hit = $false
    # Only raw mDNS answers count for the control: Resolve-DnsName and System.Net.Dns can answer
    # this PC's own name with no packet on the network.
    $raw = $false
    try {
        $records = @(Resolve-DnsName -Name $QueryName -Type A -ErrorAction Stop | Where-Object { $_.PSObject.Properties['IPAddress'] -and ($_.Type -eq 'A') } | ForEach-Object { $_.IPAddress })
        $lines.Add(('Resolve-DnsName {0}: {1}' -f $QueryName, ($records -join ', ')))
        if ($Expected -and ($records -contains $Expected)) { $hit = $true }
    } catch { $lines.Add(('Resolve-DnsName {0}: {1}' -f $QueryName, $_.Exception.Message)) }
    try {
        $records = @([System.Net.Dns]::GetHostAddresses($QueryName) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | ForEach-Object { $_.ToString() })
        $lines.Add(('System.Net.Dns {0}: {1}' -f $QueryName, ($records -join ', ')))
        if ($Expected -and ($records -contains $Expected)) { $hit = $true }
    } catch { $lines.Add(('System.Net.Dns {0}: {1}' -f $QueryName, $_.Exception.Message)) }
    foreach ($unicast in @($true, $false)) {
        $kind = $(if ($unicast) { 'QU' } else { 'QM' })
        try {
            $answer = Invoke-MdnsQuery -QueryName $QueryName -Ip $Ip -Unicast:$unicast
            $lines.Add(('raw mDNS {0} {1}: addresses [{2}] from [{3}] {4}' -f $kind, $QueryName, ($answer.ips -join ', '), ($answer.responders -join ', '), $answer.note))
            if ($answer.ips.Count -gt 0) { $raw = $true }
            if ($Expected -and ($answer.ips -contains $Expected)) { $hit = $true }
        } catch { $lines.Add(('raw mDNS {0} {1}: {2}' -f $kind, $QueryName, (Get-SocketErrorText $_))) }
    }
    foreach ($line in $lines) { Write-Line ('  ' + $line) }
    return @{ hit = $hit; raw = $raw; lines = $lines.ToArray() }
}

function Wait-LogLine {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string[]]$Like, [int]$LimitSeconds = 90)
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt $LimitSeconds) {
        if (Test-Path -LiteralPath $Path) {
            foreach ($line in @(Get-Content -LiteralPath $Path)) { foreach ($pattern in $Like) { if ($line -like $pattern) { return $line } } }
        }
        Start-Sleep -Milliseconds 500
    }
    return ''
}

function Show-RoleLog {
    param([Parameter(Mandatory = $true)][string]$Path)
    Write-Line ('----- {0}' -f $Path)
    if (Test-Path -LiteralPath $Path) { Get-Content -LiteralPath $Path | ForEach-Object { Write-Host ('  ' + $_) } } else { Write-Host '  absent' }
}

$accountName = 'slateops-spike'
$taskPath = '\SlateOpsSpike\'
$ruleName = 'SlateOps-CI-spike-mDNS-UDP-5353'
$tag = ([guid]::NewGuid().ToString('N')).Substring(0, 8)
$target = 'slateops-ci-{0}.local' -f $tag
$fallback = 'slateops-ci-{0}-fb.local' -f $tag
$workDir = Join-Path $env:SystemDrive ('SlateOpsSpike-{0}' -f $tag)
$outDir = Join-Path $workDir 'out'
$owned = $false
$verdicts = New-Object System.Collections.Generic.List[string]
$faults = New-Object System.Collections.Generic.List[string]
$exitCode = 1
try {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Not an administrator.' }
    if (Get-LocalUser -Name $accountName -ErrorAction SilentlyContinue) { throw ('The account {0} exists already.' -f $accountName) }
    $owned = $true

    # The runner's LAN-side address: the interface of the default route.
    $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object -Property RouteMetric, InterfaceMetric | Select-Object -First 1
    $ifIndex = [int]$route.InterfaceIndex
    $ip = [string](Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $ifIndex | Select-Object -First 1).IPAddress
    $computer = ('{0}.local' -f [Environment]::MachineName).ToLowerInvariant()
    Write-Line ('{0}; interface {1}; IPv4 {2}; computer name {3}; target {4}; fallback name {5}' -f [Environment]::OSVersion.VersionString, $ifIndex, $ip, $computer, $target, $fallback)
    try { Write-Line ('network category: {0}' -f ((Get-NetConnectionProfile -InterfaceIndex $ifIndex -ErrorAction Stop | ForEach-Object { '{0} ({1})' -f $_.Name, $_.NetworkCategory }) -join '; ')) } catch { Write-Line ('network category: {0}' -f $_.Exception.Message) }
    $mdnsSetting = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters' -Name 'EnableMDNS' -ErrorAction SilentlyContinue
    Write-Line ('Dnscache EnableMDNS: {0}' -f $(if ($mdnsSetting) { $mdnsSetting.EnableMDNS } else { 'not set (default on)' }))
    foreach ($rule in @(Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like '*mDNS*' })) { Write-Line ('firewall rule {0}: {1}, enabled {2}, profile {3}, action {4}' -f $rule.DisplayName, $rule.Direction, $rule.Enabled, $rule.Profile, $rule.Action) }
    foreach ($endpoint in @(Get-NetUDPEndpoint -LocalPort 5353 -ErrorAction SilentlyContinue)) {
        $process = Get-Process -Id $endpoint.OwningProcess -ErrorAction SilentlyContinue
        Write-Line ('UDP 5353 endpoint {0} owned by {1} ({2})' -f $endpoint.LocalAddress, $endpoint.OwningProcess, $(if ($process) { $process.ProcessName } else { '?' }))
    }

    # The work folder: Users read it (inherited from the system drive); the account writes out\.
    [void][System.IO.Directory]::CreateDirectory($outDir)
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $workDir 'mdns-spike.ps1')

    # The limited account, as slateops-svc: Users only, batch logon right, random password that
    # reaches only Register-ScheduledTask (lib/Service.ps1 helpers, read only).
    $lib = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\lib'
    foreach ($file in @('Common', 'Service')) { . (Join-Path $lib ('{0}.ps1' -f $file)) }
    $password = New-RandomPassword
    try {
        $user = New-LocalUser -Name $accountName -Password (ConvertTo-SecureText -Text $password) -Description 'Slate Operations CI spike' -PasswordNeverExpires -AccountNeverExpires
        try { Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $user } catch [Microsoft.PowerShell.Commands.MemberExistsException] { $null = $_ }
        $sid = $user.SID.Value
        Initialize-LsaRightsType
        [SlateOpsSetup.LsaRights]::Add($sid, [string[]]@('SeBatchLogonRight'))
        $acl = Get-Acl -LiteralPath $outDir
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule((New-Object System.Security.Principal.SecurityIdentifier($sid)), 'Modify', 'ContainerInherit, ObjectInherit', 'None', 'Allow')))
        Set-Acl -LiteralPath $outDir -AclObject $acl
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $powershell = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
        foreach ($role in @('register', 'responder')) {
            $hostName = $(if ($role -eq 'register') { $target } else { $fallback })
            $arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -Role {1} -Name {2} -Address {3} -InterfaceIndex {4} -OutDir "{5}"' -f (Join-Path $workDir 'mdns-spike.ps1'), $role, $hostName, $ip, $ifIndex, $outDir
            $action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments
            Register-ScheduledTask -TaskPath $taskPath -TaskName $role -Action $action -Settings $settings -User ('{0}\{1}' -f [Environment]::MachineName, $accountName) -Password $password -RunLevel Limited -Force | Out-Null
        }
    } finally { $password = $null }
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName 'register'
    Write-Line ('tasks run as {0} ({1}, {2})' -f $task.Principal.UserId, $task.Principal.LogonType, $task.Principal.RunLevel)

    Write-Line '---- control: this runner''s own computer name (Windows answers it if it answers any mDNS query)'
    $control = Test-Name -QueryName $computer -Ip $ip

    Write-Line ('---- check 1: DnsServiceRegister in the account for {0} -> {1}' -f $target, $ip)
    $registerLog = Join-Path $outDir 'register.log'
    Start-ScheduledTask -TaskPath $taskPath -TaskName 'register'
    $line = Wait-LogLine -Path $registerLog -Like @('* register callback *', '* error *')
    $call = ''
    $status = ''
    foreach ($entry in @(Get-Content -LiteralPath $registerLog -ErrorAction SilentlyContinue)) {
        if ($entry -match ' register call ([0-9]+) ') { $call = $Matches[1] }
        if ($entry -match ' register callback status ([0-9]+)$') { $status = $Matches[1] }
        if ($entry -like '* register callback none *') { $status = 'none' }
    }
    $first = $null
    $later = $null
    if ($status -eq '0') {
        Start-Sleep -Seconds 3
        $first = Test-Name -QueryName $target -Ip $ip -Expected $ip
        Start-Sleep -Seconds 5
        $later = Test-Name -QueryName $target -Ip $ip -Expected $ip
    }
    [System.IO.File]::WriteAllText((Join-Path $outDir 'stop-register'), 'stop')
    $null = Wait-LogLine -Path $registerLog -Like @('* end', '* error *') -LimitSeconds 30
    Show-RoleLog -Path $registerLog
    # FAIL only on the API's own answer; no answer at all is a fault of this spike.
    if ($call -eq '') { $faults.Add(('check 1: the register task gave no register call line (last line: {0})' -f $line)) }
    elseif ($call -ne '9506') { $verdicts.Add(('FAIL  check 1 DnsServiceRegister: the call returned {0}, not 9506 DNS_REQUEST_PENDING' -f $call)) }
    elseif ($status -eq 'none') { $verdicts.Add('INCONCLUSIVE  check 1 DnsServiceRegister: the call is pending, but no completion callback came in 30 s') }
    elseif ($status -ne '0') { $verdicts.Add(('FAIL  check 1 DnsServiceRegister: the completion callback gave status {0}' -f $status)) }
    elseif ($first.hit -or $later.hit) { $verdicts.Add(('PASS  check 1 DnsServiceRegister: {0} answers {1} on this PC (same PC only; a second LAN device proves the design)' -f $target, $ip)) }
    elseif (-not $control.raw) { $verdicts.Add('INCONCLUSIVE  check 1 DnsServiceRegister: registered (status 0), but this runner gives no raw mDNS answer, not even for its computer name') }
    else { $verdicts.Add(('INCONCLUSIVE  check 1 DnsServiceRegister: registered (status 0) and the computer name answers raw mDNS, but no path gave {0} for {1} (the assumption that Windows answers a registered non-computer host name is not shown here)' -f $ip, $target)) }

    Write-Line ('---- check 2: own responder in the account on UDP 5353 next to Windows'' responder, for {0}' -f $fallback)
    $responderLog = Join-Path $outDir 'responder.log'
    Start-ScheduledTask -TaskPath $taskPath -TaskName 'responder'
    $bound = Wait-LogLine -Path $responderLog -Like @('* bound *', '* bind failed *', '* error *')
    foreach ($endpoint in @(Get-NetUDPEndpoint -LocalPort 5353 -ErrorAction SilentlyContinue)) {
        $process = Get-Process -Id $endpoint.OwningProcess -ErrorAction SilentlyContinue
        Write-Line ('UDP 5353 endpoint {0} owned by {1} ({2})' -f $endpoint.LocalAddress, $endpoint.OwningProcess, $(if ($process) { $process.ProcessName } else { '?' }))
    }
    $rounds = @()
    if ($bound -like '* bound *') {
        Write-Line '  round 1: no firewall rule for the responder'
        $noRule = Test-Name -QueryName $fallback -Ip $ip -Expected $ip
        Start-Sleep -Seconds 1
        $receivedNoRule = @(Get-Content -LiteralPath $responderLog | Where-Object { $_ -like ('* received query * for {0} *' -f $fallback) }).Count
        New-NetFirewallRule -DisplayName $ruleName -Name $ruleName -Direction Inbound -Protocol UDP -LocalPort 5353 -Program $powershell -Action Allow -Profile Any | Out-Null
        Write-Line ('  round 2: inbound UDP 5353 rule {0} for {1}' -f $ruleName, $powershell)
        $withRule = Test-Name -QueryName $fallback -Ip $ip -Expected $ip
        Start-Sleep -Seconds 1
        $receivedAll = @(Get-Content -LiteralPath $responderLog | Where-Object { $_ -like ('* received query * for {0} *' -f $fallback) }).Count
        $rounds = @(('no rule: queries received {0}, answer seen {1}' -f $receivedNoRule, $noRule.hit), ('with rule: queries received {0}, answer seen {1}' -f ($receivedAll - $receivedNoRule), $withRule.hit))
    }
    [System.IO.File]::WriteAllText((Join-Path $outDir 'stop-responder'), 'stop')
    $null = Wait-LogLine -Path $responderLog -Like @('* end', '* error *', '* bind failed *') -LimitSeconds 30
    Show-RoleLog -Path $responderLog
    if ($bound -like '* bind failed *') { $verdicts.Add(('FAIL  check 2 own responder: it could not bind UDP 5353 next to Windows'' responder ({0})' -f $bound)) }
    elseif ($bound -notlike '* bound *') { $faults.Add(('check 2: the responder task gave no bind line (last line: {0})' -f $bound)) }
    elseif ($rounds.Count -gt 0) {
        $received = @(Get-Content -LiteralPath $responderLog | Where-Object { $_ -like ('* received query * for {0} *' -f $fallback) }).Count
        if ($received -gt 0) { $verdicts.Add(('PASS  check 2 own responder: bound UDP 5353 and received the multicast query ({0}) (same PC only)' -f ($rounds -join '; '))) }
        elseif (-not $control.raw) { $verdicts.Add(('INCONCLUSIVE  check 2 own responder: bound UDP 5353 but received no query, and this runner gives no raw mDNS answer at all ({0})' -f ($rounds -join '; '))) }
        else { $verdicts.Add(('INCONCLUSIVE  check 2 own responder: bound UDP 5353 but received no query ({0})' -f ($rounds -join '; '))) }
    }
    if ($faults.Count -gt 0) {
        foreach ($role in @('register', 'responder')) {
            try {
                $info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $role -ErrorAction Stop
                Write-Line ('task {0}{1}: last run {2:o}, last result 0x{3:X8}' -f $taskPath, $role, $info.LastRunTime, ([long]$info.LastTaskResult -band 4294967295L))
            } catch { Write-Line ('task {0}{1}: {2}' -f $taskPath, $role, $_.Exception.Message) }
        }
        throw ('the spike itself failed: {0}' -f ($faults -join '; '))
    }
    $exitCode = 0
} catch {
    Write-Line ('ERROR the spike could not run: {0}' -f $_.Exception.Message)
    if ($_.InvocationInfo) { Write-Host $_.InvocationInfo.PositionMessage }
} finally {
    if ($owned) {
        foreach ($role in @('register', 'responder')) {
            Stop-ScheduledTask -TaskPath $taskPath -TaskName $role -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskPath $taskPath -TaskName $role -Confirm:$false -ErrorAction SilentlyContinue
        }
        try {
            $schedule = New-Object -ComObject 'Schedule.Service'
            $schedule.Connect()
            $schedule.GetFolder('\').DeleteFolder('SlateOpsSpike', 0)
        } catch { $null = $_ }
        Remove-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
        $user = Get-LocalUser -Name $accountName -ErrorAction SilentlyContinue
        if ($user) {
            Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $user.SID.Value) -ErrorAction SilentlyContinue | Remove-CimInstance -ErrorAction SilentlyContinue
            Remove-LocalUser -Name $accountName -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

Write-Host '===== DEC-0039 spike verdicts'
if ($verdicts.Count -eq 0) { Write-Host 'none: the spike did not reach a check' }
$verdicts | ForEach-Object { Write-Host $_ }
exit $exitCode
