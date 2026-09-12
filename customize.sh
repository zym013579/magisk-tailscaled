#!/system/bin/sh

# DEBUG=1
[ -n "${DEBUG:-}" ] && {
	PS4="+ \${0##*/}:\${LINENO}: "
	set -e
	set -u
	set -x
	set
} || true

# Download a pinned release file. Full packages work without network access.
download_file() {
    ui_print "- Downloading $(basename "$1")..."
    wget --timeout=100 -qO "$2" "$1" || abort "Unable to download $1; use the full package for offline installation."
}

verify_file() {
    EXPECTED_HASH=$1
    ACTUAL_HASH=$(sha256sum "$2" | cut -d ' ' -f 1)
    [ -n "$EXPECTED_HASH" ] && [ "$ACTUAL_HASH" = "$EXPECTED_HASH" ] || abort "SHA256 verification failed: $2"
}

# shellcheck disable=SC2034
SKIPUNZIP=1
# shellcheck disable=SC2034
SKIPMOUNT=false

if [ "$BOOTMODE" != true ]; then
	ui_print "! Please install in Magisk Manager or KernelSU Manager"
	ui_print "! Install from recovery is NOT supported"
	abort "-----------------------------------------------------------"
elif [ "$KSU" = true ] && [ "$KSU_VER_CODE" -lt 10670 ]; then
	abort "error: Please update your KernelSU and KernelSU Manager"
fi

SERVICE_DIR="/data/adb/service.d"

TS_DIR="/data/adb/tailscale"
TS_BIN_DIR="$TS_DIR/bin"
TS_SCRIPTS_DIR="$TS_DIR/scripts"

# This configuration is shipped inside the module zip.
unzip -p "$ZIPFILE" binaries.env > "$TMPDIR/tailscale-binaries.env" || abort "Missing binary source configuration."
# shellcheck disable=SC1091
. "$TMPDIR/tailscale-binaries.env"

case $ARCH in
arm) JQ_ASSET="$JQ_ASSET_ARM"; JQ_HASH="$JQ_SHA256_ARM" ;;
arm64) JQ_ASSET="$JQ_ASSET_ARM64"; JQ_HASH="$JQ_SHA256_ARM64" ;;
*)
	ui_print "Unsupported architecture: $ARCH"
	abort
	;;
esac
ui_print "- Detected architecture: $ARCH"

