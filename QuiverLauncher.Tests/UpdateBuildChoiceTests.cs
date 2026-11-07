using FluentAssertions;
using QuiverLauncher.Core.Models;
using QuiverLauncher.Core.Services;
using Xunit;

namespace QuiverLauncher.Tests;

public class UpdateBuildChoiceTests
{
    private static DownloadAssetSelection Choices(params string[] names) =>
        new(names.Select(n => new GitHubAsset { name = n }).ToList(), [], null);

    [Theory]
    [InlineData("3SX-c6b8e98-linux.tar.gz", "3SX-aaaaaaa-linux.tar.gz")]
    [InlineData("DK64Recompiled-Linux-X64-Release-1-0-3.zip", "DK64Recompiled-Linux-X64-Release-1-0-4.zip")]
    public void A_build_whose_name_changes_still_finds_its_sort(string installed, string expected)
    {
        var choices = Choices(expected, expected.Replace("Linux-X64", "Windows").Replace("linux.tar.gz", "windows.zip"));
        DownloadAssetPolicy.MatchSameSort(choices, installed)!.name.Should().Be(expected);
    }

    [Fact]
    public void A_linux_copy_never_takes_the_only_windows_build()
    {
        DownloadAssetPolicy.OnlyBuildFor(Choices("Game-windows-x64-v1.2.zip"), windows: false).Should().BeNull();
        DownloadAssetPolicy.MatchSameSort(Choices("Game-windows-x64-v1.2.zip"), "Game-linux-1.1-x86_64.AppImage").Should().BeNull();
    }

    [Fact]
    public void A_linux_copy_takes_its_linux_build_and_leaves_the_flatpak_out()
    {
        var choices = Choices("Game-Linux-Flatpak-X64.zip", "Game-Linux-X64.zip", "Game-Windows.zip");
        DownloadAssetPolicy.OnlyBuildFor(choices, windows: false)!.name.Should().Be("Game-Linux-X64.zip");
    }

    [Fact]
    public void A_windows_copy_takes_its_x64_build_over_arm64()
    {
        var choices = Choices("Game-linux-x86_64.AppImage", "Game-win32-arm64.zip", "Game-win32-x86_64.zip");
        DownloadAssetPolicy.OnlyBuildFor(choices, windows: true)!.name.Should().Be("Game-win32-x86_64.zip");
    }

    [Fact]
    public void Two_builds_of_one_system_still_ask()
    {
        DownloadAssetPolicy.OnlyBuildFor(Choices("Game_Linux.tar.gz", "Game_Steam_Deck_Linux.tar.gz"), windows: false).Should().BeNull();
    }

    [Theory]
    [InlineData("v0.0.8.8.3", "v0.0.8.8.1", true)]
    [InlineData("v0.0.8.8.1", "v0.0.8.8.3", false)]
    [InlineData("v1.2.3", "v1.2.3", false)]
    [InlineData("1.2", "1.2.0", false)]
    [InlineData("Version1.0.14", "Version1.0.12", true)]
    public void Versions_compare_by_all_their_numbers(string candidate, string baseline, bool newer) =>
        ReleaseVersionIdentity.IsNewerVersion(candidate, baseline).Should().Be(newer);
}
