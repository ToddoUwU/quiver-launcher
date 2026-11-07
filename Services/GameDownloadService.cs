using System.Text.Json;
using QuiverLauncher.Core.Models;
using QuiverLauncher.Core.Services;
using QuiverLauncher.Models;

namespace QuiverLauncher.Services;

public static class GameDownloadService
{
    public static string Context(GameInfo game, GitHubRelease release, AppSettings settings) =>
        JsonSerializer.Serialize(new { game.IdentityKey, release.tag_name, Platform = GameInfo.GetPlatformIdentifier(settings), game.ReleaseAssetFilter });

    public static DownloadAssetSelection Prepare(GameInfo game, GitHubRelease release, AppSettings settings)
    {
        var result = DownloadAssetPolicy.Select(release, GameInfo.GetPlatformIdentifier(settings), game.ReleaseAssetFilter);
        var context = Context(game, release, settings);
        var selected = result.Eligible.Concat(result.Uncertain).FirstOrDefault(a =>
            a.name == game.SelectedDownload?.name && a.browser_download_url == game.SelectedDownload?.browser_download_url);
        if (game.DownloadSelectionContext != context || selected == null) game.ClearDownloadSelection();
        else game.SelectedDownload = selected;
        game.DownloadSelectionContext = context;
        game.DownloadChoices = result;
        game.AvailableDownloads = result.Eligible.ToList();
        return result;
    }

    public static bool TrySelectPlatformDownload(GameInfo game, GitHubRelease? release, AppSettings settings)
    {
        game.ClearDownloadSelection();
        if (release == null) return false;
        var result = Prepare(game, release, settings);
        game.SelectedDownload = InstalledBuildIn(game, result, release) ?? result.Automatic;
        return game.SelectedDownload != null;
    }

    /// <summary>
    /// The file in <paramref name="choices"/> that is the same build as the one installed, so an update keeps the
    /// player's build (their Linux one, not the Windows one beside it) without asking. Null when nothing is recorded
    /// or no single file matches.
    /// </summary>
    public static GitHubAsset? InstalledBuildIn(GameInfo game, DownloadAssetSelection choices, GitHubRelease release) =>
        game.InstalledBuild is { } build && game.IsInstalled
            ? DownloadAssetPolicy.MatchInstalled(choices, build.FileName, game.InstalledVersion, release.tag_name)
                ?? DownloadAssetPolicy.MatchSameSort(choices, build.FileName)
            : null;

    /// <summary>
    /// The download an update installs without asking: the build already installed, else the only build for the system
    /// the installed copy runs on. Null means the player has to choose, which also covers a release that only has a
    /// Windows build for a Linux copy: unpacked beside it, it would leave the old Linux program the one that starts.
    /// </summary>
    public static GitHubAsset? ForUpdate(GameInfo game, DownloadAssetSelection choices, GitHubRelease release, string gamesFolder)
    {
        if (InstalledBuildIn(game, choices, release) is { } same) return same;
        return InstalledCopyIsWindows(game, gamesFolder) is { } windows
            ? DownloadAssetPolicy.OnlyBuildFor(choices, windows)
            : choices.Automatic;
    }

    /// <summary>Whether the installed copy is a Windows build, from its record, its runner, then its folder. Null when that can't be told.</summary>
    private static bool? InstalledCopyIsWindows(GameInfo game, string gamesFolder)
    {
        if (!OperatingSystem.IsLinux() || !game.IsInstalled) return null;
        if (game.InstalledBuild is { } build) return PlatformAssetMatcher.IsWindowsAsset(build.FileName);
        if (WindowsRunnerService.ParseRunnerKind(game.LinuxRunner) is LinuxWindowsRunnerKind.Proton or LinuxWindowsRunnerKind.Wine) return true;
        return FolderHoldsWindowsBuild(game.GetInstallPath(gamesFolder));
    }

    /// <summary>False when a folder holds a Linux program, true when it only holds Windows ones, null when it holds neither.</summary>
    internal static bool? FolderHoldsWindowsBuild(string folder)
    {
        if (!Directory.Exists(folder)) return null;
        var windows = false;
        var files = Directory.EnumerateFiles(folder, "*", new EnumerationOptions { RecurseSubdirectories = true, MaxRecursionDepth = 2, IgnoreInaccessible = true });
        foreach (var file in files)
        {
            if (file.EndsWith(".appimage", StringComparison.OrdinalIgnoreCase) || IsLinuxProgram(file)) return false;
            windows |= file.EndsWith(".exe", StringComparison.OrdinalIgnoreCase);
        }
        return windows ? true : null;
    }

    private static bool IsLinuxProgram(string file)
    {
        var name = Path.GetFileName(file);
        if (name.Contains(".so", StringComparison.OrdinalIgnoreCase)) return false;
        try
        {
            Span<byte> head = stackalloc byte[4];
            using var stream = File.OpenRead(file);
            return stream.ReadAtLeast(head, 4, throwOnEndOfStream: false) == 4 && head.SequenceEqual("\u007fELF"u8);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    public static void SelectExplicit(GameInfo game, GitHubRelease release, AppSettings settings, GitHubAsset asset)
    {
        var result = Prepare(game, release, settings);
        game.SelectedDownload = result.Eligible.Concat(result.Uncertain).FirstOrDefault(a =>
            a.name == asset.name && a.browser_download_url == asset.browser_download_url);
        if (game.SelectedDownload == null) throw new InvalidOperationException("This download is no longer available for the selected platform and release.");
    }
}