if [ -d "$TS_DIR" ]; then
	[ -f "$TS_DIR/tmp/tailscaled.state" ] && mv -f "$TS_DIR/tmp/tailscaled.state" "$TS_DIR/tailscaled.state"
	ui_print "- Backup old files"
	PROP_FILE="$(echo "$MODPATH" | sed 's/_update//')/module.prop"
	[ ! -f "$PROP_FILE" ] && PROP_FILE="$MODPATH/module.prop"
	versionCode=$(grep '^versionCode=' "$PROP_FILE" | cut -d= -f2)
	# shellcheck disable=SC2154
	rm -rf "$TS_DIR/backups/$versionCode/" && mkdir -p "$TS_DIR/backups/$versionCode/"
	for p in "$TS_DIR"/*; do
		case "$(basename "$p")" in
		ssh | certs | backups | tailscaled.state) ;;
		*)
			mv -f -- "$p" "$TS_DIR/backups/$versionCode/"
			;;
		esac
	done
fi

mkdir -p "$TS_BIN_DIR"
unzip -qqjo "$ZIPFILE" "tailscale/bin/*-$ARCH" -d "$TS_BIN_DIR" 2>/dev/null || true
unzip -p "$ZIPFILE" tailscale/binaries.sha256 > "$TMPDIR/bundled.sha256" 2>/dev/null || true
for f in "$TS_BIN_DIR"/*-"$ARCH"; do
    if [ -f "$f" ]; then
        EXPECTED=$(awk -v name="$(basename "$f")" '$2 == name {print $1}' "$TMPDIR/bundled.sha256")
        verify_file "$EXPECTED" "$f"
        mv "$f" "${f%-"$ARCH"}"
    fi
done

if [ ! -f "$TS_BIN_DIR/tailscaled" ]; then
    BASE_URL="https://github.com/$TAILSCALE_REPO/releases/download/$TAILSCALE_TAG"
    FILENAME="tailscale_${TAILSCALE_VERSION}_${ARCH}.tgz"
    download_file "$BASE_URL/SHA256SUMS" "$TMPDIR/tailscale.sha256"
    download_file "$BASE_URL/$FILENAME" "$TMPDIR/$FILENAME"
    EXPECTED=$(awk -v name="$FILENAME" '$2 == name {print $1}' "$TMPDIR/tailscale.sha256")
    verify_file "$EXPECTED" "$TMPDIR/$FILENAME"
    tar -xzf "$TMPDIR/$FILENAME" -C "$TS_BIN_DIR" tailscaled || abort "Unable to extract tailscaled."
fi

if [ ! -f "$TS_BIN_DIR/jq" ]; then
    download_file "https://github.com/$JQ_REPO/releases/download/$JQ_TAG/$JQ_ASSET" "$TMPDIR/jq"
    verify_file "$JQ_HASH" "$TMPDIR/jq"
    mv -f "$TMPDIR/jq" "$TS_BIN_DIR/jq" || abort "Unable to install jq."
fi

ui_print "- Extracting files..."
unzip -qqo "$ZIPFILE" -x 'META-INF/*' 'tailscale/*' -d "$MODPATH"

mkdir -p "$TS_DIR" "$TS_SCRIPTS_DIR" "$SERVICE_DIR" "$MODPATH/system/bin/"
unzip -qqjo "$ZIPFILE" 'tailscale/scripts/*' -d "$TS_SCRIPTS_DIR"
unzip -qqjo "$ZIPFILE" 'tailscale/settings.sh' -d "$TS_DIR"
ln -sf "$TS_BIN_DIR/tailscaled" "$TS_BIN_DIR/tailscale"
ln -sf "$TS_BIN_DIR/"* "$MODPATH/system/bin/"

ln -sf "$TS_SCRIPTS_DIR/tailscaled.service" "$MODPATH/system/bin/"

ui_print "- Setting permissions"
set_perm_recursive "$TS_BIN_DIR/" 0 0 0755 0755 "u:object_r:system_file:s0"
set_perm_recursive "$TS_SCRIPTS_DIR/" 0 0 0755 0755 "u:object_r:system_file:s0"
set_perm_recursive "$MODPATH/system/bin/" 0 0 0755 0755 "u:object_r:system_file:s0"
set_perm "$MODPATH/service.sh" 0 0 0755 "u:object_r:system_file:s0"

if [ ! -f "$SERVICE_DIR/tailscaled_service.sh" ]; then
	# offer to move module scripts to general scripts
	ui_print "-----------------------------------------------------------"
	ui_print "- Do you want to move Module Scripts to General Scripts ?"
	ui_print "- This option allows you to toggle the 'tailscaled' service"
	ui_print "  on or off by enabling or disabling modules."
	ui_print "- Your service directory is :"
	ui_print "  '$SERVICE_DIR'."
	ui_print "- Because the Developer Guides mentioned :"
	ui_print "  Modules should NOT add general scripts during installation."
	ui_print "- I offer this option to you."
	ui_print "- You have 10 seconds to make a selection. Default is [Yes]."
	ui_print "- [ Vol UP(+): Yes ]"
	ui_print "- [ Vol DOWN(-): No ]"
	timeout 10 sh -c '
  while true; do
    if getevent -lc 1 2>&1 | grep -q KEY_VOLUMEUP; then
      echo "up"
      break
    elif getevent -lc 1 2>&1 | grep -q KEY_VOLUMEDOWN; then
      echo "down"
      break
    fi
  done
' >"$TMPDIR/choice" || true

	choice=$(cat "$TMPDIR/choice" 2>/dev/null)
	if [ "$choice" = "up" ] || [ -z "$choice" ]; then
		ui_print "- [Yes] Move Module Scripts to General Scripts."
		mv -f "$MODPATH/service.sh" "$SERVICE_DIR/tailscaled_service.sh"
	else
		ui_print "- [No] Skip and keep using Module Scripts."
	fi
else
	ui_print "- Move General Scripts."
	mv -f "$MODPATH/service.sh" "$SERVICE_DIR/tailscaled_service.sh"
fi
ui_print "- Starting service in background."
${TS_SCRIPTS_DIR}/start.sh postinstall 2>&1 &
if [ ! -f "/system/bin/tailscale" ] || ! cmp --silent "/system/bin/tailscale" "$MODPATH/system/bin/tailscale"; then
	ui_print "- Link file to /dev/."
	ln -sf "$TS_SCRIPTS_DIR/tailscaled.service" /dev/tailscaled.service
	ln -sf "$TS_BIN_DIR/tailscaled" /dev/tailscaled
	ln -sf "$TS_BIN_DIR/tailscaled" /dev/tailscale
	ui_print "-----------------------------------------------------------"
	ui_print " Instructions       "
	ui_print "-----------------------------------------------------------"
	ui_print "- If you not reboot, execute with /dev/tailscale or /dev/tailscaled.service."
	ui_print "- After reboot, you can use tailscale and tailscaled.service directly."
	if [ ! -f "$TS_DIR/tailscaled.state" ]; then
		ui_print "- Quickstart to new user :"
		ui_print "  su -c '/dev/tailscale login'"
		ui_print "  su -c '/dev/tailscaled.service status'"
		ui_print "- Read the README.md"
	else
		ui_print "- Tailscaled service manager :"
		ui_print "  su -c '/dev/tailscaled.service'"
	fi
else
	if [ ! -f "$TS_DIR/tailscaled.state" ]; then
		ui_print "- Quickstart to login :"
		ui_print "  su -c 'tailscale login'"
		ui_print "  su -c 'tailscaled.service status'"
		ui_print "- Read the README.md"
	else
		ui_print "- Tailscaled service manager :"
		ui_print "  su -c 'tailscaled.service'"
	fi
fi
[ -n "${DEBUG:-}" ] && { set +ue; } || true
