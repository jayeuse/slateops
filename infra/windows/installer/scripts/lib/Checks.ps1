# Checks.ps1 - the PC check (wizard spec 5.1 to 5.3, checks C01 to C30; plan 4.2 R1 to R9).
#
# Two halves:
# - Test-C01 ... Test-C30 decide one check each from a facts hashtable. They read nothing from
#   Windows, so tests drive them with controlled inputs.
# - Get-PcCheckFacts reads Windows (read-only; it changes nothing on the PC) and fills the
#   facts. A value that cannot be read is $null.
# Each result is @{ id; class; code; message_key; values }. class: pass, stop, fix, advice, auto
# or log. The wizard (W8) maps message_key and values to the spec's copy.
# C16 (mDNS probe) and C17 (DNS Client, multicast policy, mDNS rule) are F1 checks whose names
# W8 checks in Microsoft's documentation (plan 10.3 F1, spec C17); W8 adds them.
# Windows PowerShell 5.1, ASCII only.

$SlateOpsCheck = @{
    # C05: TotalPhysicalMemory >= 12 GiB (spec C05; Software Architect decision, TASK-0080).
    MinUsableMemoryBytes = [long]12884901888
    # C07: 15 GB free on one fixed NTFS drive (spec C07 planning value). GiB, as Windows shows it.
    MinFreeBytes         = [long]15 * 1GB
    # C13: 30 seconds (spec C13 planning value).
    MaxClockOffsetSec    = 30
    # C30: Windows' generated computer names (spec C30; pattern is an Assumption, W14 checks it).
    FactoryNamePattern   = '^(DESKTOP|LAPTOP)-[A-Z0-9]{7}$'
    # C02: the kit's edition rule (precheck): Pro, Enterprise or Education families.
    EditionPattern       = '^(Professional|Enterprise|Education)'
    # The checks that run again on S06 and on Install in S11 (spec 5.2).
    RecheckIds           = @('C08', 'C09', 'C10', 'C12', 'C13', 'C14', 'C21')
    # Plan R-checks whose unreadable value is Advice "cannot read" (spec 5.2; C18 is Fix).
    RequirementIds       = @('C01', 'C02', 'C04', 'C05', 'C07', 'C10', 'C11', 'C12', 'C15', 'C16', 'C17', 'C21')
    # C17 (plan F1; W8): the built-in inbound mDNS rules. The names are an Assumption from
    # Windows 11's built-in rule set ("MDNS-In-UDP-<profile>-Active"); W14 shows them.
    MdnsRulePattern      = 'MDNS-In-UDP*'
    DnsClientPolicyKey   = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient'
    # Uninstall key of the installed program (Inno AppId, see SlateOpsSetup.iss).
    UninstallKey         = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8B0C1D7E-3F4A-4E52-9A61-5C2D7B9E0F13}_is1'
    Kit = @{
        AccountName = 'slateops-svc'
        Root        = (Join-Path $SlateOpsPaths.ProgramData 'SlateOpsBootTest')
        TaskPath    = '\SlateOpsBootTest\'
        RuleName    = 'SlateOpsBootTest-TCP-8443'
        HyperVRule  = 'SlateOpsBootTest-HyperV-TCP-8443'
    }
}

function New-CheckResult {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][ValidateSet('pass', 'stop', 'fix', 'advice', 'auto', 'log')][string]$Class,
        [Parameter(Mandatory = $true)][string]$Code,
        [hashtable]$Values = @{}
    )
    return @{
        id          = $Id
        class       = $Class
        code        = $Code
        message_key = ('check.{0}.{1}' -f $Id.ToLowerInvariant(), $Code)
        values      = $Values
    }
}

function New-UnreadableResult {
    # Spec 5.2: an unreadable R-check is Advice "Setup cannot read ..."; any other check is Log.
    param([Parameter(Mandatory = $true)][string]$Id)
    if ($SlateOpsCheck.RequirementIds -contains $Id) { return New-CheckResult -Id $Id -Class 'advice' -Code 'cannot_read' }
    return New-CheckResult -Id $Id -Class 'log' -Code 'cannot_read'
}

function Get-FactValue {
    param([hashtable]$Facts, [Parameter(Mandatory = $true)][string]$Name)
    # The unary comma keeps an empty list (no listener) from unrolling to $null ("cannot read").
    if ($Facts.ContainsKey($Name)) { return , $Facts[$Name] }
    return $null
}

# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

function Test-C01 {
    # Windows 11 build 22621 or later. Windows 10 (build below 22000) is Stop; Windows 11 below
    # 22H2 is Fix (Windows Update).
    param([hashtable]$Facts)
    $build = Get-FactValue $Facts 'build'
    if ($null -eq $build) { return New-UnreadableResult 'C01' }
    $values = @{ build = [int]$build; display_version = (Get-FactValue $Facts 'display_version') }
    if ([int]$build -lt 22000) { return New-CheckResult 'C01' 'stop' 'windows_10' $values }
    if ([int]$build -lt $SlateOps.MinBuild) { return New-CheckResult 'C01' 'fix' 'too_old' $values }
    return New-CheckResult 'C01' 'pass' 'ok' $values
}

function Test-C02 {
    param([hashtable]$Facts)
    $edition = Get-FactValue $Facts 'edition_id'
    if (-not $edition) { return New-UnreadableResult 'C02' }
    $values = @{ edition_id = [string]$edition }
    if ([string]$edition -match $SlateOpsCheck.EditionPattern) { return New-CheckResult 'C02' 'pass' 'ok' $values }
    if ([string]$edition -like 'Core*') { return New-CheckResult 'C02' 'stop' 'home' $values }
    return New-CheckResult 'C02' 'stop' 'edition_not_supported' $values
}

function Test-C03 {
    param([hashtable]$Facts)
    $arch = Get-FactValue $Facts 'architecture'
    if (-not $arch) { return New-UnreadableResult 'C03' }
    $values = @{ architecture = [string]$arch }
    if ([string]$arch -eq 'AMD64') { return New-CheckResult 'C03' 'pass' 'ok' $values }
    if ([string]$arch -eq 'ARM64') { return New-CheckResult 'C03' 'stop' 'arm' $values }
    return New-CheckResult 'C03' 'stop' 'not_supported' $values
}

