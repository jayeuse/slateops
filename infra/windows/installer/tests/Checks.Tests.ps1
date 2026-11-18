# Checks.Tests.ps1 - AC-1: the PC check decides each C-check from controlled facts (spec 5.1 to
# 5.3) and the verdict follows spec 5.2. Expected values are literal.

function Get-Check { param([string]$Id, [hashtable]$Facts) return (& ('Test-{0}' -f $Id) -Facts $Facts) }

Test-Case 'AC-1 C01 refuses Windows 10, asks for an update below 22H2, passes 22621, advises when unreadable' {
    Assert-Equal 'stop windows_10' ('{0} {1}' -f (Get-Check C01 @{ build = 19045 }).class, (Get-Check C01 @{ build = 19045 }).code)
    Assert-Equal 'fix too_old' ('{0} {1}' -f (Get-Check C01 @{ build = 22000 }).class, (Get-Check C01 @{ build = 22000 }).code)
    Assert-Equal 'pass' (Get-Check C01 @{ build = 22621 }).class
    $unread = Get-Check C01 @{}
    Assert-Equal 'advice cannot_read check.c01.cannot_read' ('{0} {1} {2}' -f $unread.class, $unread.code, $unread.message_key)
}

Test-Case 'AC-1 C02 passes Pro, Enterprise and Education and stops Home and server editions' {
    foreach ($edition in @('Professional', 'Enterprise', 'Education', 'ProfessionalWorkstation')) { Assert-Equal 'pass' (Get-Check C02 @{ edition_id = $edition }).class $edition }
    Assert-Equal 'home' (Get-Check C02 @{ edition_id = 'Core' }).code
    Assert-Equal 'home' (Get-Check C02 @{ edition_id = 'CoreSingleLanguage' }).code
    Assert-Equal 'edition_not_supported' (Get-Check C02 @{ edition_id = 'ServerDatacenter' }).code
}

Test-Case 'AC-1 C03 stops an Arm processor' {
    Assert-Equal 'stop arm' ('{0} {1}' -f (Get-Check C03 @{ architecture = 'ARM64' }).class, (Get-Check C03 @{ architecture = 'ARM64' }).code)
    Assert-Equal 'pass' (Get-Check C03 @{ architecture = 'AMD64' }).class
}

Test-Case 'AC-1 C04 passes a running hypervisor, fixes virtualization off, stops no SLAT, advises unreadable' {
    Assert-Equal 'pass' (Get-Check C04 @{ hypervisor_present = $true; virtualization_firmware = $false }).class
    $off = Get-Check C04 @{ hypervisor_present = $false; virtualization_firmware = $false; slat = $false; uefi = $true; bitlocker_c = 'Off' }
    Assert-Equal 'fix off' ('{0} {1}' -f $off.class, $off.code)
    Assert-Equal $false $off.values.bitlocker_caution 'BitLocker off on C: needs no caution'
    Assert-Equal $true $off.values.uefi
    Assert-Equal 'stop no_slat' ('{0} {1}' -f (Get-Check C04 @{ hypervisor_present = $false; virtualization_firmware = $true; slat = $false }).class, (Get-Check C04 @{ hypervisor_present = $false; virtualization_firmware = $true; slat = $false }).code)
    $unknown = Get-Check C04 @{ hypervisor_present = $false }
    Assert-Equal 'advice cannot_read' ('{0} {1}' -f $unknown.class, $unknown.code)
    $unreadableC = Get-Check C04 @{ hypervisor_present = $false; virtualization_firmware = $false }
    Assert-Equal $true $unreadableC.values.bitlocker_caution 'an unreadable C: state shows the caution in the Fix dialog (W80-4)'
}

Test-Case 'AC-1 C05 passes at 12 GiB usable and shows the installed amount' {
    Assert-Equal 'pass' (Get-Check C05 @{ total_physical_bytes = [long]12884901888 }).class
    $reserved = Get-Check C05 @{ total_physical_bytes = [long]12884901887; installed_memory_kb = [long]16777216 }
    Assert-Equal 'stop reserved 16 11' ('{0} {1} {2} {3}' -f $reserved.class, $reserved.code, $reserved.values.installed_gb, $reserved.values.usable_gb)
    $small = Get-Check C05 @{ total_physical_bytes = [long]8402640896; installed_memory_kb = [long]8388608 }
    Assert-Equal 'too_small 8' ('{0} {1}' -f $small.code, $small.values.installed_gb)
    $noSmbios = Get-Check C05 @{ total_physical_bytes = [long]8402640896 }
    Assert-Equal 8 $noSmbios.values.installed_gb 'TotalPhysicalMemory rounded up when the installed amount is unknown'
    Assert-Equal 'advice' (Get-Check C05 @{}).class
}

