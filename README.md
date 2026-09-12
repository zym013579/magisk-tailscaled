# Magisk Tailscaled

[![Build and release](https://github.com/zym013579/magisk-tailscaled/actions/workflows/release.yml/badge.svg)](https://github.com/zym013579/magisk-tailscaled/actions/workflows/release.yml)

Magisk/KernelSU module for running Tailscale on rooted Android, maintained by
**zym013579**. Based on anasfanani's module and the Android adaptations in
[zym013579/tailscale-android-cli](https://github.com/zym013579/tailscale-android-cli).
The current module is **v2.1.0.0**, based on **Tailscale v1.102.4**.

## Install

Download from [Releases](https://github.com/zym013579/magisk-tailscaled/releases):

- `Magisk-Tailscaled-v2.1.0.0-full.zip`: recommended; includes ARMv7 and ARM64
  tailscaled and jq binaries, so installation works offline.
- `Magisk-Tailscaled-v2.1.0.0.zip`: lightweight; downloads the pinned Android
  release from your fork and verifies checksums during installation.

Install through Magisk or KernelSU Manager, then reboot. Existing state files are
preserved and previous module files are backed up under `/data/adb/tailscale/backups/`.
The module supports ARMv7 and ARM64; x86_64 binaries are available separately in the
Android CLI repository. A rooted physical Android device is needed for full runtime
validation; successful builds alone do not confirm every phone/kernel combination.

```sh
su -c 'tailscale login'
su -c 'tailscale set --accept-dns=false'
su -c 'tailscale status'
su -c 'tailscaled.service status'
```

Follow the login URL to authorize your device. Service commands include `start`,
`stop`, `restart`, `status`, `log daemon`, and `log service`.

## Networking and local configuration

Settings: `/data/adb/tailscale/settings.sh`. The preserved local startup command is:

```sh
tailscaled -no-logs-no-support --tun=userspace-networking --socks5-server=127.0.0.1:1099
```

Userspace mode provides a SOCKS5 proxy at `127.0.0.1:1099`; applications must use
that proxy to make outbound tailnet connections. It does not automatically route
all Android application traffic. For example:

```sh
curl --socks5-hostname 127.0.0.1:1099 http://your-tailnet-host:port/
```

For native TUN routing on a compatible rooted device, remove the two userspace
arguments in settings.sh and restart the service. Test route, VPN and DNS behavior
on your device. This module no longer bundles hev-socks5-tunnel or its old scripts.

State: `/data/adb/tailscale/tailscaled.state`. Logs: `/data/adb/tailscale/run/`.
Before enabling SSH or advertising subnet/exit-node routes, confirm the relevant
permissions and tailnet policies for your device.

## Build and release with GitHub Actions

The **Build and release Magisk module** workflow runs for main pushes, PRs, tags,
and manual dispatch. It:

1. Checks out the exact Android source commit pinned in `binaries.env`.
2. Compiles Android ARMv7 and ARM64 binaries with Go and NDK r27c.
3. Verifies ELF metadata and pinned jq downloads.
4. Packages and tests both installation zips and uploads workflow artifacts.
5. Publishes a release on a matching `v2.1.0.0` tag or manual `publish=true`.

No personal access token is required. The workflow uses `GITHUB_TOKEN` for releases.
Ordinary pushes and PRs build artifacts without publishing. The fourth module
version component being nonzero marks a prerelease.

The online installer needs the corresponding Android CLI release to be published.
Push the Android `vX.Y.Z-android` tag first, followed by the module release tag.
The full package builds directly from source and has no release-download dependency.

## Local builds

Requires Python 3.9+ and locally compiled Android archives, or access to an already
published Android release:

```sh
# Build the binaries first in the sibling tailscale-android-cli repository.
./.github/tools/build.sh --binary-dir ../tailscale-android-cli/dist
python3 .github/tools/test-build.py

# Alternatively, download the pinned published binaries:
./.github/tools/build.sh
```

Outputs: `dist/`, including both zips, `SHA256SUMS`, and `build-info.json`.
The build uses an explicit file allowlist; it does not package Git data, caches or
unrelated files, and does not remove binaries from your working directory.

For a new upstream version, update the version, release tag and exact source commit
in `binaries.env`. Use `./.github/tools/version-bump.sh minor` (or `major`, `patch`,
`build`) to update module.prop and all update manifests together. Review CHANGELOG.md,
commit on main, then push and tag. Only main is used for development.

## Credits and license

- [anasfanani and the original module contributors](https://github.com/anasfanani/magisk-tailscaled)
- [Tailscale Inc. and contributors](https://github.com/tailscale/tailscale)
- [Magisk](https://github.com/topjohnwu/Magisk) and [KernelSU](https://github.com/tiann/KernelSU)
- [Android jq builds](https://github.com/theshoqanebi/jq-build-for-android)

Original copyright and license notices are retained in [LICENSE](LICENSE).
This is an independent community module, not an official Tailscale Android app.
Report module issues [here](https://github.com/zym013579/magisk-tailscaled/issues).