function Test-C04 {
    # Pass when a hypervisor runs. Fix when virtualization is off (also when SLAT then reads
    # false). Stop only when virtualization is on and SLAT is false. Advice when unreadable.
    param([hashtable]$Facts)
    $hypervisor = Get-FactValue $Facts 'hypervisor_present'
    $firmware = Get-FactValue $Facts 'virtualization_firmware'
    $slat = Get-FactValue $Facts 'slat'
    $values = @{
        uefi              = [bool](Get-FactValue $Facts 'uefi')
        bitlocker_caution = ((Get-FactValue $Facts 'bitlocker_c') -ne 'Off')
        maker             = (Get-FactValue $Facts 'maker')
    }
    if ($hypervisor -eq $true) { return New-CheckResult 'C04' 'pass' 'ok' $values }
    if ($null -eq $firmware) { return New-UnreadableResult 'C04' }
    if ($firmware -eq $false) { return New-CheckResult 'C04' 'fix' 'off' $values }
    if ($slat -eq $false) { return New-CheckResult 'C04' 'stop' 'no_slat' $values }
    if ($null -eq $slat) { return New-UnreadableResult 'C04' }
    return New-CheckResult 'C04' 'pass' 'ok' $values
}

function Test-C05 {
    # TotalPhysicalMemory decides. The screen shows the installed memory
    # (GetPhysicallyInstalledSystemMemory) in whole GB; if that failed, TotalPhysicalMemory
    # rounded up.
    param([hashtable]$Facts)
    $total = Get-FactValue $Facts 'total_physical_bytes'
    if ($null -eq $total) { return New-UnreadableResult 'C05' }
    $installedKb = Get-FactValue $Facts 'installed_memory_kb'
    if ($installedKb) { $installedGb = [int][math]::Round([double]$installedKb / 1MB) }
    else { $installedGb = [int][math]::Ceiling([double]$total / 1GB) }
    $values = @{
        installed_gb         = $installedGb
        usable_gb            = [int][math]::Floor([double]$total / 1GB)
        total_physical_bytes = [long]$total
        installed_memory_kb  = $installedKb
    }
    if ([long]$total -ge $SlateOpsCheck.MinUsableMemoryBytes) { return New-CheckResult 'C05' 'pass' 'ok' $values }
    if ($installedGb -ge 16) { return New-CheckResult 'C05' 'stop' 'reserved' $values }
    return New-CheckResult 'C05' 'stop' 'too_small' $values
}

function Test-C06 {
    param([hashtable]$Facts)
    return New-CheckResult 'C06' 'log' 'recorded' @{ cores = (Get-FactValue $Facts 'cores'); threads = (Get-FactValue $Facts 'threads') }
}

function Get-DataDriveCandidate {
    # The fixed NTFS drives that can hold the data (plan page 4, spec C07 and S07): not
    # removable, not network, not compressed, not EFS-encrypted. Largest free space first.
    param([AllowNull()][object[]]$Drives)
    $out = @()
    foreach ($drive in @($Drives)) {
        if ($null -eq $drive) { continue }
        if ($drive.drive_type -ne 'Fixed') { continue }
        if ($drive.file_system -ne 'NTFS') { continue }
        if ($drive.compressed -or $drive.encrypted) { continue }
        $out += $drive
    }
    return @($out | Sort-Object -Property @{ Expression = { [long]$_.free_bytes } } -Descending)
}

function Test-C07 {
    param([hashtable]$Facts)
    $drives = Get-FactValue $Facts 'drives'
    if ($null -eq $drives) { return New-UnreadableResult 'C07' }
    $candidates = @(Get-DataDriveCandidate -Drives $drives)
    if ($candidates.Count -eq 0) { return New-CheckResult 'C07' 'fix' 'no_drive' @{ need_gb = 15 } }
    $best = $candidates[0]
    $values = @{ letter = [string]$best.letter; free_gb = [int][math]::Floor([double]$best.free_bytes / 1GB); need_gb = 15 }
    if ([long]$best.free_bytes -ge $SlateOpsCheck.MinFreeBytes) { return New-CheckResult 'C07' 'pass' 'ok' $values }
    return New-CheckResult 'C07' 'fix' 'too_small' $values
}

function Test-C08 {
    param([hashtable]$Facts)
    $pending = Get-FactValue $Facts 'restart_pending'
    if ($null -eq $pending) { return New-UnreadableResult 'C08' }
    $set = Get-OrdinalSorted @($pending.Keys | Where-Object { $pending[$_] -eq $true })
    if ($set.Count -gt 0) { return New-CheckResult 'C08' 'fix' 'pending' @{ values_set = $set } }
    return New-CheckResult 'C08' 'pass' 'ok'
}

function Test-C09 {
    param([hashtable]$Facts)
    $lan = Get-FactValue $Facts 'lan'
    if (-not $Facts.ContainsKey('lan')) { return New-UnreadableResult 'C09' }
    if ($null -eq $lan) { return New-CheckResult 'C09' 'fix' 'not_connected' }
    return New-CheckResult 'C09' 'pass' 'ok' @{ interface = [string]$lan.interface_alias }
}

function Test-C10 {
    param([hashtable]$Facts)
    if (-not $Facts.ContainsKey('lan')) { return New-UnreadableResult 'C10' }
    $lan = Get-FactValue $Facts 'lan'
    if ($null -eq $lan) { return New-CheckResult 'C10' 'log' 'no_network' }
    $category = [string]$lan.category
    if (-not $category) { return New-UnreadableResult 'C10' }
    if ($category -eq 'Public') { return New-CheckResult 'C10' 'fix' 'public' @{ network_name = [string]$lan.network_name } }
    return New-CheckResult 'C10' 'pass' 'ok' @{ category = $category }
}

function Test-C11 {
    param([hashtable]$Facts)
    if (-not $Facts.ContainsKey('lan')) { return New-UnreadableResult 'C11' }
    $lan = Get-FactValue $Facts 'lan'
    $domain = Get-FactValue $Facts 'part_of_domain'
    if (($null -ne $lan) -and ([string]$lan.category -eq 'DomainAuthenticated')) { return New-CheckResult 'C11' 'stop' 'domain' }
    if ($domain -eq $true) { return New-CheckResult 'C11' 'stop' 'domain' }
    return New-CheckResult 'C11' 'pass' 'ok'
}

function Test-C12 {
    param([hashtable]$Facts)
    $internet = Get-FactValue $Facts 'internet'
    if ($null -eq $internet) { return New-UnreadableResult 'C12' }
    if ($internet.proxy -eq $true) { return New-CheckResult 'C12' 'fix' 'proxy' }
    $failed = Get-OrdinalSorted @($internet.hosts.Keys | Where-Object { $internet.hosts[$_] -ne 'ok' })
    if ($failed.Count -gt 0) { return New-CheckResult 'C12' 'fix' 'no_connection' @{ hosts = $failed } }
    return New-CheckResult 'C12' 'pass' 'ok'
}