Test-Case 'AC-1 C07 counts only fixed NTFS drives that are not compressed or encrypted' {
    $drives = @(
        @{ letter = 'C:'; drive_type = 'Fixed'; file_system = 'NTFS'; free_bytes = [long]12 * 1GB; compressed = $false; encrypted = $false },
        @{ letter = 'D:'; drive_type = 'Removable'; file_system = 'NTFS'; free_bytes = [long]500 * 1GB; compressed = $false; encrypted = $false },
        @{ letter = 'E:'; drive_type = 'Fixed'; file_system = 'NTFS'; free_bytes = [long]200 * 1GB; compressed = $true; encrypted = $false },
        @{ letter = 'G:'; drive_type = 'Fixed'; file_system = 'FAT32'; free_bytes = [long]100 * 1GB; compressed = $false; encrypted = $false },
        @{ letter = 'H:'; drive_type = 'Network'; file_system = 'NTFS'; free_bytes = [long]900 * 1GB; compressed = $false; encrypted = $false }
    )
    $tooSmall = Get-Check C07 @{ drives = $drives }
    Assert-Equal 'fix too_small C: 12 15' ('{0} {1} {2} {3} {4}' -f $tooSmall.class, $tooSmall.code, $tooSmall.values.letter, $tooSmall.values.free_gb, $tooSmall.values.need_gb)
    $drives += @{ letter = 'F:'; drive_type = 'Fixed'; file_system = 'NTFS'; free_bytes = [long]15 * 1GB; compressed = $false; encrypted = $false }
    $ok = Get-Check C07 @{ drives = $drives }
    Assert-Equal 'pass F:' ('{0} {1}' -f $ok.class, $ok.values.letter)
}

Test-Case 'AC-1 C08 fixes a pending restart and names the values that are set' {
    $pending = Get-Check C08 @{ restart_pending = @{ RebootPending = $false; RebootRequired = $true; PendingFileRenameOperations = $true } }
    Assert-Equal 'fix pending' ('{0} {1}' -f $pending.class, $pending.code)
    Assert-Equal @('PendingFileRenameOperations', 'RebootRequired') $pending.values.values_set
    Assert-Equal 'pass' (Get-Check C08 @{ restart_pending = @{ RebootPending = $false; RebootRequired = $false; PendingFileRenameOperations = $false } }).class
}

Test-Case 'AC-1 C09 to C11 network: not connected, Public, domain' {
    Assert-Equal 'fix not_connected' ('{0} {1}' -f (Get-Check C09 @{ lan = $null }).class, (Get-Check C09 @{ lan = $null }).code)
    Assert-Equal 'fix public' ('{0} {1}' -f (Get-Check C10 @{ lan = @{ category = 'Public'; network_name = 'Cafe' } }).class, (Get-Check C10 @{ lan = @{ category = 'Public'; network_name = 'Cafe' } }).code)
    Assert-Equal 'pass' (Get-Check C10 @{ lan = @{ category = 'Private' } }).class
    Assert-Equal 'advice cannot_read' ('{0} {1}' -f (Get-Check C10 @{ lan = @{ category = '' } }).class, (Get-Check C10 @{ lan = @{ category = '' } }).code)
    Assert-Equal 'stop domain' ('{0} {1}' -f (Get-Check C11 @{ lan = @{ category = 'DomainAuthenticated' } }).class, (Get-Check C11 @{ lan = @{ category = 'DomainAuthenticated' } }).code)
    Assert-Equal 'stop' (Get-Check C11 @{ lan = @{ category = 'Private' }; part_of_domain = $true }).class
}

