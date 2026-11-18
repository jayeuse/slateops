# Service.ps1 - the hidden account slateops-svc and the tasks \SlateOps\Exec and \SlateOps\Start
# (plan 3.1, W7-6). Every setting is the boot-test kit's (10-setup.ps1, proven in REQ-0022:
# E1, E2, E4, E5, E6); only the names and the script paths change.
# Windows PowerShell 5.1, ASCII only.

function Get-ExecTaskDefinition {
    # Kit: the on-demand task that runs one allow-listed job as the service account.
    param([Parameter(Mandatory = $true)][string]$ScriptsDir)
    return @{
        TaskName  = $SlateOps.ExecTaskName
        Execute   = (Join-Path $SlateOpsPaths.System32 'WindowsPowerShell\v1.0\powershell.exe')
        Argument  = ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $ScriptsDir 'exec.ps1'))
        Trigger   = 'none'
        RunLevel  = 'Limited'
        Settings  = [ordered]@{
            # 8 hours, not the kit's 2 (parent decision, DEC-0036, TASK-0095): the update job
            # runs its backup and, after a failure, a restore in one run.
            ExecutionTimeLimit         = 'PT8H'
            MultipleInstances          = 'IgnoreNew'
            AllowStartIfOnBatteries    = $true
            DontStopIfGoingOnBatteries = $true
            StartWhenAvailable         = $true
        }
        Description = 'Slate Operations: runs one allow-listed job as slateops-svc.'
    }
}

function Get-StartTaskDefinition {
    # Kit: the boot task. Each setting and why (kit 10-setup.ps1):
    #   At startup trigger        starts before anyone signs in.
    #   Repetition every 1 min    starts the task again within a minute if it ever stopped
    #                             (MultipleInstances IgnoreNew makes a repeat a no-op while it runs).
    #   Password logon type       "Run whether user is logged on or not": runs in session 0.
    #   ExecutionTimeLimit PT0S   no time limit; the default stops a task after 72 hours.
    #   RestartCount/Interval     Task Scheduler tries again every minute if the start fails.
    #   Batteries settings        a laptop on battery does not block or stop it.
    #   StartWhenAvailable        a missed start runs as soon as possible.
    #   Priority 4                normal priority (the default 7 is below normal).
    param([Parameter(Mandatory = $true)][string]$ScriptsDir)
    return @{
        TaskName  = $SlateOps.StartTaskName
        Execute   = (Join-Path $SlateOpsPaths.System32 'WindowsPowerShell\v1.0\powershell.exe')
        Argument  = ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $ScriptsDir 'start.ps1'))
        Trigger   = 'AtStartup'
        Repetition = 'PT1M'
        RunLevel  = 'Limited'
        Settings  = [ordered]@{
            ExecutionTimeLimit         = 'PT0S'
            RestartCount               = 999
            RestartInterval            = 'PT1M'
            MultipleInstances          = 'IgnoreNew'
            AllowStartIfOnBatteries    = $true
            DontStopIfGoingOnBatteries = $true
            StartWhenAvailable         = $true
            DontStopOnIdleEnd          = $true
            Priority                   = 4
        }
        Description = 'Slate Operations: start the server part at boot and keep it running.'
    }
}