function Test-C13 {
    param([hashtable]$Facts)
    $offset = Get-FactValue $Facts 'clock_offset_seconds'
    if ($null -eq $offset) { return New-UnreadableResult 'C13' }
    $values = @{ offset_seconds = [double]$offset; offset_minutes = [int][math]::Ceiling([math]::Abs([double]$offset) / 60) }
    if ([math]::Abs([double]$offset) -gt $SlateOpsCheck.MaxClockOffsetSec) { return New-CheckResult 'C13' 'fix' 'wrong' $values }
    return New-CheckResult 'C13' 'pass' 'ok' $values
}

function Test-C14 {
    param([hashtable]$Facts)
    $listeners = Get-FactValue $Facts 'listeners'
    if ($null -eq $listeners) { return New-UnreadableResult 'C14' }
    $foreign = @($listeners | Where-Object { -not $_.ours })
    if ($foreign.Count -gt 0) {
        $names = Get-OrdinalSorted @($foreign | ForEach-Object { [string]$_.process_name } | Select-Object -Unique)
        return New-CheckResult 'C14' 'fix' 'in_use' @{ programs = $names; ports = @($foreign | ForEach-Object { [int]$_.port } | Sort-Object -Unique) }
    }
    return New-CheckResult 'C14' 'pass' 'ok'
}

function Test-DnsLabel {
    # RFC 1123 host label: letters, digits and hyphens, 1 to 63 characters, no hyphen at either
    # end, not all digits.
    param([AllowNull()][string]$Name)
    if (-not $Name) { return $false }
    if ($Name -notmatch '^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$') { return $false }
    if ($Name -match '^[0-9]+$') { return $false }
    return $true
}

function Test-C15 {
    # The address is the DNS host name in lower case (P3-9; Windows answers mDNS for it). Advice
    # when it differs from the NetBIOS name or is longer than 15 characters, because other
    # Windows names of this PC then do not match the address.
    param([hashtable]$Facts)
    $name = Get-FactValue $Facts 'dns_host_name'
    if (-not $name) { return New-UnreadableResult 'C15' }
    $netbios = [string](Get-FactValue $Facts 'computer_name')
    $values = @{ address = ('{0}.local' -f ([string]$name).ToLowerInvariant()); netbios_name = $netbios }
    if (-not (Test-DnsLabel $name)) { return New-CheckResult 'C15' 'fix' 'invalid_name' $values }
    if ((([string]$name).Length -gt 15) -or ($netbios -and ([string]$name -ine $netbios))) { return New-CheckResult 'C15' 'advice' 'name_mismatch' $values }
    return New-CheckResult 'C15' 'pass' 'ok' $values
}

function Test-C16 {
    # Plan F1: no other device on this network answers to <name>.local (an mDNS probe).
    param([hashtable]$Facts)
    if (-not $Facts.ContainsKey('mdns_other')) { return New-UnreadableResult 'C16' }
    $other = Get-FactValue $Facts 'mdns_other'
    if ($null -eq $other) { return New-UnreadableResult 'C16' }
    $name = Get-FactValue $Facts 'dns_host_name'
    if ($other -eq $true) { return New-CheckResult 'C16' 'fix' 'name_in_use' @{ address = ('{0}.local' -f $name) } }
    return New-CheckResult 'C16' 'pass' 'ok'
}

function Test-C17 {
    # Plan F1: the DNS Client service runs, no policy turns multicast name resolution off, and a
    # built-in mDNS rule allows the Private profile. A rule that a policy sets is not fixable
    # here ("Ask the person who manages this PC").
    param([hashtable]$Facts)
    $mdns = Get-FactValue $Facts 'mdns'
    if ($null -eq $mdns) { return New-UnreadableResult 'C17' }
    if ((-not $mdns.dns_client_running) -or $mdns.multicast_off) { return New-CheckResult 'C17' 'fix' 'policy' }
    if ($mdns.private_rule_enabled) { return New-CheckResult 'C17' 'pass' 'ok' }
    if ($mdns.rule_from_policy -or (-not $mdns.private_rule)) { return New-CheckResult 'C17' 'fix' 'policy' }
    return New-CheckResult 'C17' 'fix' 'rule_off' @{ rule = [string]$mdns.private_rule }
}

function Get-MdnsFact {
    # C17 facts: read-only.
    $service = Get-Service -Name 'Dnscache' -ErrorAction Stop
    $policy = Get-ItemProperty -LiteralPath $SlateOpsCheck.DnsClientPolicyKey -ErrorAction SilentlyContinue
    $off = [bool]($policy -and $policy.PSObject.Properties['EnableMulticast'] -and ([int]$policy.EnableMulticast -eq 0))
    $rules = @(Get-NetFirewallRule -Name $SlateOpsCheck.MdnsRulePattern -ErrorAction SilentlyContinue | Where-Object { [string]$_.Direction -eq 'Inbound' })
    $private = @($rules | Where-Object { ([string]$_.Profile -match 'Private') -or ([string]$_.Profile -eq 'Any') })
    $enabled = @($private | Where-Object { [string]$_.Enabled -eq 'True' })
    $fromPolicy = @($private | Where-Object { [string]$_.PolicyStoreSourceType -eq 'GroupPolicy' }).Count -gt 0
    return @{
        dns_client_running   = ([string]$service.Status -eq 'Running')
        multicast_off        = $off
        private_rule         = $(if ($private.Count -gt 0) { [string]$private[0].Name } else { '' })
        private_rule_enabled = ($enabled.Count -gt 0)
        rule_from_policy     = $fromPolicy
    }
}

