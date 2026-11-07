using System.Diagnostics;

namespace QuiverLauncher.Services;

/// <summary>
/// Stamps how long each stage of starting took, when QUIVER_STARTUP_TRACE names a file. Off, it costs one null check.
/// It's what tools/quiver-bench and a performance check read, so a change that slows startup shows up as numbers.
/// </summary>
public static class StartupTimeline
{
    private static readonly string? Output = Environment.GetEnvironmentVariable("QUIVER_STARTUP_TRACE");
    private static readonly object Gate = new();

    public static void Mark(string stage)
    {
        if (Output == null) return;
        // From when the process began, so runtime startup before Main counts too.
        var ms = (DateTime.Now - Process.GetCurrentProcess().StartTime).TotalMilliseconds;
        lock (Gate)
        {
            try { File.AppendAllText(Output, $"{ms,8:0} {stage}\n"); }
            catch (IOException) { }
        }
    }
}