function New-TaskSettingsFromDefinition {
    # Builds the ScheduledTasks objects of a definition (no registration).
    param([Parameter(Mandatory = $true)][hashtable]$Definition)
    $s = $Definition.Settings
    $parameters = @{
        ExecutionTimeLimit = [System.Xml.XmlConvert]::ToTimeSpan($s.ExecutionTimeLimit)
        MultipleInstances  = $s.MultipleInstances
    }
    if ($s.Contains('RestartCount')) {
        $parameters.RestartCount = $s.RestartCount
        $parameters.RestartInterval = [System.Xml.XmlConvert]::ToTimeSpan($s.RestartInterval)
    }
    if ($s.Contains('Priority')) { $parameters.Priority = $s.Priority }
    $settings = New-ScheduledTaskSettingsSet @parameters -AllowStartIfOnBatteries:$s.AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries:$s.DontStopIfGoingOnBatteries -StartWhenAvailable:$s.StartWhenAvailable `
        -DontStopOnIdleEnd:($s.Contains('DontStopOnIdleEnd') -and $s.DontStopOnIdleEnd)
    $action = New-ScheduledTaskAction -Execute $Definition.Execute -Argument $Definition.Argument
    $trigger = $null
    if ($Definition.Trigger -eq 'AtStartup') {
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval ([System.Xml.XmlConvert]::ToTimeSpan($Definition.Repetition))).Repetition
    }
    return @{ Settings = $settings; Action = $action; Trigger = $trigger }
}

# ---------------------------------------------------------------------------
# The account
# ---------------------------------------------------------------------------

function ConvertTo-SecureText {
    # Kit: builds a SecureString one character at a time, so the plain text never passes through
    # a logged cmdlet parameter (ConvertTo-SecureString -AsPlainText would).
    param([Parameter(Mandatory = $true)][string]$Text)
    $secure = New-Object System.Security.SecureString
    foreach ($character in $Text.ToCharArray()) { $secure.AppendChar($character) }
    $secure.MakeReadOnly()
    return $secure
}

function New-RandomPassword {
    # Kit: 32 characters from a cryptographic random source; meets the Windows complexity rules.
    $lower = 'abcdefghijkmnopqrstuvwxyz'; $upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'; $digits = '23456789'; $symbols = '-_.:+=@%'
    $all = $lower + $upper + $digits + $symbols
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    try {
        $bytes = New-Object byte[] 64
        $rng.GetBytes($bytes)
        $chars = New-Object System.Collections.Generic.List[char]
        $chars.Add($lower[$bytes[0] % $lower.Length]); $chars.Add($upper[$bytes[1] % $upper.Length])
        $chars.Add($digits[$bytes[2] % $digits.Length]); $chars.Add($symbols[$bytes[3] % $symbols.Length])
        for ($i = 4; $i -lt 32; $i++) { $chars.Add($all[$bytes[$i] % $all.Length]) }
        return (-join $chars)
    } finally { $rng.Dispose() }
}

function Initialize-LsaRightsType {
    # Kit: Local Security Authority calls for user rights. Windows has no cmdlet for them.
    if ('SlateOpsSetup.LsaRights' -as [type]) { return }
    $source = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Principal;

namespace SlateOpsSetup
{
    public static class LsaRights
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct LSA_UNICODE_STRING { public ushort Length; public ushort MaximumLength; public IntPtr Buffer; }

        [StructLayout(LayoutKind.Sequential)]
        private struct LSA_OBJECT_ATTRIBUTES
        {
            public int Length; public IntPtr RootDirectory; public IntPtr ObjectName; public uint Attributes;
            public IntPtr SecurityDescriptor; public IntPtr SecurityQualityOfService;
        }

        private const uint POLICY_VIEW_LOCAL_INFORMATION = 0x00000001;
        private const uint POLICY_CREATE_ACCOUNT = 0x00000010;
        private const uint POLICY_LOOKUP_NAMES = 0x00000800;
        private const uint STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034;

        [DllImport("advapi32.dll")] private static extern uint LsaOpenPolicy(IntPtr systemName, ref LSA_OBJECT_ATTRIBUTES objectAttributes, uint desiredAccess, out IntPtr policyHandle);
        [DllImport("advapi32.dll")] private static extern uint LsaAddAccountRights(IntPtr policyHandle, byte[] accountSid, LSA_UNICODE_STRING[] userRights, uint countOfRights);
        [DllImport("advapi32.dll")] private static extern uint LsaRemoveAccountRights(IntPtr policyHandle, byte[] accountSid, [MarshalAs(UnmanagedType.U1)] bool allRights, LSA_UNICODE_STRING[] userRights, uint countOfRights);
        [DllImport("advapi32.dll")] private static extern uint LsaEnumerateAccountRights(IntPtr policyHandle, byte[] accountSid, out IntPtr userRights, out uint countOfRights);
        [DllImport("advapi32.dll")] private static extern uint LsaFreeMemory(IntPtr buffer);
        [DllImport("advapi32.dll")] private static extern uint LsaClose(IntPtr policyHandle);
        [DllImport("advapi32.dll")] private static extern int LsaNtStatusToWinError(uint status);

        private static IntPtr OpenPolicy()
        {
            LSA_OBJECT_ATTRIBUTES attributes = new LSA_OBJECT_ATTRIBUTES();
            attributes.Length = Marshal.SizeOf(typeof(LSA_OBJECT_ATTRIBUTES));
            IntPtr handle;
            Check(LsaOpenPolicy(IntPtr.Zero, ref attributes, POLICY_VIEW_LOCAL_INFORMATION | POLICY_CREATE_ACCOUNT | POLICY_LOOKUP_NAMES, out handle), "LsaOpenPolicy");
            return handle;
        }

        private static void Check(uint status, string call)
        {
            if (status != 0) { throw new System.ComponentModel.Win32Exception(LsaNtStatusToWinError(status), call + " failed"); }
        }

        private static byte[] SidBytes(string sid)
        {
            SecurityIdentifier identifier = new SecurityIdentifier(sid);
            byte[] bytes = new byte[identifier.BinaryLength];
            identifier.GetBinaryForm(bytes, 0);
            return bytes;
        }

        private static LSA_UNICODE_STRING[] ToLsaStrings(string[] rights)
        {
            LSA_UNICODE_STRING[] result = new LSA_UNICODE_STRING[rights.Length];
            for (int i = 0; i < rights.Length; i++)
            {
                result[i].Buffer = Marshal.StringToHGlobalUni(rights[i]);
                result[i].Length = (ushort)(rights[i].Length * 2);
                result[i].MaximumLength = (ushort)(rights[i].Length * 2 + 2);
            }
            return result;
        }

        private static void FreeLsaStrings(LSA_UNICODE_STRING[] strings)
        {
            for (int i = 0; i < strings.Length; i++) { if (strings[i].Buffer != IntPtr.Zero) { Marshal.FreeHGlobal(strings[i].Buffer); } }
        }

        public static void Add(string sid, string[] rights)
        {
            IntPtr policy = OpenPolicy();
            LSA_UNICODE_STRING[] strings = ToLsaStrings(rights);
            try { Check(LsaAddAccountRights(policy, SidBytes(sid), strings, (uint)strings.Length), "LsaAddAccountRights"); }
            finally { FreeLsaStrings(strings); LsaClose(policy); }
        }

        public static void Remove(string sid, string[] rights)
        {
            IntPtr policy = OpenPolicy();
            LSA_UNICODE_STRING[] strings = ToLsaStrings(rights);
            try
            {
                uint status = LsaRemoveAccountRights(policy, SidBytes(sid), false, strings, (uint)strings.Length);
                if (status != STATUS_OBJECT_NAME_NOT_FOUND) { Check(status, "LsaRemoveAccountRights"); }
            }
            finally { FreeLsaStrings(strings); LsaClose(policy); }
        }

        public static string[] Get(string sid)
        {
            IntPtr policy = OpenPolicy();
            try
            {
                IntPtr buffer;
                uint count;
                uint status = LsaEnumerateAccountRights(policy, SidBytes(sid), out buffer, out count);
                if (status == STATUS_OBJECT_NAME_NOT_FOUND) { return new string[0]; }
                Check(status, "LsaEnumerateAccountRights");
                List<string> rights = new List<string>();
                int size = Marshal.SizeOf(typeof(LSA_UNICODE_STRING));
                for (int i = 0; i < count; i++)
                {
                    LSA_UNICODE_STRING item = (LSA_UNICODE_STRING)Marshal.PtrToStructure(new IntPtr(buffer.ToInt64() + (long)i * size), typeof(LSA_UNICODE_STRING));
                    rights.Add(Marshal.PtrToStringUni(item.Buffer, item.Length / 2));
                }
                LsaFreeMemory(buffer);
                return rights.ToArray();
            }
            finally { LsaClose(policy); }
        }
    }
}
'@
    Add-Type -TypeDefinition $source -Language CSharp
}

function Get-AccountDefinition {
    # The account as data: a standard user (Users only), batch logon, no interactive, Remote
    # Desktop or network sign-in, hidden from the sign-in screen (kit; plan 3.1).
    return @{
        Name        = $SlateOps.AccountName
        FullName    = 'Slate Operations service'
        # Windows limits a local user's description to 48 characters (New-LocalUser).
        Description = 'Runs Slate Operations. Uninstall removes it.'
        Groups      = @($SlateOps.SidUsers)
        Rights      = @($SlateOps.AccountRights)
        Hidden      = $true
        PasswordNeverExpires     = $true
        UserMayNotChangePassword = $true
        AccountNeverExpires      = $true
    }
}

function Get-TaskFolderState {
    # 'absent', 'product' (only the Exec and Start tasks, or one of them) or 'unknown' (an empty
    # folder or another task in it; S91-3: setup does not take over a folder it did not make).
    param([string]$FolderPath = ('\' + $SlateOps.TaskFolder))
    $service = New-Object -ComObject 'Schedule.Service'
    $service.Connect()
    try { $folder = $service.GetFolder($FolderPath) } catch { return 'absent' }
    $names = @(@($folder.GetTasks(1)) | ForEach-Object { [string]$_.Name })
    if ($names.Count -eq 0) { return 'unknown' }
    foreach ($name in $names) { if (@($SlateOps.ExecTaskName, $SlateOps.StartTaskName) -notcontains $name) { return 'unknown' } }
    return 'product'
}

function Install-ServiceAccountAndTasks {
    # Creates slateops-svc, gives it its rights and folder access, and registers both tasks with
    # one random password that exists only in this process. Never reuses an existing account
    # (spec C29): the caller removes a leftover first, after the person selects Continue.
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $step = 'setup.service'
    if (Get-LocalUser -Name $SlateOps.AccountName -ErrorAction SilentlyContinue) {
        return New-StepResult -Code 'account_exists' -MessageKey 'setup.service.account_exists'
    }
    if ((Get-TaskFolderState) -eq 'unknown') {
        return New-StepResult -Code 'task_folder_unknown' -MessageKey 'setup.service.task_folder_unknown'
    }
    # S91-4: the folder that the account record goes into, checked right before the write.
    Assert-TreeWritable -Tree $Layout.StateTree -Directory $Layout.State -ServiceSid (Get-RecordedServiceSid -Layout $Layout)
    # P2-3: a recorded account that is gone (a partial earlier step, or a removal) leaves its
    # entries in the trees; they go before the new account is made.
    $stale = Get-RecordedServiceSid -Layout $Layout
    if ($stale) {
        Write-RunLog $step 'INFO' ('remove the entries of the earlier account {0}' -f $stale)
        # R-9: a profile that an earlier removal left (it was still loaded then) goes first, so
        # the SID is not dropped from the record with its profile still on the PC.
        $null = Remove-ServiceProfile -Sid $stale
        Remove-ServiceAccess -Tree $Layout.StateTree -Sid $stale
        if ($Layout.DataRoot) { Remove-ServiceAccess -Tree $Layout.DataTree -Sid $stale }
        $record = Read-WindowsChanges -Layout $Layout
        $record.Remove('account_sid')
        Save-WindowsChanges -Layout $Layout -Record $record
    }
    # R7 again right before the password moves (spec 5.2, W80-8): an unreadable policy stops too.
    try { $covered = @(Get-PasswordModuleLogged) } catch { return New-StepResult -Code 'logging_policy_unreadable' -MessageKey 'check.c18.unreadable' }
    if ($covered.Count -gt 0) { return New-StepResult -Code 'logging_policy' -MessageKey 'check.c18.policy' }

    $definition = Get-AccountDefinition
    $password = New-RandomPassword
    Register-LogSecret $password
    try {
        $secure = ConvertTo-SecureText -Text $password
        Write-RunLog $step 'INFO' ('create the standard local account {0} (random password, not stored, not shown)' -f $definition.Name)
        $userParameters = @{
            Name = $definition.Name; Password = $secure; FullName = $definition.FullName; Description = $definition.Description
            PasswordNeverExpires = $definition.PasswordNeverExpires; UserMayNotChangePassword = $definition.UserMayNotChangePassword
            AccountNeverExpires = $definition.AccountNeverExpires
        }
        New-LocalUser @userParameters | Out-Null
        $account = Get-LocalUser -Name $definition.Name
        $sid = $account.SID.Value
        # Recorded at once, so a later failure still leaves the SID known (P2-3).
        $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
        $record = Read-WindowsChanges -Layout $Layout
        if (-not $record.Contains('userlist_key_existed')) {
            $record.userlist_key_existed = [bool](Test-Path -LiteralPath $userList)
            $record.specialaccounts_key_existed = [bool](Test-Path -LiteralPath (Split-Path -Parent $userList))
        }
        $record.account_sid = $sid
        Save-WindowsChanges -Layout $Layout -Record $record
        foreach ($group in $definition.Groups) {
            try { Add-LocalGroupMember -SID $group -Member $account }
            catch [Microsoft.PowerShell.Commands.MemberExistsException] { Write-RunLog $step 'INFO' ('  already a member of {0}' -f $group) }
        }
        Initialize-LsaRightsType
        [SlateOpsSetup.LsaRights]::Add($sid, [string[]]$definition.Rights)
        Write-RunLog $step 'INFO' ('  rights now: {0}' -f (([SlateOpsSetup.LsaRights]::Get($sid)) -join ', '))
        if ($definition.Hidden) {
            if (-not (Test-Path -LiteralPath $userList)) { New-Item -Path $userList -Force | Out-Null }
            New-ItemProperty -LiteralPath $userList -Name $definition.Name -PropertyType DWord -Value 0 -Force | Out-Null
            Write-RunLog $step 'INFO' '  hidden from the sign-in screen'
        }

        # S91-5: the one call that gives the new account its folder entries.
        $problems = @(Grant-ServiceAccess -Tree $Layout.StateTree -ServiceSid $sid)
        if ($Layout.DataRoot) { $problems += @(Grant-ServiceAccess -Tree $Layout.DataTree -ServiceSid $sid) }
        if ($problems.Count -gt 0) {
            Write-RunLog $step 'FAIL' ('folder safety check: {0}' -f ($problems -join '; '))
            return New-StepResult -Code 'folder_unsafe' -MessageKey 'setup.folder_unsafe'
        }

        Register-ServiceTasks -Layout $Layout -AccountName $definition.Name -Password $password
    } finally {
        $password = $null
        $secure = $null
    }
    return New-StepResult -Code 'created' -MessageKey 'setup.service.created' -Values @{ account_sid = $sid }
}

function Register-ServiceTasks {
    # Registers \SlateOps\Exec and \SlateOps\Start as the account (the service step, and Repair
    # in W9). The password reaches only Register-ScheduledTask.
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][string]$AccountName, [Parameter(Mandatory = $true)][string]$Password)
    $qualified = '{0}\{1}' -f [Environment]::MachineName, $AccountName
    foreach ($taskDefinition in @((Get-ExecTaskDefinition -ScriptsDir $Layout.Scripts), (Get-StartTaskDefinition -ScriptsDir $Layout.Scripts))) {
        $objects = New-TaskSettingsFromDefinition -Definition $taskDefinition
        $parameters = @{
            TaskPath = $SlateOps.TaskPath; TaskName = $taskDefinition.TaskName; Action = $objects.Action; Settings = $objects.Settings
            User = $qualified; Password = $Password; RunLevel = $taskDefinition.RunLevel; Force = $true; Description = $taskDefinition.Description
        }
        if ($objects.Trigger) { $parameters.Trigger = $objects.Trigger }
        Write-RunLog 'setup.service' 'INFO' ('register the task {0}{1} as {2}' -f $SlateOps.TaskPath, $taskDefinition.TaskName, $AccountName)
        Register-ScheduledTask @parameters | Out-Null
    }
}

# ---------------------------------------------------------------------------
# The record of Windows changes (for uninstall, W9): old values and what setup added
# ---------------------------------------------------------------------------

function Read-WindowsChanges {
    param([Parameter(Mandatory = $true)][hashtable]$Layout)
    $path = Join-Path $Layout.State 'windows-changes.json'
    $record = [ordered]@{}
    if (Test-Path -LiteralPath $path) {
        $value = Read-JsonFile -Path $path
        foreach ($key in $value.Keys) { $record[$key] = $value[$key] }
    }
    return $record
}

function Save-WindowsChanges {
    param([Parameter(Mandatory = $true)][hashtable]$Layout, [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Record)
    $Record['updated_at'] = Get-UtcStamp
    Write-JsonFile -Path (Join-Path $Layout.State 'windows-changes.json') -Value $Record
}
