using System.Diagnostics;
using System.IO.Compression;
using System.Net;
using FluentAssertions;
using QuiverLauncher.Core.Models;
using QuiverLauncher.Core.Services;
using QuiverLauncher.Models;
using QuiverLauncher.Services;
using QuiverLauncher.ViewModels;

namespace QuiverLauncher.Tests;

/// <summary>
/// What a player expects of game updates, from the real download and install code with only the network faked: they
/// happen by themselves, they never stop to ask, and they leave a game being played alone.
/// </summary>
public sealed class AutoUpdateEndToEndTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "quiver-auto-update-" + Guid.NewGuid().ToString("N"));
    private string GamePath => Path.Combine(_root, "game");

    public AutoUpdateEndToEndTests()
    {
        Directory.CreateDirectory(GamePath);
        var cache = Path.Combine(_root, "cache");
        Directory.CreateDirectory(cache);
        GitHubApiCache.Initialize(cache);
    }

    public void Dispose() => TestFixtures.CleanupDirectory(_root);

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Updating_a_windows_build_never_opens_the_runner_menu(bool automatic)
    {
        Assert.SkipUnless(OperatingSystem.IsLinux(), "Runners are a Linux feature.");
        var game = await InstalledAsync("Game-Windows-v1.zip", "proton", ("game.exe", "MZ"));
        var player = new Player();
        using var client = Serving(ZipOf(("game.exe", "MZ"), ("v2.txt", "new")));

        await GameDownloadInstallService.DownloadAndInstallAsync(game, client, _root, Release("Game-Windows-v2.zip"), new AppSettings(),
            GameStatus.UpdateAvailable, automatic ? new AutomaticGameDownloadDialogs(player) : player, releaseMode: ReleaseInstallMode.ExplicitRelease);

        player.Asked.Should().BeEmpty("the installed copy already has its Proton setup");
        File.ReadAllText(Path.Combine(GamePath, "version.txt")).Trim().Should().Be("v2");
        File.Exists(Path.Combine(GamePath, "v2.txt")).Should().BeTrue();
        game.LinuxRunner.Should().Be("proton");
        game.Status.Should().Be(GameStatus.Installed);
    }

    [Fact]
    public async Task A_first_install_of_a_windows_build_still_asks_how_to_run_it()
    {
        Assert.SkipUnless(OperatingSystem.IsLinux(), "Runners are a Linux feature.");
        var game = new GameInfo { Name = "Game", Repository = "fixture/game", FolderName = "game" };
        var player = new Player();
        using var client = Serving(ZipOf(("game.exe", "MZ")));

        await GameDownloadInstallService.DownloadAndInstallAsync(game, client, _root, Release("Game-Windows-v2.zip"), new AppSettings(),
            GameStatus.NotInstalled, player, releaseMode: ReleaseInstallMode.ExplicitRelease);

        player.Asked.Should().ContainSingle().Which.Should().BeOneOf("runner", "no runner");
    }

    [Fact]
    public async Task Moving_a_linux_copy_to_a_windows_build_still_asks_how_to_run_it()
    {
        Assert.SkipUnless(OperatingSystem.IsLinux(), "Runners are a Linux feature.");
        var game = await InstalledAsync("Game-linux-v1.AppImage", null, ("Game-linux-v1.AppImage", "\u007fELF"));
        var player = new Player();
        using var client = Serving(ZipOf(("game.exe", "MZ")));

        await GameDownloadInstallService.DownloadAndInstallAsync(game, client, _root, Release("Game-Windows-v2.zip"), new AppSettings(),
            GameStatus.UpdateAvailable, player, releaseMode: ReleaseInstallMode.ExplicitRelease);

        player.Asked.Should().ContainSingle().Which.Should().BeOneOf("runner", "no runner");
    }

    [Fact]
    public async Task Automatic_updates_answer_everything_themselves()
    {
        var player = new Player();
        var automatic = new AutomaticGameDownloadDialogs(player);
        var existing = new LinuxWindowsRunnerConfig { Kind = LinuxWindowsRunnerKind.Proton, ProtonPath = "/proton" };

        (await automatic.ConfigureWindowsRunnerAsync(GamePath, existing)).Should().BeSameAs(existing);
        (await automatic.ConfigureWindowsRunnerAsync(GamePath)).Should().NotBeNull();
        (await automatic.ConfirmDownloadWithoutRunnerAsync()).Should().BeTrue();
        await automatic.ShowRateLimitExceededAsync();
        await automatic.ShowGitLabRateLimitExceededAsync();
        await automatic.ShowErrorAsync("Disk full", "Update failed");

        player.Asked.Should().BeEmpty("nobody may be there to answer, and an open dialog would hold back every other update");
    }

    [Fact]
    public async Task Updates_wait_for_a_game_being_played_and_install_after_it_closes()
    {
        var previousDelay = LauncherUpdateWorkflow.PlayingRetryDelay;
        LauncherUpdateWorkflow.PlayingRetryDelay = TimeSpan.FromMilliseconds(20);
        var store = new Store();
        using var manager = new GameManager(store);
        using var library = new LibraryViewModel(manager, new SettingsViewModel(store));
        var session = new LauncherSession();
        var game = new GameInfo { Name = "Waiting", Repository = "owner/waiting", AutoUpdate = true, Status = GameStatus.UpdateAvailable };
        manager.Games.Add(game);
        var playing = true;
        var installed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var installs = 0;
        var workflow = new LauncherUpdateWorkflow(manager, library.Settings, library, new ShellViewModel(), session, null!, new Presentation(),
            () => null, new VelopackUpdateService(), () => Task.CompletedTask,
            _ => { installs++; game.Status = GameStatus.Installed; installed.TrySetResult(); return Task.FromResult(true); },
            _ => playing ? "/games/being-played" : null);
        try
        {
            (await workflow.ApplyAutoUpdatesAsync(false)).Should().Be(0);
            installs.Should().Be(0, "a game is being played");
            await Task.Delay(100, TestContext.Current.CancellationToken);
            installs.Should().Be(0, "it's still being played");

            playing = false;
            await installed.Task.WaitAsync(TimeSpan.FromSeconds(10), TestContext.Current.CancellationToken);
            installs.Should().Be(1);
        }
        finally
        {
            await session.DisposeAsync();
            LauncherUpdateWorkflow.PlayingRetryDelay = previousDelay;
        }
    }

    [Fact]
    public async Task A_game_running_from_its_own_folder_is_found_however_it_was_started()
    {
        Assert.SkipUnless(OperatingSystem.IsLinux(), "Reads /proc.");
        var program = Path.Combine(GamePath, "game");
        File.Copy(ResolveSleep(), program);
        File.SetUnixFileMode(program, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);

        RunningGames.FindFolderInUse([GamePath]).Should().BeNull("nothing has started yet");
        using var game = Process.Start(new ProcessStartInfo(program, "30") { WorkingDirectory = _root })!;
        try
        {
            await WaitUntilAsync(() => RunningGames.FindFolderInUse([GamePath]) != null);
            RunningGames.FindFolderInUse([Path.Combine(_root, "other"), GamePath]).Should().Be(GamePath);
        }
        finally
        {
            game.Kill();
            await game.WaitForExitAsync(TestContext.Current.CancellationToken);
        }
        await WaitUntilAsync(() => RunningGames.FindFolderInUse([GamePath]) == null);
    }

    [Theory]
    [InlineData("")]
    [InlineData("/")]
    [InlineData("/usr")]
    [InlineData("relative/folder")]
    public void A_folder_that_would_match_everything_never_counts(string folder)
    {
        RunningGames.FindFolderInUse([folder]).Should().BeNull();
    }

    [Fact]
    public async Task A_game_working_from_its_folder_counts_but_a_shell_left_there_does_not()
    {
        Assert.SkipUnless(OperatingSystem.IsLinux(), "Reads /proc.");
        // Proton: the program lives elsewhere and the game's folder is where it works.
        var elsewhere = Path.Combine(_root, "proton");
        Directory.CreateDirectory(elsewhere);
        var runner = Path.Combine(elsewhere, "runner");
        File.Copy(ResolveSleep(), runner);
        File.SetUnixFileMode(runner, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);

        using var shell = Process.Start(new ProcessStartInfo("/bin/sh", ["-c", "exec sleep 30"]) { WorkingDirectory = GamePath })!;
        try
        {
            await Task.Delay(200, TestContext.Current.CancellationToken);
            RunningGames.FindFolderInUse([GamePath]).Should().BeNull("a system program working there isn't the game");
        }
        finally
        {
            shell.Kill();
            await shell.WaitForExitAsync(TestContext.Current.CancellationToken);
        }

        using var proton = Process.Start(new ProcessStartInfo(runner, "30") { WorkingDirectory = GamePath })!;
        try
        {
            await WaitUntilAsync(() => RunningGames.FindFolderInUse([GamePath]) == GamePath);
        }
        finally
        {
            proton.Kill();
            await proton.WaitForExitAsync(TestContext.Current.CancellationToken);
        }
    }

    private static string ResolveSleep()
    {
        foreach (var path in new[] { "/usr/bin/sleep", "/bin/sleep" })
            if (File.Exists(path))
                return path;
        throw new FileNotFoundException("sleep");
    }

    private static async Task WaitUntilAsync(Func<bool> condition)
    {
        for (var i = 0; i < 100 && !condition(); i++)
            await Task.Delay(50, TestContext.Current.CancellationToken);
        condition().Should().BeTrue();
    }

    private async Task<GameInfo> InstalledAsync(string installedFile, string? runner, params (string Name, string Contents)[] files)
    {
        foreach (var (name, contents) in files)
            File.WriteAllText(Path.Combine(GamePath, name), contents);
        File.WriteAllText(Path.Combine(GamePath, "version.txt"), "v1");
        File.WriteAllText(Path.Combine(GamePath, "installed-build.txt"), installedFile + "\n" + new string('a', 64) + "\n");
        var game = new GameInfo { Name = "Game", Repository = "fixture/" + Guid.NewGuid().ToString("N"), FolderName = "game", LinuxRunner = runner, AutoUpdate = true };
        using var client = Serving([]);
        await GameStatusService.CheckStatusAsync(game, client, _root, checkRemoteVersion: false, applyCachedRelease: false);
        game.IsInstalled.Should().BeTrue();
        game.LatestVersion = "v2";
        game.Status = GameStatus.UpdateAvailable;
        return game;
    }

    private static GitHubRelease Release(string asset) => new()
    {
        tag_name = "v2",
        assets = [new GitHubAsset { name = asset, browser_download_url = "https://example.test/" + asset }],
    };

    private static HttpClient Serving(byte[] file) => new(new Download(file));

    private sealed class Download(byte[] file) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(file) });
    }

    private static byte[] ZipOf(params (string Name, string Contents)[] files)
    {
        using var stream = new MemoryStream();
        using (var zip = new ZipArchive(stream, ZipArchiveMode.Create, true))
        {
            foreach (var (name, contents) in files)
            {
                using var writer = new StreamWriter(zip.CreateEntry(name).Open());
                writer.Write(contents);
            }
        }
        return stream.ToArray();
    }

    /// <summary>Stands in for the dialogs and notes every question reaching the player.</summary>
    private sealed class Player : IGameDownloadDialogs
    {
        public List<string> Asked { get; } = [];
        public Task<bool> ConfirmDownloadWithoutRunnerAsync() { Asked.Add("no runner"); return Task.FromResult(true); }
        public Task<LinuxWindowsRunnerConfig?> ConfigureWindowsRunnerAsync(string gamePath, LinuxWindowsRunnerConfig? existing = null, bool isInstall = true)
        {
            Asked.Add("runner");
            return Task.FromResult<LinuxWindowsRunnerConfig?>(existing ?? new());
        }
        public Task ShowRateLimitExceededAsync() { Asked.Add("rate limit"); return Task.CompletedTask; }
        public Task ShowGitLabRateLimitExceededAsync() { Asked.Add("rate limit"); return Task.CompletedTask; }
        public Task ShowErrorAsync(string message, string title) { Asked.Add("error: " + message); return Task.CompletedTask; }
        public Task<bool> ConfirmUnverifiedReleaseAsync(string appName, string version, ReleaseCheck check) { Asked.Add("unverified"); return Task.FromResult(true); }
    }

    private sealed class Presentation : IUpdatePresentation
    {
        public bool CanPresentResults => false;
        public bool CanShowFailureSummary => false;
        public void OpenAppUpdatesReview() { }
        public void OpenBrowse() { }
        public void UpdateStatusChanged() { }
    }

    private sealed class Store : ISettingsStore
    {
        public AppSettings Current { get; } = new();
        public AppSettings Load() => Current;
        public void Save(AppSettings settings) { }
    }
}
