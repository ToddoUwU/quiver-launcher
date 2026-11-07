# Sourced by the launcher's automated tests: a throwaway home, so no test can read or write the real library.
ISO_HOME=$(mktemp -d "${TMPDIR:-/tmp}/quiver-tests.XXXXXX")
export HOME_REAL=$HOME NUGET_PACKAGES=$HOME/.nuget/packages
export HOME=$ISO_HOME XDG_DATA_HOME=$ISO_HOME/.local/share XDG_CONFIG_HOME=$ISO_HOME/.config XDG_STATE_HOME=$ISO_HOME/.local/state XDG_CACHE_HOME=$ISO_HOME/.cache
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_CLI_HOME=$ISO_HOME