function Test-MdnsNameInUse {
    # C16: one mDNS query for <name>.local (A record, unicast response asked) on every IPv4
    # address of this PC. An answer from an address that is not this PC's means another device
    # uses the name. $null when the probe cannot run.
    param([Parameter(Mandatory = $true)][string]$Name, [int]$WaitMs = 1500)
    $own = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | ForEach-Object { [string]$_.IPAddress })
    $query = New-Object System.Collections.Generic.List[byte]
    $query.AddRange([byte[]](0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0))
    foreach ($label in @($Name, 'local')) {
        $bytes = [System.Text.Encoding]::ASCII.GetBytes($label)
        $query.Add([byte]$bytes.Length); $query.AddRange($bytes)
    }
    # QTYPE A, QCLASS IN with the unicast-response bit.
    $query.AddRange([byte[]](0, 0, 1, 128, 1))
    $client = New-Object System.Net.Sockets.UdpClient(0)
    try {
        $client.Client.ReceiveTimeout = $WaitMs
        $packet = $query.ToArray()
        [void]$client.Send($packet, $packet.Length, (New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse('224.0.0.251'), 5353)))
        $deadline = [DateTime]::UtcNow.AddMilliseconds($WaitMs)
        while ([DateTime]::UtcNow -lt $deadline) {
            $from = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
            try { $answer = $client.Receive([ref]$from) } catch [System.Net.Sockets.SocketException] { break }
            # A response (QR bit) with at least one answer record, from another address.
            if (($answer.Length -ge 12) -and (($answer[2] -band 0x80) -ne 0) -and ((($answer[6] * 256) + $answer[7]) -gt 0)) {
                if ($own -notcontains $from.Address.ToString()) { return $true }
            }
        }
        return $false
    } finally { $client.Dispose() }
}

function Test-C18 {
    # W80-8: a policy that records the password module, or a policy that cannot be read, is Fix.
    param([hashtable]$Facts)
    $policy = Get-FactValue $Facts 'logging_policy'
    if ($null -eq $policy) { return New-CheckResult 'C18' 'fix' 'unreadable' }
    $covered = @(Get-PasswordModuleLogged -Policy $policy)
    if ($covered.Count -gt 0) { return New-CheckResult 'C18' 'fix' 'policy' @{ modules = $covered } }
    return New-CheckResult 'C18' 'pass' 'ok'
}

function Test-C19 {
    param([hashtable]$Facts)
    return New-CheckResult 'C19' 'log' 'recorded' @{ smart_app_control = (Get-FactValue $Facts 'smart_app_control') }
}

function Test-C20 {
    param([hashtable]$Facts)
    $products = Get-FactValue $Facts 'antivirus'
    if ($null -eq $products) { return New-UnreadableResult 'C20' }
    $other = Get-OrdinalSorted @($products | Where-Object { $_ -and ($_ -notmatch '^(Windows Defender|Microsoft Defender)') } | Select-Object -Unique)
    if ($other.Count -gt 0) { return New-CheckResult 'C20' 'advice' 'other_antivirus' @{ products = $other } }
    return New-CheckResult 'C20' 'pass' 'ok'
}

function Test-C21 {
    param([hashtable]$Facts)
    if (-not $Facts.ContainsKey('battery')) { return New-UnreadableResult 'C21' }
    $battery = Get-FactValue $Facts 'battery'
    if ($null -eq $battery) { return New-UnreadableResult 'C21' }
    if (-not $battery.present) { return New-CheckResult 'C21' 'pass' 'ok' }
    if ($battery.on_battery -eq $true) { return New-CheckResult 'C21' 'advice' 'on_battery' }
    return New-CheckResult 'C21' 'advice' 'laptop'
}

function Test-C22 {
    # Laptops only. 0 = do nothing (documented LIDACTION values: 0 do nothing, 1 sleep,
    # 2 hibernate, 3 shut down).
    param([hashtable]$Facts)
    $battery = Get-FactValue $Facts 'battery'
    if (($null -eq $battery) -or (-not $battery.present)) { return New-CheckResult 'C22' 'pass' 'not_laptop' }
    $lid = Get-FactValue $Facts 'lid_action_ac'
    if ($null -eq $lid) { return New-UnreadableResult 'C22' }
    if ([int]$lid -ne 0) { return New-CheckResult 'C22' 'advice' 'sleeps' @{ lid_action_ac = [int]$lid } }
    return New-CheckResult 'C22' 'pass' 'ok'
}

function Test-C23 {
    param([hashtable]$Facts)
    $lan = Get-FactValue $Facts 'lan'
    if (($null -eq $lan) -or ($null -eq $lan.wifi)) { return New-UnreadableResult 'C23' }
    if ($lan.wifi -eq $true) { return New-CheckResult 'C23' 'advice' 'wifi' }
    return New-CheckResult 'C23' 'pass' 'ok'
}

function Test-C24 {
    # Status only (ProtectionStatus), of C: and of the data drive candidate (W80-9).
    param([hashtable]$Facts)
    $status = Get-FactValue $Facts 'bitlocker'
    $drives = Get-FactValue $Facts 'drives'
    if (($null -eq $status) -or ($null -eq $drives)) { return New-UnreadableResult 'C24' }
    $candidates = @(Get-DataDriveCandidate -Drives $drives)
    if ($candidates.Count -eq 0) { return New-UnreadableResult 'C24' }
    $letter = [string]$candidates[0].letter
    $state = $null
    if ($status.ContainsKey($letter)) { $state = [string]$status[$letter] }
    if (-not $state) { return New-UnreadableResult 'C24' }
    # Owner decision (2026-11-18): setup never suggests turning BitLocker on; the state is recorded
    # for support only. An encrypted data drive still needs automatic unlock (below).
    if ($state -eq 'Off') { return New-CheckResult 'C24' 'log' 'off' @{ letter = $letter } }
    if ($letter -ne 'C:') { return New-CheckResult 'C24' 'advice' 'auto_unlock' @{ letter = $letter } }
    return New-CheckResult 'C24' 'pass' 'ok' @{ letter = $letter }
}

function Test-C25 {
    param([hashtable]$Facts)
    $docker = Get-FactValue $Facts 'docker_desktop'
    if ($null -eq $docker) { return New-UnreadableResult 'C25' }
    if ($docker -eq $true) { return New-CheckResult 'C25' 'advice' 'installed' }
    return New-CheckResult 'C25' 'pass' 'ok'
}

function Test-C26 {
    # Auto: setup turns the feature on and installs the pinned WSL in S05. restart_needed decides
    # the verdict's second line.
    param([hashtable]$Facts, [version]$PinnedWsl = [version]'0.0.0.0')
    $feature = Get-FactValue $Facts 'vmp_state'
    $wsl = Get-FactValue $Facts 'wsl_version'
    if ($null -eq $feature) { return New-UnreadableResult 'C26' }
    $restart = ([string]$feature -ne 'Enabled')
    $install = (($null -eq $wsl) -or ([version]$wsl -lt $PinnedWsl))
    $values = @{ vmp_state = [string]$feature; wsl_version = $(if ($wsl) { [string]$wsl } else { $null }); restart_needed = $restart; wsl_install_needed = $install }
    if ($restart -or $install) { return New-CheckResult 'C26' 'auto' 'prepare' $values }
    return New-CheckResult 'C26' 'pass' 'ok' $values
}