Test-Case 'AC-1 C12 and C13: proxy, unreachable registry, clock off by more than 30 seconds' {
    Assert-Equal 'proxy' (Get-Check C12 @{ internet = @{ proxy = $true; hosts = @{ 'ghcr.io' = 'ok' } } }).code
    $down = Get-Check C12 @{ internet = @{ proxy = $false; hosts = @{ 'ghcr.io' = 'ok'; 'registry-1.docker.io' = 'fail' } } }
    Assert-Equal 'fix no_connection' ('{0} {1}' -f $down.class, $down.code)
    Assert-Equal @('registry-1.docker.io') $down.values.hosts
    Assert-Equal 'pass' (Get-Check C13 @{ clock_offset_seconds = 30.0 }).class
    $late = Get-Check C13 @{ clock_offset_seconds = -125.0 }
    Assert-Equal 'fix wrong 3' ('{0} {1} {2}' -f $late.class, $late.code, $late.values.offset_minutes)
}

Test-Case 'AC-1 C14 names the program that holds port 80 or 443' {
    $used = Get-Check C14 @{ listeners = @(@{ port = 80; process_name = 'System'; ours = $false }, @{ port = 443; process_name = 'wslrelay'; ours = $true }) }
    Assert-Equal 'fix in_use' ('{0} {1}' -f $used.class, $used.code)
    Assert-Equal @('System') $used.values.programs
    Assert-Equal 'pass' (Get-Check C14 @{ listeners = @() }).class
}

Test-Case 'AC-1 C18 is Fix when module logging covers ScheduledTasks and when the policy is unreadable (W80-8)' {
    Assert-Equal 'fix unreadable' ('{0} {1}' -f (Get-Check C18 @{}).class, (Get-Check C18 @{}).code)
    $covered = Get-Check C18 @{ logging_policy = @{ ModuleLogging = $true; ModuleNames = @('*') } }
    Assert-Equal 'fix policy' ('{0} {1}' -f $covered.class, $covered.code)
    Assert-Equal 'pass' (Get-Check C18 @{ logging_policy = @{ ModuleLogging = $true; ModuleNames = @('Microsoft.PowerShell.*') } }).class
}

Test-Case 'AC-1 C20 to C25 advice items' {
    Assert-Equal 'advice' (Get-Check C20 @{ antivirus = @('Windows Defender', 'Norton 360') }).class
    Assert-Equal @('Norton 360') (Get-Check C20 @{ antivirus = @('Windows Defender', 'Norton 360') }).values.products
    Assert-Equal 'pass' (Get-Check C20 @{ antivirus = @('Windows Defender') }).class
    Assert-Equal 'on_battery' (Get-Check C21 @{ battery = @{ present = $true; on_battery = $true } }).code
    Assert-Equal 'laptop' (Get-Check C21 @{ battery = @{ present = $true; on_battery = $false } }).code
    Assert-Equal 'pass' (Get-Check C21 @{ battery = @{ present = $false; on_battery = $false } }).class
    Assert-Equal 'sleeps' (Get-Check C22 @{ battery = @{ present = $true }; lid_action_ac = 1 }).code
    Assert-Equal 'pass' (Get-Check C22 @{ battery = @{ present = $true }; lid_action_ac = 0 }).class
    Assert-Equal 'wifi' (Get-Check C23 @{ lan = @{ wifi = $true } }).code
    Assert-Equal 'installed' (Get-Check C25 @{ docker_desktop = $true }).code
}

Test-Case 'AC-1 C24 reads BitLocker status of the data drive only, records off without a suggestion, and advises automatic unlock on another drive' {
    $drives = @(
        @{ letter = 'C:'; drive_type = 'Fixed'; file_system = 'NTFS'; free_bytes = [long]40 * 1GB; compressed = $false; encrypted = $false },
        @{ letter = 'D:'; drive_type = 'Fixed'; file_system = 'NTFS'; free_bytes = [long]400 * 1GB; compressed = $false; encrypted = $false }
    )
    $other = Get-Check C24 @{ drives = $drives; bitlocker = @{ 'C:' = 'On'; 'D:' = 'On' } }
    Assert-Equal 'advice auto_unlock D:' ('{0} {1} {2}' -f $other.class, $other.code, $other.values.letter)
    $off = Get-Check C24 @{ drives = $drives; bitlocker = @{ 'C:' = 'On'; 'D:' = 'Off' } }
    Assert-Equal 'off log' ('{0} {1}' -f $off.code, $off.class) 'BitLocker off is recorded, never suggested'
    Assert-Equal 'log' (Get-Check C24 @{ drives = $drives }).class
}

