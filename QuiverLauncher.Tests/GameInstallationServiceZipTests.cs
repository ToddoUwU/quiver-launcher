using System.IO.Compression;
using System.Text;
using FluentAssertions;
using QuiverLauncher.Core.Services;

namespace QuiverLauncher.Tests;

public class GameInstallationServiceZipTests
{
    private const int UnixExecutableAttributes = unchecked((int)0x81ED0000);

    [Fact]
    public async Task InstallOrUpdateGameAsync_keeps_nested_executable_and_unix_mode()
    {
        var archivePath = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.zip");
        var gamePath = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));

        try
        {
            var launcher = Encoding.UTF8.GetBytes(new string('L', 2048));
            var biosTool = Encoding.UTF8.GetBytes(new string('B', 2048));
            File.WriteAllBytes(archivePath, CreateZip(
            [
                new ZipSpec("Yu_Gi_Oh_Forbidden_Memories_Recompiled", launcher, UnixExecutableAttributes),
                new ZipSpec("psxrecomp/recompiler/build/psxrecomp-bios", biosTool, UnixExecutableAttributes),
            ]));

            await GameInstallationService.InstallOrUpdateGameAsync(
                archivePath,
                gamePath,
                "ygofm-0.5.3-linux-x64.zip",
                "v0.5.3");

            var nested = Path.Combine(gamePath, "psxrecomp", "recompiler", "build", "psxrecomp-bios");
            File.ReadAllBytes(nested).Should().Equal(biosTool);
            File.Exists(Path.Combine(gamePath, "Yu_Gi_Oh_Forbidden_Memories_Recompiled")).Should().BeTrue();

            if (!OperatingSystem.IsWindows())
            {
                File.GetUnixFileMode(nested).Should().HaveFlag(UnixFileMode.UserExecute);
            }
        }
        finally
        {
            TryDelete(archivePath, gamePath);
        }
    }

    [Fact]
    public void ExtractZipManaged_turns_backslash_entry_names_into_directories()
    {
        var archivePath = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.zip");
        var extractPath = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));

        try
        {
            var bios = Encoding.UTF8.GetBytes("openbios");
            var mod = Encoding.UTF8.GetBytes("mod");
            File.WriteAllBytes(archivePath, CreateZip(
            [
                new ZipSpec(@"bios\openbios.bin", bios),
                new ZipSpec(@"mods\preloaded\readme.txt", mod),
            ], normalizeSlashes: false));

            GameInstallationService.ExtractZipManaged(archivePath, extractPath);

            File.ReadAllBytes(Path.Combine(extractPath, "bios", "openbios.bin")).Should().Equal(bios);
            File.ReadAllBytes(Path.Combine(extractPath, "mods", "preloaded", "readme.txt")).Should().Equal(mod);
            Directory.GetFiles(extractPath, "*", SearchOption.TopDirectoryOnly)
                .Select(Path.GetFileName)
                .Should().NotContain(name => name.Contains('\\'));
        }
        finally
        {
            TryDelete(archivePath, extractPath);
        }
    }

    [Fact]
    public async Task InstallOrUpdateGameAsync_update_replaces_root_build_from_doubly_wrapped_zip()
    {
        // Star Fox Enhanced 0.0.8.8.3 ships dist/StarFoxEnhanced-linux-x64/starfox_pc. Updating an install whose root
        // already held the old starfox_pc left the new build in StarFoxEnhanced-linux-x64/ and kept launching the old one.
        var archivePath = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.zip");
        var gamePath = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));

        try
        {
            Directory.CreateDirectory(gamePath);
            File.WriteAllBytes(Path.Combine(gamePath, "starfox_pc"), Encoding.UTF8.GetBytes(new string('O', 2048)));
            File.WriteAllText(Path.Combine(gamePath, "pregame.cfg"), "user settings");
            File.WriteAllText(Path.Combine(gamePath, "version.txt"), "v0.0.8");

            var newBuild = Encoding.UTF8.GetBytes(new string('N', 2048));
            File.WriteAllBytes(archivePath, CreateZip(
            [
                new ZipSpec("dist/StarFoxEnhanced-linux-x64/", []),
                new ZipSpec("dist/StarFoxEnhanced-linux-x64/starfox_pc", newBuild, UnixExecutableAttributes),
                new ZipSpec("dist/StarFoxEnhanced-linux-x64/licenses/fonts/README.md", Encoding.UTF8.GetBytes("fonts")),
            ]));

            await GameInstallationService.InstallOrUpdateGameAsync(
                archivePath,
                gamePath,
                "StarFoxEnhanced-0.0.8.8.3-linux-x64.zip",
                "v0.0.8.8.3");

            File.ReadAllBytes(Path.Combine(gamePath, "starfox_pc")).Should().Equal(newBuild);
            File.ReadAllText(Path.Combine(gamePath, "pregame.cfg")).Should().Be("user settings");
            File.Exists(Path.Combine(gamePath, "licenses", "fonts", "README.md")).Should().BeTrue();
            Directory.Exists(Path.Combine(gamePath, "StarFoxEnhanced-linux-x64")).Should().BeFalse();
            Directory.Exists(Path.Combine(gamePath, "dist")).Should().BeFalse();
            File.ReadAllText(Path.Combine(gamePath, "version.txt")).Should().Be("v0.0.8.8.3");
        }
        finally
        {
            TryDelete(archivePath, gamePath);
        }
    }

    [Fact]
    public void GetEffectiveExtractionSource_stops_at_files_several_folders_or_an_app_bundle()
    {
        var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        try
        {
            var deep = Directory.CreateDirectory(Path.Combine(root, "a", "b", "c")).FullName;
            File.WriteAllText(Path.Combine(deep, "game"), "x");
            GameInstallationService.GetEffectiveExtractionSource(root).Should().Be(deep);

            Directory.CreateDirectory(Path.Combine(root, "a", "b", "other"));
            GameInstallationService.GetEffectiveExtractionSource(root).Should().Be(Path.Combine(root, "a", "b"));

            File.WriteAllText(Path.Combine(root, "README.txt"), "x");
            GameInstallationService.GetEffectiveExtractionSource(root).Should().Be(root);

            var bundleRoot = Path.Combine(root, "mac");
            Directory.CreateDirectory(Path.Combine(bundleRoot, "Wrapper", "Game.app", "Contents"));
            GameInstallationService.GetEffectiveExtractionSource(bundleRoot).Should().Be(Path.Combine(bundleRoot, "Wrapper"));
        }
        finally
        {
            if (Directory.Exists(root))
                Directory.Delete(root, true);
        }
    }

    [Fact]
    public async Task InstallOrUpdateGameAsync_keeps_empty_directory_after_single_folder_unwrap()
    {
        var archivePath = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.zip");
        var gamePath = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));

        try
        {
            var binary = Encoding.UTF8.GetBytes(new string('E', 2048));
            File.WriteAllBytes(archivePath, CreateZip(
            [
                new ZipSpec("Game-1.2.3/game.exe", binary),
                new ZipSpec("Game-1.2.3/empty/", []),
            ]));

            await GameInstallationService.InstallOrUpdateGameAsync(
                archivePath,
                gamePath,
                "Game-1.2.3.zip",
                "v1.2.3");

            File.ReadAllBytes(Path.Combine(gamePath, "game.exe")).Should().Equal(binary);
            Directory.Exists(Path.Combine(gamePath, "empty")).Should().BeTrue();
            Directory.Exists(Path.Combine(gamePath, "Game-1.2.3")).Should().BeFalse();
        }
        finally
        {
            TryDelete(archivePath, gamePath);
        }
    }

    [Fact]
    public void MoveDirectoryContents_moves_top_level_folders_including_empty_ones()
    {
        var source = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        var dest = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));

        try
        {
            Directory.CreateDirectory(Path.Combine(source, "mods", "empty"));
            File.WriteAllText(Path.Combine(source, "game.toml"), "title = \"demo\"");

            GameInstallationService.MoveDirectoryContents(source, dest);

            File.ReadAllText(Path.Combine(dest, "game.toml")).Should().Be("title = \"demo\"");
            Directory.Exists(Path.Combine(dest, "mods", "empty")).Should().BeTrue();
        }
        finally
        {
            if (Directory.Exists(source))
                Directory.Delete(source, true);
            if (Directory.Exists(dest))
                Directory.Delete(dest, true);
        }
    }

    static void TryDelete(string archivePath, string directoryPath)
    {
        if (File.Exists(archivePath))
            File.Delete(archivePath);
        if (Directory.Exists(directoryPath))
            Directory.Delete(directoryPath, true);
    }

    readonly record struct ZipSpec(string Path, byte[] Content, int? ExternalAttributes = null);

    static byte[] CreateZip(IReadOnlyList<ZipSpec> entries, bool normalizeSlashes = true)
    {
        using var zipStream = new MemoryStream();
        using (var archive = new ZipArchive(zipStream, ZipArchiveMode.Create, leaveOpen: true))
        {
            foreach (var spec in entries)
            {
                var name = normalizeSlashes ? spec.Path.Replace('\\', '/') : spec.Path;
                var entry = archive.CreateEntry(name, CompressionLevel.Optimal);
                if (spec.ExternalAttributes is int attributes)
                    entry.ExternalAttributes = attributes;

                if (spec.Content.Length == 0 && name.EndsWith('/'))
                    continue;

                using var entryStream = entry.Open();
                entryStream.Write(spec.Content);
            }
        }

        return zipStream.ToArray();
    }
}
