using System.Diagnostics;

namespace QuiverLauncher.Services;

/// <summary>A desktop notification, which never waits for anyone: Quiver may be on a TV through Moonlight.</summary>
public static class DesktopNotification
{
    public static void Show(string title, string body)
    {
        if (!OperatingSystem.IsLinux()) return;
        try
        {
            var start = new ProcessStartInfo("gdbus") { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (var arg in new[] { "call", "--session", "--dest", "org.freedesktop.Notifications", "--object-path", "/org/freedesktop/Notifications",
                "--method", "org.freedesktop.Notifications.Notify", "Quiver Launcher", "0", "quiver-launcher", title, body, "[]", "{}", "10000" })
                start.ArgumentList.Add(arg);
            using var process = Process.Start(start);
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            Trace.WriteLine($"Couldn't show a notification: {ex.Message}");
        }
    }
}
