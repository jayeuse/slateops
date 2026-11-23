<#
screenshot.ps1 - AC-F8 (TASK-0097): one window of the screenshot build (/DScreenshots) as a PNG.

The screenshot build calls this script for each page and state that it draws. PrintWindow with
PW_RENDERFULLCONTENT draws the window into a bitmap without bringing it to the front; when that
fails, the script copies the window's area of the screen. Windows PowerShell 5.1, ASCII only.

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File screenshot.ps1 -Handle <hwnd> -Path <file.png>

Exit code 0 when the file was written, 1 otherwise.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][long]$Handle,
    [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Drawing
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class SlateOpsShot
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr window, out RECT rect);
    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr window, IntPtr dc, uint flags);
}
'@
    $window = [IntPtr]$Handle
    $rect = New-Object SlateOpsShot+RECT
    if (-not [SlateOpsShot]::GetWindowRect($window, [ref]$rect)) { throw 'GetWindowRect failed' }
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if (($width -le 0) -or ($height -le 0)) { throw ('the window has no size ({0} x {1})' -f $width, $height) }
    $bitmap = New-Object System.Drawing.Bitmap $width, $height
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $dc = $graphics.GetHdc()
            # 2 = PW_RENDERFULLCONTENT (the DWM content of the window).
            $printed = [SlateOpsShot]::PrintWindow($window, $dc, 2)
            $graphics.ReleaseHdc($dc)
            if (-not $printed) {
                $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, (New-Object System.Drawing.Size $width, $height))
            }
        } finally { $graphics.Dispose() }
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $bitmap.Dispose() }
    exit 0
} catch {
    Write-Host ('screenshot failed: {0}' -f $_.Exception.Message)
    exit 1
}
