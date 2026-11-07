namespace QuiverLauncher.Services;

/// <summary>Whether to log Avalonia warnings and trace lines. Off unless asked for: QUIVER_TRACE=1 quiver</summary>
public static class LauncherDiagnostics
{
    public static bool Enabled { get; } = Environment.GetEnvironmentVariable("QUIVER_TRACE") is { Length: > 0 } value && value != "0";
}