function Test-C27 {
    param([hashtable]$Facts)
    return New-CheckResult 'C27' 'auto' 'keep_awake' @{ sleep_ac_seconds = (Get-FactValue $Facts 'sleep_ac_seconds'); hibernate_ac_seconds = (Get-FactValue $Facts 'hibernate_ac_seconds') }
}

function Test-C28 {
    param([hashtable]$Facts)
    return New-CheckResult 'C28' 'log' 'recorded' @{
        fast_startup   = (Get-FactValue $Facts 'fast_startup')
        user_distros   = (Get-FactValue $Facts 'user_distros')
        user_wslconfig = (Get-FactValue $Facts 'user_wslconfig')
        time_zone      = (Get-FactValue $Facts 'time_zone')
    }
}

function Test-C29 {
    # Parts of the boot-test kit, a lone account (an earlier uninstall, N-2), or Slate Operations
    # parts with no installed program (unknown: Stop). The check removes nothing.
    param([hashtable]$Facts)
    $parts = Get-FactValue $Facts 'leftovers'
    if ($null -eq $parts) { return New-UnreadableResult 'C29' }
    $kit = @()
    foreach ($name in @('kit_distro', 'kit_tasks', 'kit_rules', 'kit_folder')) { if ($parts[$name]) { $kit += $name } }
    $values = @{ found = (Get-OrdinalSorted @($parts.Keys | Where-Object { $parts[$_] -eq $true })) }
    # S91-1: a kit folder that fails the kit's own safety check is not "an earlier test": setup
    # removes nothing there and stops.
    if ($parts['kit_folder_unsafe']) { return New-CheckResult 'C29' 'stop' 'unknown_parts' $values }
    # W9 review item 3: parts with no installed program but an uninstall log are the leftovers of
    # an earlier uninstall: Fix (remove-windows). Without the log they stay unknown (Stop).
    if ($parts['slateops_parts'] -and (-not $parts['installed_program'])) {
        if ($parts['uninstall_log']) { return New-CheckResult 'C29' 'fix' 'uninstall_leftovers' $values }
        return New-CheckResult 'C29' 'stop' 'unknown_parts' $values
    }
    if ($kit.Count -gt 0) { return New-CheckResult 'C29' 'fix' 'earlier_test' $values }
    if ($parts['account'] -and (-not $parts['installed_program'])) { return New-CheckResult 'C29' 'fix' 'leftover_account' $values }
    return New-CheckResult 'C29' 'pass' 'ok' $values
}

function Test-C30 {
    param([hashtable]$Facts)
    $name = Get-FactValue $Facts 'dns_host_name'
    if (-not $name) { return New-UnreadableResult 'C30' }
    $values = @{ address = ('{0}.local' -f ([string]$name).ToLowerInvariant()) }
    if (([string]$name).ToUpperInvariant() -cmatch $SlateOpsCheck.FactoryNamePattern) { return New-CheckResult 'C30' 'advice' 'factory_name' $values }
    return New-CheckResult 'C30' 'pass' 'ok' $values
}

function Invoke-PcCheck {
    # Runs every check that W7 owns over one facts hashtable. -Only limits it to the given IDs
    # (the recheck of spec 5.2). Returns the results in ID order.
    param(
        [Parameter(Mandatory = $true)][hashtable]$Facts,
        [version]$PinnedWsl = [version]'0.0.0.0',
        [string[]]$Only = @()
    )
    $ids = @('C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08', 'C09', 'C10', 'C11', 'C12', 'C13', 'C14', 'C15',
        'C16', 'C17', 'C18', 'C19', 'C20', 'C21', 'C22', 'C23', 'C24', 'C25', 'C26', 'C27', 'C28', 'C29', 'C30')
    if ($Only.Count -gt 0) { $ids = @($ids | Where-Object { $Only -contains $_ }) }
    $results = @()
    foreach ($id in $ids) {
        try {
            if ($id -eq 'C26') { $results += , (Test-C26 -Facts $Facts -PinnedWsl $PinnedWsl) }
            else { $results += , (& ('Test-{0}' -f $id) -Facts $Facts) }
        } catch {
            $results += , (New-UnreadableResult $id)
        }
    }
    return $results
}

function Get-PcVerdict {
    # Spec 5.2: any Stop -> not_suitable; else any Fix -> needs_fixes (count); else ready, with
    # restart_needed from C26.
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Results)
    $stops = @($Results | Where-Object { $_.class -eq 'stop' })
    $fixes = @($Results | Where-Object { $_.class -eq 'fix' })
    $restart = $false
    foreach ($result in $Results) { if (($result.id -eq 'C26') -and $result.values.ContainsKey('restart_needed')) { $restart = [bool]$result.values.restart_needed } }
    if ($stops.Count -gt 0) { return @{ verdict = 'not_suitable'; message_key = 'check.verdict.not_suitable'; stop_ids = @($stops | ForEach-Object { $_.id }) } }
    if ($fixes.Count -gt 0) { return @{ verdict = 'needs_fixes'; message_key = 'check.verdict.needs_fixes'; fix_count = $fixes.Count; fix_ids = @($fixes | ForEach-Object { $_.id }) } }
    return @{ verdict = 'ready'; message_key = 'check.verdict.ready'; restart_needed = $restart }
}

# ---------------------------------------------------------------------------
# Reading Windows (read-only). Each reader returns $null when it cannot read its value.
# ---------------------------------------------------------------------------

function Invoke-Reader {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][scriptblock]$Reader)
    # The unary comma keeps an empty array as an empty array; a plain return would unroll it
    # to $null, which means "cannot read".
    try { $value = & $Reader; return , $value }
    catch {
        Write-RunLog ('check.read.{0}' -f $Name) 'WARN' ('cannot read: {0}' -f $_.Exception.Message)
        return $null
    }
}

