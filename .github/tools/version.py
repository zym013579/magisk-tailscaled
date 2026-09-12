#!/usr/bin/env python3
"""Keep module.prop and Magisk update manifests in sync."""
import json
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[2]
prop = root / 'module.prop'
text = prop.read_text()
current = re.search(r'^version=v([0-9.]+)$', text, re.M).group(1)
parts = list(map(int, current.split('.')))
command = sys.argv[1] if len(sys.argv) > 1 else 'patch'
if command in ('major', 'minor', 'patch', 'build'):
    index = ('major', 'minor', 'patch', 'build').index(command)
    parts[index] += 1
    parts[index + 1:] = [0] * (3 - index)
elif command != 'sync':
    raise SystemExit('Usage: version.py major|minor|patch|build|sync')
if len(parts) != 4 or any(p < 0 or p > 99 for p in parts):
    raise SystemExit('Version fields must be in 0..99')
version = 'v' + '.'.join(map(str, parts))
code = int(''.join(f'{p:02d}' for p in parts))
text = re.sub(r'^version=.*$', 'version=' + version, text, flags=re.M)
text = re.sub(r'^versionCode=.*$', 'versionCode=' + str(code), text, flags=re.M)
prop.write_text(text)
metadata = {
    'version': version, 'versionCode': code,
    'zipUrl': f'https://github.com/zym013579/magisk-tailscaled/releases/download/{version}/Magisk-Tailscaled-{version}.zip',
    'changelog': 'https://raw.githubusercontent.com/zym013579/magisk-tailscaled/main/CHANGELOG.md',
}
for name in ['update.json', 'update-arm.json', 'update-arm64.json']:
    (root / name).write_text(json.dumps(metadata, indent=2) + '\n')
print(f'Module version: {version} ({code})')
