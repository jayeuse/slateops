# Facts.ps1 - the environment facts that each run records at its start (plan 10.4, W7-7).
#
# Every source is a fixed command or a fixed registry or CIM read; no request field and no
# value from Linux names a command, a path or an argument (plan 11.1 W7 security cell).
# BitLocker: VolumeStatus, ProtectionStatus and EncryptionMethod only, never KeyProtector.
# WSL facts of the distribution come from the Exec job wsl-facts (as slateops-svc), because
# the distribution is registered for that account only.
# Windows PowerShell 5.1, ASCII only.

function Initialize-IcuType {
    # Windows 10 1903 and later ship ICU as icu.dll. ucal_getTimeZoneIDForWindowsID maps a
    # Windows time zone ID to an IANA name with ICU's CLDR windowsZones data, so no table is
    # copied into this repository (TASK-0083 carry: CLDR windowsZones).
    if ('SlateOpsSetup.Icu' -as [type]) { return }
    $source = @'
using System;
using System.Runtime.InteropServices;
using System.Text;
namespace SlateOpsSetup
{
    public static class Icu
    {
        [DllImport("icu.dll", CharSet = CharSet.Unicode, CallingConvention = CallingConvention.Cdecl)]
        private static extern int ucal_getTimeZoneIDForWindowsID(string winid, int len, [MarshalAs(UnmanagedType.LPStr)] string region, StringBuilder id, int idCapacity, ref int status);

        // Returns the IANA name, or null when ICU has no mapping or the call fails.
        public static string ToIana(string windowsId)
        {
            StringBuilder buffer = new StringBuilder(128);
            int status = 0;
            int length = ucal_getTimeZoneIDForWindowsID(windowsId, windowsId.Length, null, buffer, buffer.Capacity, ref status);
            if (status > 0 || length <= 0) { return null; }
            return buffer.ToString(0, length);
        }
    }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp
}

function ConvertTo-IanaTimeZone {
    # The IANA name for a Windows time zone ID (region 001, the CLDR default). $null when none.
    param([Parameter(Mandatory = $true)][string]$WindowsId)
    if ($WindowsId -notmatch '^[A-Za-z0-9 .()+,-]{1,64}$') { return $null }
    Initialize-IcuType
    $name = [SlateOpsSetup.Icu]::ToIana($WindowsId)
    if ((-not $name) -or ($name -notmatch '^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*$')) { return $null }
    return $name
}

function Get-EnvironmentFacts {
    # Collects the facts of plan 10.4 that the Windows side reads. Each reader logs its command;
    # a fact that cannot be read is $null and logged.
    param([string]$SetupVersion = '', [string]$DataDrive = '')
    $facts = [ordered]@{ recorded_at = (Get-UtcStamp); setup_version = $SetupVersion }
    $cv = Invoke-Reader 'windows' { Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' }
    if ($cv) {
        $facts.windows = @{
            edition_id      = [string]$cv.EditionID
            display_version = $(if ($cv.PSObject.Properties['DisplayVersion']) { [string]$cv.DisplayVersion } else { $null })
            build           = [string]$cv.CurrentBuildNumber
            ubr             = $(if ($cv.PSObject.Properties['UBR']) { [int]$cv.UBR } else { $null })
        }
    }
    $facts.processor = Invoke-Reader 'processor' {
        $cpu = @(Get-CimInstance -ClassName Win32_Processor)[0]
        $cs = Get-CimInstance -ClassName Win32_ComputerSystem
        @{
            name                    = [string]$cpu.Name
            cores                   = $cpu.NumberOfCores
            threads                 = $cpu.NumberOfLogicalProcessors
            virtualization_firmware = $cpu.VirtualizationFirmwareEnabled
            slat                    = $cpu.SecondLevelAddressTranslationExtensions
            hypervisor_present      = $cs.HypervisorPresent
        }
    }
    $facts.memory = Invoke-Reader 'memory' {
        $cs = Get-CimInstance -ClassName Win32_ComputerSystem
        $os = Get-CimInstance -ClassName Win32_OperatingSystem
        Initialize-NativeInfoType
        @{ total_physical_bytes = [long]$cs.TotalPhysicalMemory; free_physical_kb = [long]$os.FreePhysicalMemory; installed_kb = [long][SlateOpsSetup.NativeInfo]::InstalledMemoryKb() }
    }
    $facts.volumes = Invoke-Reader 'volumes' {
        , @(Get-Volume | Where-Object { $_.DriveLetter } | ForEach-Object {
                @{ letter = ('{0}:' -f $_.DriveLetter); file_system = [string]$_.FileSystemType; drive_type = [string]$_.DriveType; free_bytes = [long]$_.SizeRemaining; size_bytes = [long]$_.Size }
            })
    }
    $mounts = @('C:')
    if ($DataDrive -match '^[A-Za-z]:$') { $mounts += $DataDrive.ToUpperInvariant() }
    $facts.bitlocker = Invoke-Reader 'bitlocker' {
        # Status only. Select-Object keeps the three properties; KeyProtector is never read.
        , @(Get-BitLockerVolume -MountPoint @($mounts | Select-Object -Unique) -ErrorAction Stop |
                Select-Object -Property MountPoint, VolumeStatus, ProtectionStatus, EncryptionMethod |
                ForEach-Object { @{ mount_point = [string]$_.MountPoint; volume_status = [string]$_.VolumeStatus; protection_status = [string]$_.ProtectionStatus; encryption_method = [string]$_.EncryptionMethod } })
    }
    $facts.wsl = Invoke-Reader 'wsl' {
        $version = Get-WslPackageVersion
        @{ package_version = $(if ($version) { $version.ToString() } else { $null }); vmp_state = [string](Get-WindowsOptionalFeature -Online -FeatureName 'VirtualMachinePlatform' -ErrorAction Stop).State }
    }
    $facts.network = Invoke-Reader 'network' {
        @{
            profiles  = @(Get-NetConnectionProfile | ForEach-Object { @{ name = [string]$_.Name; category = [string]$_.NetworkCategory; interface = [string]$_.InterfaceAlias } })
            adapters  = @(Get-NetAdapter | ForEach-Object { @{ name = [string]$_.Name; status = [string]$_.Status; media = [string]$_.MediaType; physical_medium = [string]$_.NdisPhysicalMedium; link_speed = [string]$_.LinkSpeed } })
            ipv4      = @(Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object { @{ interface = [string]$_.InterfaceAlias; address = [string]$_.IPAddress; prefix = [int]$_.PrefixLength } })
            dns       = @(Get-DnsClientServerAddress -AddressFamily IPv4 | ForEach-Object { @{ interface = [string]$_.InterfaceAlias; servers = @($_.ServerAddresses) } })
        }
    }
    $facts.proxy = Invoke-Reader 'proxy' {
        $winhttp = Invoke-Logged -Step 'facts.proxy' -FilePath 'netsh.exe' -ArgumentList @('winhttp', 'show', 'proxy') -NoThrow
        $settings = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
        @{
            winhttp       = @($winhttp.Output)
            user_enabled  = $(if ($settings -and $settings.PSObject.Properties['ProxyEnable']) { [int]$settings.ProxyEnable } else { $null })
            user_auto_url = $(if ($settings -and $settings.PSObject.Properties['AutoConfigURL']) { $true } else { $false })
        }
    }
    $facts.firewall = Invoke-Reader 'firewall' {
        @{
            mdns_rules     = @(Get-NetFirewallRule -DisplayGroup 'mDNS' -ErrorAction SilentlyContinue | ForEach-Object { @{ name = [string]$_.Name; enabled = [string]$_.Enabled; profile = [string]$_.Profile } })
            product_rules  = @(Get-NetFirewallRule -Name $SlateOps.FirewallRuleName -ErrorAction SilentlyContinue | ForEach-Object { @{ name = [string]$_.Name; enabled = [string]$_.Enabled; profile = [string]$_.Profile } })
            hyperv_rules   = @(Get-NetFirewallHyperVRule -Name $SlateOps.HyperVRuleName -ErrorAction SilentlyContinue | ForEach-Object { @{ name = [string]$_.Name; enabled = [string]$_.Enabled } })
            multicast_policy = $(
                $policy = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient' -Name 'EnableMulticast' -ErrorAction SilentlyContinue
                if ($policy) { [int]$policy.EnableMulticast } else { $null })
        }
    }
    $facts.listeners = Invoke-Reader 'listeners' { , @(Get-ListenerFact) }
    $facts.power = Invoke-Reader 'power' {
        $scheme = Invoke-Logged -Step 'facts.power' -FilePath 'powercfg.exe' -ArgumentList @('/getactivescheme') -NoThrow
        $states = Invoke-Logged -Step 'facts.power' -FilePath 'powercfg.exe' -ArgumentList @('/a') -NoThrow
        $sleep = Get-PowerIndex -SubGroup 'SUB_SLEEP' -Setting 'STANDBYIDLE'
        $hibernate = Get-PowerIndex -SubGroup 'SUB_SLEEP' -Setting 'HIBERNATEIDLE'
        $boot = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name 'HiberbootEnabled' -ErrorAction SilentlyContinue
        @{
            active_scheme = @($scheme.Output)
            sleep_states  = @($states.Output)
            sleep_ac      = $(if ($sleep) { $sleep.ac } else { $null })
            hibernate_ac  = $(if ($hibernate) { $hibernate.ac } else { $null })
            fast_startup  = $(if ($boot) { [int]$boot.HiberbootEnabled } else { $null })
        }
    }
    $facts.security = Invoke-Reader 'security' {
        $antivirus = @(Get-CimInstance -Namespace 'root\SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction SilentlyContinue | ForEach-Object { [string]$_.displayName })
        $sac = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -Name 'VerifiedAndReputablePolicyState' -ErrorAction SilentlyContinue
        @{ antivirus = $antivirus; smart_app_control = $(if ($sac) { [int]$sac.VerifiedAndReputablePolicyState } else { $null }) }
    }
    $facts.time = Invoke-Reader 'time' {
        $zone = Get-TimeZone
        $sync = Invoke-Logged -Step 'facts.time' -FilePath 'w32tm.exe' -ArgumentList @('/query', '/status') -NoThrow
        @{ windows_id = [string]$zone.Id; iana = (ConvertTo-IanaTimeZone -WindowsId $zone.Id); utc_offset = [string]$zone.BaseUtcOffset; w32tm = @($sync.Output) }
    }
    $facts.restart_pending = Invoke-Reader 'restart_pending' { Get-RestartPendingFact }
    return $facts
}