function Initialize-NativeInfoType {
    if ('SlateOpsSetup.NativeInfo' -as [type]) { return }
    $source = @'
using System;
using System.Runtime.InteropServices;
namespace SlateOpsSetup
{
    public static class NativeInfo
    {
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetPhysicallyInstalledSystemMemory(out ulong totalMemoryInKilobytes);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetFirmwareType(out uint firmwareType);

        // Returns the installed memory in kilobytes (SMBIOS), or 0 when the call fails.
        public static ulong InstalledMemoryKb()
        {
            ulong kb;
            if (GetPhysicallyInstalledSystemMemory(out kb)) { return kb; }
            return 0;
        }

        // FirmwareTypeBios = 1, FirmwareTypeUefi = 2. Returns 0 when the call fails.
        public static uint FirmwareType()
        {
            uint type;
            if (GetFirmwareType(out type)) { return type; }
            return 0;
        }
    }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp
}

function Get-LanFact {
    # The up adapter with an IPv4 default gateway (kit Get-LanInfo), with its category and
    # whether it is Wi-Fi (NdisPhysicalMedium 9 = Native 802.11; Assumption, W14 checks it).
    $configs = @(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter -and ($_.NetAdapter.Status -eq 'Up') })
    if ($configs.Count -eq 0) { return $null }
    $config = $configs[0]
    $ipv4 = @($config.IPv4Address)[0]
    $connection = Get-NetConnectionProfile -InterfaceIndex $config.InterfaceIndex -ErrorAction SilentlyContinue
    $wifi = $null
    try { $wifi = ([int]$config.NetAdapter.NdisPhysicalMedium -eq 9) } catch { $wifi = $null }
    return @{
        interface_alias = [string]$config.InterfaceAlias
        interface_index = [int]$config.InterfaceIndex
        address         = [string]$ipv4.IPAddress
        prefix_length   = [int]$ipv4.PrefixLength
        category        = $(if ($connection) { [string]$connection.NetworkCategory } else { $null })
        network_name    = $(if ($connection) { [string]$connection.Name } else { $null })
        adapter_count   = $configs.Count
        wifi            = $wifi
    }
}

function Get-DriveFact {
    $out = @()
    foreach ($disk in @(Get-CimInstance -ClassName Win32_LogicalDisk)) {
        $type = switch ([int]$disk.DriveType) { 2 { 'Removable' } 3 { 'Fixed' } 4 { 'Network' } 5 { 'CD' } 6 { 'RAM' } default { 'Unknown' } }
        $root = '{0}\' -f $disk.DeviceID
        $encrypted = $false
        try { $encrypted = [bool]((Get-Item -LiteralPath $root -Force).Attributes -band [System.IO.FileAttributes]::Encrypted) } catch { $encrypted = $false }
        $out += @{
            letter      = [string]$disk.DeviceID
            label       = [string]$disk.VolumeName
            drive_type  = $type
            file_system = [string]$disk.FileSystem
            free_bytes  = [long]$disk.FreeSpace
            size_bytes  = [long]$disk.Size
            compressed  = [bool]$disk.Compressed
            encrypted   = $encrypted
        }
    }
    return $out
}

