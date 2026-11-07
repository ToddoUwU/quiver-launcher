namespace QuiverLauncher.Services;

/// <summary>
/// Finds what is being played from the system itself, so a game counts however it was started: from Quiver, from a
/// Moonlight tile or from a terminal. Quiver can't otherwise see a game it didn't start, or one whose launcher exited.
/// </summary>
public static class RunningGames
{
    private static readonly string[] SystemPrograms = ["/usr/", "/bin/", "/sbin/", "/snap/"];

    /// <summary>A terminal or editor left open in a game's folder isn't playing it.</summary>
    private static readonly HashSet<string> Tools = new(StringComparer.Ordinal) { "claude", "code", "emacs", "git", "less", "node", "nvim", "vim" };

    /// <summary>The first of <paramref name="folders"/> a running program belongs to; null when none, or off Linux.</summary>
    public static string? FindFolderInUse(IReadOnlyCollection<string> folders, string procRoot = "/proc")
    {
        if (folders.Count == 0 || !OperatingSystem.IsLinux() || !Directory.Exists(procRoot)) return null;
        var roots = new List<string>(folders.Count);
        foreach (var folder in folders)
        {
            // A blank or top-level folder would match every program on the computer.
            if (Path.IsPathFullyQualified(folder) && Path.GetDirectoryName(Path.TrimEndingDirectorySeparator(folder)) is { Length: > 1 })
                roots.Add(Path.TrimEndingDirectorySeparator(folder) + Path.DirectorySeparatorChar);
        }
        if (roots.Count == 0) return null;
        var self = Environment.ProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture);
        foreach (var process in Directory.EnumerateDirectories(procRoot))
        {
            var pid = Path.GetFileName(process);
            if (!char.IsAsciiDigit(pid[0]) || pid == self) continue;
            var exe = LinkTarget(Path.Combine(process, "exe"));
            if (exe != null && Match(roots, exe) is { } running) return running;
            if (exe != null && IsSystemProgramOrTool(exe)) continue;
            if (LinkTarget(Path.Combine(process, "cwd")) is { } cwd && Match(roots, cwd + Path.DirectorySeparatorChar) is { } working) return working;
        }
        return null;
    }

    private static string? Match(List<string> roots, string path)
    {
        foreach (var root in roots)
            if (path.StartsWith(root, StringComparison.Ordinal))
                return root[..^1];
        return null;
    }

    private static bool IsSystemProgramOrTool(string exe)
    {
        var name = Path.GetFileName(exe.AsSpan());
        // Wine from the system still runs the game in the game's folder.
        if (name.Contains("wine", StringComparison.OrdinalIgnoreCase)) return false;
        foreach (var system in SystemPrograms)
            if (exe.StartsWith(system, StringComparison.Ordinal))
                return true;
        return Tools.Contains(name.ToString());
    }

    private static string? LinkTarget(string link)
    {
        try { return new FileInfo(link).LinkTarget; }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return null; }
    }
}