Test-Case 'AC-1 C26 asks for the restart only when the Windows feature is off' {
    $off = Test-C26 -Facts @{ vmp_state = 'Disabled'; wsl_version = [version]'3.0.3.0' } -PinnedWsl ([version]'3.0.3.0')
    Assert-Equal 'auto' $off.class
    Assert-Equal $true $off.values.restart_needed
    $old = Test-C26 -Facts @{ vmp_state = 'Enabled'; wsl_version = [version]'2.6.1.0' } -PinnedWsl ([version]'3.0.3.0')
    Assert-Equal 'auto' $old.class
    Assert-Equal $false $old.values.restart_needed
    Assert-Equal 'pass' (Test-C26 -Facts @{ vmp_state = 'Enabled'; wsl_version = [version]'3.0.5.0' } -PinnedWsl ([version]'3.0.3.0')).class
}

Test-Case 'AC-1 C29 finds kit parts, a lone account and unknown parts without removing anything' {
    $base = @{ account = $false; kit_folder = $false; kit_distro = $false; kit_tasks = $false; kit_rules = $false; slateops_parts = $false; installed_program = $false }
    $kit = $base.Clone(); $kit.account = $true; $kit.kit_tasks = $true
    Assert-Equal 'fix earlier_test' ('{0} {1}' -f (Get-Check C29 @{ leftovers = $kit }).class, (Get-Check C29 @{ leftovers = $kit }).code)
    $lone = $base.Clone(); $lone.account = $true
    Assert-Equal 'leftover_account' (Get-Check C29 @{ leftovers = $lone }).code
    $unknown = $base.Clone(); $unknown.slateops_parts = $true; $unknown.kit_tasks = $true
    Assert-Equal 'stop unknown_parts' ('{0} {1}' -f (Get-Check C29 @{ leftovers = $unknown }).class, (Get-Check C29 @{ leftovers = $unknown }).code)
    $installed = $base.Clone(); $installed.account = $true; $installed.slateops_parts = $true; $installed.installed_program = $true
    Assert-Equal 'pass' (Get-Check C29 @{ leftovers = $installed }).class
}

Test-Case 'AC-1 S91-1 a kit folder that fails the kit safety check is unknown parts (Stop)' {
    $parts = @{ account = $true; kit_folder = $false; kit_folder_unsafe = $true; kit_distro = $false; kit_tasks = $true; kit_rules = $false; slateops_parts = $false; installed_program = $false }
    Assert-Equal 'stop unknown_parts' ('{0} {1}' -f (Get-Check C29 @{ leftovers = $parts }).class, (Get-Check C29 @{ leftovers = $parts }).code)
}