function Get-RestartPendingFact {
    return @{
        RebootPending              = [bool](Test-Path -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')
        RebootRequired             = [bool](Test-Path -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
        PendingFileRenameOperations = [bool](Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name 'PendingFileRenameOperations' -ErrorAction SilentlyContinue)
    }
}

function Get-InternetFact {
    # HTTPS HEAD to the image registries with a plain user agent (R8; REQ-0022: a browser-like
    # agent gets a bot check). Any HTTP answer, 401 included, means reachable. The clock offset
    # is the smallest of three Date-header samples after half the round trip (spec C13).
    param([string]$UserAgent = 'SlateOpsSetup/1.0')
    $proxy = $false
    $settings = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if ($settings) {
        if ($settings.PSObject.Properties['ProxyEnable'] -and ($settings.ProxyEnable -eq 1)) { $proxy = $true }
        if ($settings.PSObject.Properties['AutoConfigURL'] -and $settings.AutoConfigURL) { $proxy = $true }
    }
    $winHttp = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings\Connections' -Name 'WinHttpSettings' -ErrorAction SilentlyContinue
    if ($winHttp -and ($winHttp.WinHttpSettings.Length -gt 8) -and (([int]$winHttp.WinHttpSettings[8] -band 2) -ne 0)) { $proxy = $true }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $hosts = [ordered]@{ 'ghcr.io' = 'https://ghcr.io/v2/'; 'registry-1.docker.io' = 'https://registry-1.docker.io/v2/' }
    $result = @{}
    $offsets = @()
    foreach ($name in $hosts.Keys) {
        $result[$name] = 'fail'
        for ($i = 0; $i -lt 3; $i++) {
            $request = [System.Net.HttpWebRequest]::Create($hosts[$name])
            $request.Method = 'HEAD'
            $request.UserAgent = $UserAgent
            $request.Timeout = 10000
            $request.AllowAutoRedirect = $false
            $sent = Get-Date
            $response = $null
            try { $response = $request.GetResponse() }
            catch [System.Net.WebException] { if ($_.Exception.Response) { $response = $_.Exception.Response } }
            $received = Get-Date
            if ($null -eq $response) { break }
            $result[$name] = 'ok'
            $date = $response.Headers['Date']
            $response.Close()
            if ($date) {
                $server = [datetime]::Parse($date, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AdjustToUniversal)
                $local = $sent.ToUniversalTime().AddMilliseconds((($received - $sent).TotalMilliseconds) / 2)
                $offsets += ($local - $server).TotalSeconds
            }
        }
    }
    $offset = $null
    if ($offsets.Count -gt 0) { $offset = ($offsets | Sort-Object { [math]::Abs($_) } | Select-Object -First 1) }
    return @{ internet = @{ proxy = $proxy; hosts = $result }; clock_offset_seconds = $offset }
}

function Get-ListenerFact {
    $out = @()
    foreach ($connection in @(Get-NetTCPConnection -State Listen -LocalPort 80, 443 -ErrorAction SilentlyContinue)) {
        $name = $null
        try { $name = (Get-Process -Id $connection.OwningProcess -ErrorAction Stop).ProcessName } catch { $name = ('process {0}' -f $connection.OwningProcess) }
        # wslrelay forwards ports of a WSL distribution (Assumption: the server part's ports in
        # mirrored mode show as this process; W14 records the real owner).
        $out += @{ port = [int]$connection.LocalPort; process_name = [string]$name; ours = ($name -eq 'wslrelay') }
    }
    return $out
}

function Get-PowerIndex {
    # Kit function: the AC and DC index of one power setting. Returns @{ ac; dc } or $null.
    param([string]$Scheme = 'SCHEME_CURRENT', [Parameter(Mandatory = $true)][string]$SubGroup, [Parameter(Mandatory = $true)][string]$Setting)
    $query = Invoke-Logged -Step 'check.read.power' -FilePath 'powercfg.exe' -ArgumentList @('/query', $Scheme, $SubGroup, $Setting) -NoThrow
    if ($query.ExitCode -ne 0) { return $null }
    $hex = @($query.Output | ForEach-Object { if ($_ -match '0x([0-9a-fA-F]{8})\s*$') { $Matches[1] } })
    if ($hex.Count -lt 2) { return $null }
    return @{ ac = [Convert]::ToInt64($hex[$hex.Count - 2], 16); dc = [Convert]::ToInt64($hex[$hex.Count - 1], 16) }
}

function Get-EncryptableVolumeStatus {
    # BitLocker status through WMI (P2-4, S91-10; changes the plan 10.4 command, TASK-0091): the
    # class Win32_EncryptableVolume with only DriveLetter, ProtectionStatus, ConversionStatus
    # and EncryptionMethod selected. The BitLocker module is not used, because it loads every
    # volume's key protectors before any property is selected. ProtectionStatus: 0 off, 1 on,
    # 2 unknown (Win32_EncryptableVolume documentation).
    param([string[]]$MountPoints)
    $wanted = @($MountPoints | ForEach-Object { ([string]$_).ToUpperInvariant() })
    $out = @()
    $volumes = @(Get-CimInstance -Namespace 'root\cimv2\Security\MicrosoftVolumeEncryption' -ClassName 'Win32_EncryptableVolume' `
            -Property DriveLetter, ProtectionStatus, ConversionStatus, EncryptionMethod -ErrorAction Stop)
    foreach ($volume in $volumes) {
        $letter = ([string]$volume.DriveLetter).ToUpperInvariant()
        if ($wanted -notcontains $letter) { continue }
        $protection = switch ([int]$volume.ProtectionStatus) { 0 { 'Off' } 1 { 'On' } default { 'Unknown' } }
        $out += @{ mount_point = $letter; protection_status = $protection; conversion_status = [int]$volume.ConversionStatus; encryption_method = [int]$volume.EncryptionMethod }
    }
    return $out
}

function Get-BitLockerStatusFact {
    # Status only (W80-9): protection status per mount point.
    param([string[]]$MountPoints)
    $out = @{}
    foreach ($volume in @(Get-EncryptableVolumeStatus -MountPoints $MountPoints)) { $out[[string]$volume.mount_point] = [string]$volume.protection_status }
    return $out
}

function Get-WslPackageVersion {
    # Kit function: the installed WSL package version, or $null when the package is absent.
    $exe = Join-Path $SlateOpsPaths.ProgramFiles 'WSL\wsl.exe'
    if (-not (Test-Path -LiteralPath $exe)) { return $null }
    $info = (Get-Item -LiteralPath $exe).VersionInfo
    return New-Object -TypeName System.Version -ArgumentList $info.FileMajorPart, $info.FileMinorPart, $info.FileBuildPart, $info.FilePrivatePart
}

function Get-KitTree {
    # The boot-test kit's folder tree and its expected access (kit lib/common.ps1).
    param([Parameter(Mandatory = $true)][hashtable]$Kit)
    return @{ Root = $Kit.Root; Entries = [ordered]@{ 'kit' = 'read'; 'cache' = 'read'; 'state' = 'read'; 'logs' = 'none'; 'svc-out' = 'modify'; 'distro' = 'modify' } }
}

function Get-KitTreeProblem {
    # The kit's own safety check, with the kit account's SID when the account exists. N-1: after
    # the C29 removal has deleted the account, the caller passes the SID that it saved, because
    # the kit folder still holds the account's entries.
    param([Parameter(Mandatory = $true)][hashtable]$Kit, [string]$AccountSid = '')
    if (-not (Test-Path -LiteralPath $Kit.Root)) { return @() }
    $sid = $AccountSid
    if (-not $sid) {
        $account = Get-LocalUser -Name $Kit.AccountName -ErrorAction SilentlyContinue
        $sid = $(if ($account) { $account.SID.Value } else { '' })
    }
    return @(Get-TreeProblem -Tree (Get-KitTree -Kit $Kit) -ServiceSid $sid)
}

function Test-InstalledProgram {
    # Spec 4.1 signal (P3-2, S91-1c): the installed program's version.json, in the folder that
    # the uninstall key of this setup names.
    $key = Get-ItemProperty -LiteralPath $SlateOpsCheck.UninstallKey -ErrorAction SilentlyContinue
    if ((-not $key) -or (-not $key.PSObject.Properties['InstallLocation']) -or (-not $key.InstallLocation)) { return $false }
    return [bool](Test-Path -LiteralPath (Join-Path ([string]$key.InstallLocation) 'version.json') -PathType Leaf)
}

function Get-LeftoverFact {
    # C29: parts of the boot-test kit (plan 10.7) and Slate Operations parts without an
    # installed program. Read-only. Nothing below the kit folder is read until the folder
    # passes the kit's safety check (S91-1).
    param([hashtable]$Kit = $SlateOpsCheck.Kit)
    $unsafe = (@(Get-KitTreeProblem -Kit $Kit).Count -gt 0)
    $folder = $false
    $distro = $false
    if (-not $unsafe) {
        # The kit's cleanup keeps its logs folder; a folder with only logs is not a leftover.
        $folder = (@(Get-ChildItem -LiteralPath $Kit.Root -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -ine 'logs' }).Count -gt 0)
        $distro = [bool](Test-Path -LiteralPath (Join-Path $Kit.Root 'distro\vhd\ext4.vhdx'))
    }
    return @{
        account           = [bool](Get-LocalUser -Name $Kit.AccountName -ErrorAction SilentlyContinue)
        kit_folder        = $folder
        kit_folder_unsafe = $unsafe
        kit_distro        = $distro
        kit_tasks         = [bool](Get-ScheduledTask -TaskPath $Kit.TaskPath -ErrorAction SilentlyContinue)
        kit_rules         = ([bool](Get-NetFirewallRule -Name $Kit.RuleName -ErrorAction SilentlyContinue)) -or ([bool](Get-NetFirewallHyperVRule -Name $Kit.HyperVRule -ErrorAction SilentlyContinue))
        slateops_parts    = [bool](Get-ScheduledTask -TaskPath $SlateOps.TaskPath -ErrorAction SilentlyContinue)
        installed_program = (Test-InstalledProgram)
        uninstall_log     = (@(Get-ChildItem -LiteralPath (Join-Path (New-SlateOpsLayout).Logs 'uninstall') -Filter 'uninstall-*.log' -File -Force -ErrorAction SilentlyContinue).Count -gt 0)
    }
}

function Get-PcCheckFacts {
    # Reads every fact of the PC check. Changes nothing on the PC.
    $facts = @{}
    $cv = Invoke-Reader 'windows' { Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' }
    if ($cv) {
        $facts.build = [int]$cv.CurrentBuildNumber
        $facts.edition_id = [string]$cv.EditionID
        if ($cv.PSObject.Properties['DisplayVersion']) { $facts.display_version = [string]$cv.DisplayVersion }
    }
    $facts.architecture = Invoke-Reader 'architecture' {
        # The operating system's architecture from .NET, not from an environment value (S91-6).
        switch ([string][System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture) { 'X64' { 'AMD64' } 'Arm64' { 'ARM64' } default { 'OTHER' } }
    }
    $cs = Invoke-Reader 'computer_system' { Get-CimInstance -ClassName Win32_ComputerSystem }
    $cpu = Invoke-Reader 'processor' { @(Get-CimInstance -ClassName Win32_Processor)[0] }
    if ($cs) {
        $facts.hypervisor_present = [bool]$cs.HypervisorPresent
        $facts.total_physical_bytes = [long]$cs.TotalPhysicalMemory
        $facts.part_of_domain = [bool]$cs.PartOfDomain
        $facts.maker = [string]$cs.Manufacturer
        $facts.computer_name = [string]$cs.Name
        $facts.dns_host_name = ([string]$cs.DNSHostName).ToLowerInvariant()
    }
    if ($cpu) {
        $facts.virtualization_firmware = $cpu.VirtualizationFirmwareEnabled
        $facts.slat = $cpu.SecondLevelAddressTranslationExtensions
        $facts.cores = $cpu.NumberOfCores
        $facts.threads = $cpu.NumberOfLogicalProcessors
    }
    $native = Invoke-Reader 'native' {
        Initialize-NativeInfoType
        @{ kb = [SlateOpsSetup.NativeInfo]::InstalledMemoryKb(); firmware = [SlateOpsSetup.NativeInfo]::FirmwareType() }
    }
    if ($native) {
        if ($native.kb -gt 0) { $facts.installed_memory_kb = [long]$native.kb }
        $facts.uefi = ($native.firmware -eq 2)
    }
    $facts.drives = Invoke-Reader 'drives' { Get-DriveFact }
    $facts.restart_pending = Invoke-Reader 'restart_pending' { Get-RestartPendingFact }
    $lan = Invoke-Reader 'lan' { @{ value = (Get-LanFact) } }
    if ($lan) { $facts.lan = $lan.value }
    $internet = Invoke-Reader 'internet' { Get-InternetFact }
    if ($internet) { $facts.internet = $internet.internet; $facts.clock_offset_seconds = $internet.clock_offset_seconds }
    $facts.listeners = Invoke-Reader 'listeners' { , @(Get-ListenerFact) }
    $facts.logging_policy = Invoke-Reader 'logging_policy' { Get-PowerShellLoggingPolicy }
    $facts.mdns = Invoke-Reader 'mdns' { Get-MdnsFact }
    if ($facts.dns_host_name) { $facts.mdns_other = Invoke-Reader 'mdns_other' { Test-MdnsNameInUse -Name $facts.dns_host_name } }
    $facts.smart_app_control = Invoke-Reader 'smart_app_control' {
        # Registry value name is an Assumption (plan 10.4); 0 off, 1 on, 2 evaluation.
        [int](Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -Name 'VerifiedAndReputablePolicyState' -ErrorAction Stop).VerifiedAndReputablePolicyState
    }
    $facts.antivirus = Invoke-Reader 'antivirus' { , @(Get-CimInstance -Namespace 'root\SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction Stop | ForEach-Object { [string]$_.displayName }) }
    $battery = Invoke-Reader 'battery' {
        $items = @(Get-CimInstance -ClassName Win32_Battery -ErrorAction Stop)
        # BatteryStatus 1 = discharging (on battery).
        @{ present = ($items.Count -gt 0); on_battery = (@($items | Where-Object { $_.BatteryStatus -eq 1 }).Count -gt 0) }
    }
    if ($null -ne $battery) { $facts.battery = $battery }
    $lid = Invoke-Reader 'lid' { Get-PowerIndex -SubGroup 'SUB_BUTTONS' -Setting 'LIDACTION' }
    if ($lid) { $facts.lid_action_ac = $lid.ac }
    $sleep = Invoke-Reader 'sleep' { Get-PowerIndex -SubGroup 'SUB_SLEEP' -Setting 'STANDBYIDLE' }
    if ($sleep) { $facts.sleep_ac_seconds = $sleep.ac }
    $hibernate = Invoke-Reader 'hibernate' { Get-PowerIndex -SubGroup 'SUB_SLEEP' -Setting 'HIBERNATEIDLE' }
    if ($hibernate) { $facts.hibernate_ac_seconds = $hibernate.ac }
    $mounts = @('C:')
    $candidates = @(Get-DataDriveCandidate -Drives $facts.drives)
    if ($candidates.Count -gt 0) { $mounts += [string]$candidates[0].letter }
    $facts.bitlocker = Invoke-Reader 'bitlocker' { Get-BitLockerStatusFact -MountPoints @($mounts | Select-Object -Unique) }
    if ($facts.bitlocker -and $facts.bitlocker.ContainsKey('C:')) { $facts.bitlocker_c = $facts.bitlocker['C:'] }
    $facts.docker_desktop = Invoke-Reader 'docker_desktop' {
        (Test-Path -LiteralPath (Join-Path $SlateOpsPaths.ProgramFiles 'Docker\Docker\Docker Desktop.exe')) -or [bool](Get-Service -Name 'com.docker.service' -ErrorAction SilentlyContinue)
    }
    $facts.vmp_state = Invoke-Reader 'vmp' { [string](Get-WindowsOptionalFeature -Online -FeatureName 'VirtualMachinePlatform' -ErrorAction Stop).State }
    $facts.wsl_version = Invoke-Reader 'wsl_version' { Get-WslPackageVersion }
    $facts.fast_startup = Invoke-Reader 'fast_startup' { (Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name 'HiberbootEnabled' -ErrorAction Stop).HiberbootEnabled }
    $facts.user_distros = Invoke-Reader 'user_distros' {
        $lxss = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
        if (Test-Path -LiteralPath $lxss) { , @(Get-ChildItem -LiteralPath $lxss | ForEach-Object { [string](Get-ItemProperty -LiteralPath $_.PSPath).DistributionName }) } else { , @() }
    }
    $facts.user_wslconfig = Invoke-Reader 'user_wslconfig' { Test-Path -LiteralPath (Join-Path (Get-UserProfilePath) '.wslconfig') }
    $facts.time_zone = Invoke-Reader 'time_zone' { (Get-TimeZone).Id }
    $facts.leftovers = Invoke-Reader 'leftovers' { Get-LeftoverFact }
    return $facts
}
