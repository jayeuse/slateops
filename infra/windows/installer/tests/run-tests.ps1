<#
run-tests.ps1 - the plain PowerShell tests of the Windows-side scripts (TASK-0091, W7).

No test framework is downloaded: this file holds the few assertions the tests need. Every
*.Tests.ps1 file next to it is dot-sourced after the library, and each Test-Case runs on its
own. The tests need Windows PowerShell 5.1 on Windows, run as an administrator (the CI runner
is one): some create a disposable local user and folders under %TEMP%. They never start WSL.

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1 [-Filter <text>]

Exit code 0 when every test passes, 1 otherwise (also when no test ran).
#>
[CmdletBinding()]
param([string]$Filter = '')

$libDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\lib'
foreach ($name in @('Common', 'Checks', 'Facts', 'Exec', 'Service', 'Windows', 'Report', 'Uninstall', 'Mdns')) { . (Join-Path $libDir ('{0}.ps1' -f $name)) }
$script:Log.Console = $false

$script:TestResults = New-Object System.Collections.Generic.List[object]
# RUNNER_TEMP on the CI runner: its %TEMP% is an 8.3 short path.
$base = $env:RUNNER_TEMP
if (-not $base) { $base = $env:TEMP }
$script:TestRoot = Join-Path $base ('slateops-w7-tests-{0}' -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
[void][System.IO.Directory]::CreateDirectory($script:TestRoot)

function Test-Case {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][scriptblock]$Body)
    if ($Filter -and ($Name -notlike ('*{0}*' -f $Filter))) { return }
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        & $Body
        $script:TestResults.Add(@{ name = $Name; ok = $true; message = '' })
        Write-Host ('PASS  {0} ({1} ms)' -f $Name, $watch.ElapsedMilliseconds)
    } catch {
        $where = ''
        if ($_.InvocationInfo) { $where = $_.InvocationInfo.PositionMessage }
        $script:TestResults.Add(@{ name = $Name; ok = $false; message = $_.Exception.Message })
        Write-Host ('FAIL  {0}: {1}' -f $Name, $_.Exception.Message)
        if ($where) { Write-Host $where }
    }
}

function Format-TestValue {
    param([AllowNull()]$Value)
    if ($null -eq $Value) { return '<null>' }
    if (($Value -is [System.Collections.IEnumerable]) -and -not ($Value -is [string])) { return ('@(' + ((@($Value) | ForEach-Object { Format-TestValue $_ }) -join ', ') + ')') }
    return ('"{0}" [{1}]' -f $Value, $Value.GetType().Name)
}

function Assert-Equal {
    param([AllowNull()]$Expected, [AllowNull()]$Actual, [string]$Because = '')
    $same = $false
    if (($Expected -is [System.Collections.IEnumerable]) -and -not ($Expected -is [string])) {
        $left = @($Expected); $right = @($Actual)
        $same = ($left.Count -eq $right.Count)
        if ($same) { for ($i = 0; $i -lt $left.Count; $i++) { if (-not ($left[$i] -ceq $right[$i])) { $same = $false; break } } }
    } elseif ($null -eq $Expected) {
        $same = ($null -eq $Actual)
    } else {
        $same = ($null -ne $Actual) -and ($Expected -ceq $Actual)
    }
    if (-not $same) { throw ('expected {0}, got {1}. {2}' -f (Format-TestValue $Expected), (Format-TestValue $Actual), $Because) }
}

function Assert-True {
    param([AllowNull()]$Condition, [string]$Because = '')
    if ($Condition -ne $true) { throw ('expected true. {0}' -f $Because) }
}

function Assert-Throws {
    param([Parameter(Mandatory = $true)][scriptblock]$Body, [string]$Like = '*')
    $thrown = $null
    try { & $Body } catch { $thrown = $_.Exception.Message }
    if ($null -eq $thrown) { throw 'expected an error, none was thrown.' }
    if ($thrown -notlike $Like) { throw ('expected an error like "{0}", got "{1}".' -f $Like, $thrown) }
}

function New-TestDirectory {
    param([Parameter(Mandatory = $true)][string]$Name)
    $path = Join-Path $script:TestRoot $Name
    [void][System.IO.Directory]::CreateDirectory($path)
    return $path
}

# A disposable local user for owner and access-list tests. Its password exists only here.
$script:TestUsers = New-Object System.Collections.Generic.List[string]
function New-TestUser {
    param([Parameter(Mandatory = $true)][string]$Name)
    $existing = Get-LocalUser -Name $Name -ErrorAction SilentlyContinue
    if ($existing) { Remove-LocalUser -Name $Name }
    $secure = ConvertTo-SecureText -Text (New-RandomPassword)
    $user = New-LocalUser -Name $Name -Password $secure -Description 'Slate Operations W7 test user'
    $script:TestUsers.Add($Name)
    return $user.SID.Value
}

try {
    foreach ($file in @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.Tests.ps1' | Sort-Object Name)) {
        Write-Host ('--- {0}' -f $file.Name)
        # An error outside a Test-Case (the file's own setup) is one failure; the next files
        # still run, so one broken setup cannot hide the other tests.
        try { . $file.FullName }
        catch {
            $script:TestResults.Add(@{ name = ('{0} setup' -f $file.Name); ok = $false; message = $_.Exception.Message })
            Write-Host ('FAIL  {0} setup: {1}' -f $file.Name, $_.Exception.Message)
            if ($_.InvocationInfo) { Write-Host $_.InvocationInfo.PositionMessage }
        }
    }
} finally {
    foreach ($name in $script:TestUsers) { Remove-LocalUser -Name $name -ErrorAction SilentlyContinue }
    try { Remove-PathNoFollow -Path $script:TestRoot } catch { Write-Host ('cleanup: {0}' -f $_.Exception.Message) }
}

$failed = @($script:TestResults | Where-Object { -not $_.ok })
Write-Host ('{0} tests, {1} failed' -f $script:TestResults.Count, $failed.Count)
if (($script:TestResults.Count -eq 0) -or ($failed.Count -gt 0)) { exit 1 }
exit 0