Test-Case 'AC-1 S91-1 a junction at the kit folder reads as unsafe, and nothing below it is read' {
    $target = New-TestDirectory 's91-1-check-target'
    [void][System.IO.Directory]::CreateDirectory((Join-Path $target 'distro\vhd'))
    [System.IO.File]::WriteAllText((Join-Path $target 'distro\vhd\ext4.vhdx'), 'x')
    $link = Join-Path $script:TestRoot 's91-1-check-kit'
    $null = & cmd.exe /c mklink /J $link $target 2>&1
    $kit = @{ AccountName = 'slateops-w7nokit'; Root = $link; TaskPath = '\SlateOpsW7NoKit\'; RuleName = 'SlateOpsW7NoKit-rule'; HyperVRule = 'SlateOpsW7NoKit-hv' }
    $facts = Get-LeftoverFact -Kit $kit
    Assert-Equal $true $facts.kit_folder_unsafe
    Assert-Equal $false $facts.kit_distro 'the distro file behind the junction is not read'
    Assert-Equal 'stop' (Get-Check C29 @{ leftovers = $facts }).class
}

Test-Case 'AC-1 the verdict is not suitable on a Stop, counts the Fix items, and carries the restart line' {
    $stop = Get-PcVerdict -Results @((New-CheckResult 'C02' 'stop' 'home'), (New-CheckResult 'C10' 'fix' 'public'))
    Assert-Equal 'not_suitable' $stop.verdict
    $fix = Get-PcVerdict -Results @((New-CheckResult 'C10' 'fix' 'public'), (New-CheckResult 'C18' 'fix' 'policy'), (New-CheckResult 'C21' 'advice' 'laptop'))
    Assert-Equal 'needs_fixes 2' ('{0} {1}' -f $fix.verdict, $fix.fix_count)
    $ready = Get-PcVerdict -Results @((New-CheckResult 'C26' 'auto' 'prepare' @{ restart_needed = $true }), (New-CheckResult 'C21' 'advice' 'laptop'))
    Assert-Equal 'ready' $ready.verdict
    Assert-Equal $true $ready.restart_needed
}

Test-Case 'AC-1 the recheck runs exactly the spec 5.2 checks' {
    $ids = @(Invoke-PcCheck -Facts @{} -Only $SlateOpsCheck.RecheckIds | ForEach-Object { $_.id })
    Assert-Equal @('C08', 'C09', 'C10', 'C12', 'C13', 'C14', 'C21') $ids
}

Test-Case 'AC-1 the check reads this PC without changing it and returns every check (W7 plus C17 from W8; DEC-0039 no C15, C16, C30)' {
    $facts = Get-PcCheckFacts
    $results = @(Invoke-PcCheck -Facts $facts -PinnedWsl ([version]'3.0.3.0'))
    Assert-Equal 27 $results.Count
    foreach ($result in $results) {
        Assert-True ($result.message_key -match '^check\.c[0-9]{2}\.[a-z_]+$') $result.message_key
        Assert-True (@('pass', 'stop', 'fix', 'advice', 'auto', 'log') -contains $result.class) $result.id
    }
}

Test-Case 'W14-D5 the check names each check as it reads it, in order, beside its result file' {
    $dir = New-TestDirectory 'w14-d5-check'
    $path = Join-Path $dir 'check-1.json.progress'
    Set-HelperProgressFile -Path $path
    try { $null = Get-PcCheckFacts -ProgressJob 'check' } finally { Set-HelperProgressFile -Path '' }
    $lines = @([System.IO.File]::ReadAllLines($path))
    Assert-Equal 'progress check 1/30 c01 start' $lines[0]
    $last = 0
    foreach ($line in $lines) {
        Assert-True ($line -cmatch '^progress check ([0-9]+)/30 c[0-9]{2} start$') $line
        $number = [int]$Matches[1]
        Assert-True ($number -ge $last) ('{0} after {1}' -f $number, $last)
        $last = $number
    }
    Assert-Equal 'progress check 29/30 c29 start' $lines[$lines.Count - 1]
}

Test-Case 'W14-D5 the recheck counts only its seven checks, and no file means no line' {
    $dir = New-TestDirectory 'w14-d5-recheck'
    $path = Join-Path $dir 'check-2.json.progress'
    Set-HelperProgressFile -Path $path
    try { $null = Get-PcCheckFacts -ProgressJob 'recheck' -ProgressIds $SlateOpsCheck.RecheckIds } finally { Set-HelperProgressFile -Path '' }
    $lines = @([System.IO.File]::ReadAllLines($path))
    Assert-Equal 'progress recheck 1/7 c08 start' $lines[0]
    foreach ($line in $lines) { Assert-True ($line -cmatch '^progress recheck [1-7]/7 c(08|09|12|14|21) start$') $line }
    Write-HelperProgress -Job 'pc' -Number 1 -Total 3 -Key 'vmp'
    Assert-Equal $lines.Count @([System.IO.File]::ReadAllLines($path)).Count
}

Test-Case 'W9 review item 3 C29 offers to remove the parts of an earlier uninstall; other unknown parts still stop' {
    $base = @{ account = $false; kit_folder = $false; kit_distro = $false; kit_tasks = $false; kit_rules = $false; slateops_parts = $true; installed_program = $false; uninstall_log = $true }
    Assert-Equal 'fix uninstall_leftovers' ('{0} {1}' -f (Get-Check C29 @{ leftovers = $base }).class, (Get-Check C29 @{ leftovers = $base }).code)
    $nolog = $base.Clone(); $nolog.uninstall_log = $false
    Assert-Equal 'stop unknown_parts' ('{0} {1}' -f (Get-Check C29 @{ leftovers = $nolog }).class, (Get-Check C29 @{ leftovers = $nolog }).code)
    $installed = $base.Clone(); $installed.installed_program = $true
    Assert-Equal 'pass' (Get-Check C29 @{ leftovers = $installed }).class
}
