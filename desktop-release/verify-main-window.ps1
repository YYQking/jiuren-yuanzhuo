param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
if (-not ('RoundtableWindowCheck' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class RoundtableWindowInfo {
    public string Title;
    public string ClassName;
    public bool Visible;
    public int Width;
    public int Height;
}
public static class RoundtableWindowCheck {
    private delegate bool Callback(IntPtr window, IntPtr context);
    [StructLayout(LayoutKind.Sequential)]
    private struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] private static extern bool EnumWindows(Callback callback, IntPtr context);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr window, StringBuilder text, int count);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetClassName(IntPtr window, StringBuilder text, int count);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr window, out Rect rect);
    public static RoundtableWindowInfo[] Read(int pid) {
        var result = new List<RoundtableWindowInfo>();
        EnumWindows((window, context) => {
            uint owner;
            GetWindowThreadProcessId(window, out owner);
            if (owner != pid) return true;
            var title = new StringBuilder(1024);
            var className = new StringBuilder(256);
            Rect rect;
            GetWindowText(window, title, title.Capacity);
            GetClassName(window, className, className.Capacity);
            GetWindowRect(window, out rect);
            result.Add(new RoundtableWindowInfo {
                Title = title.ToString(), ClassName = className.ToString(),
                Visible = IsWindowVisible(window),
                Width = rect.Right - rect.Left, Height = rect.Bottom - rect.Top
            });
            return true;
        }, IntPtr.Zero);
        return result.ToArray();
    }
}
'@
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.HasExited) {
        throw 'Application exited before its main window was ready.'
    }
    $windows = @([RoundtableWindowCheck]::Read($ProcessId))
    $errors = @($windows | Where-Object { $_.Visible -and $_.ClassName -eq '#32770' })
    if ($errors.Count -gt 0) {
        throw "Startup error dialog: $($errors[0].Title)"
    }
    $main = @($windows | Where-Object {
        $_.Visible -and $_.Title -eq '九人圆桌' -and
        $_.ClassName.StartsWith('Qt') -and $_.Width -ge 600 -and $_.Height -ge 400
    })
    if ($main.Count -gt 0) {
        Start-Sleep -Seconds 2
        $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $process -or $process.HasExited) {
            throw 'Application exited after opening its main window.'
        }
        $confirmed = @([RoundtableWindowCheck]::Read($ProcessId) | Where-Object {
            $_.Visible -and $_.Title -eq '九人圆桌' -and $_.ClassName.StartsWith('Qt')
        })
        if ($confirmed.Count -eq 0) { throw 'Main window disappeared after startup.' }
        return $confirmed[0]
    }
    Start-Sleep -Milliseconds 200
} while ([DateTime]::UtcNow -lt $deadline)
throw 'No visible Qt main window appeared within the startup timeout.'
