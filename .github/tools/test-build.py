#!/usr/bin/env python3
"""Check the installer contract, offline payloads, checksums and metadata."""
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('builder', Path(__file__).with_name('build.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackageTests(unittest.TestCase):
    def test_package_contract(self):
        prop = builder.read_properties(ROOT / 'module.prop')
        name = f"Magisk-Tailscaled-{prop['version']}"
        for full in (False, True):
            with self.subTest(full=full), zipfile.ZipFile(ROOT / 'dist' / (name + ('-full' if full else '') + '.zip')) as archive:
                names = set(archive.namelist())
                self.assertIn('META-INF/com/google/android/update-binary', names)
                self.assertIn('binaries.env', names)
                self.assertNotIn('.github/tools/build.py', names)
                self.assertFalse(any(n.startswith(('build/', 'dist/', '.git/')) for n in names))
                self.assertIn(b'--tun=userspace-networking --socks5-server=127.0.0.1:1099', archive.read('tailscale/settings.sh'))
                bins = {f'tailscale/bin/{binary}-{arch}' for binary in ('tailscaled', 'jq') for arch in ('arm', 'arm64')}
                self.assertEqual(names & bins, bins if full else set())
                if full:
                    hashes = dict((line.split()[1], line.split()[0]) for line in archive.read('tailscale/binaries.sha256').decode().splitlines())
                    for path in bins:
                        data = archive.read(path)
                        self.assertEqual(hashlib.sha256(data).hexdigest(), hashes[path.rsplit('/', 1)[1]])
                        builder.check_elf(data, path.rsplit('-', 1)[1])
                        self.assertEqual((archive.getinfo(path).external_attr >> 16) & 0o777, 0o755)

    def test_update_metadata(self):
        prop = builder.read_properties(ROOT / 'module.prop')
        for file in ROOT.glob('update*.json'):
            metadata = json.loads(file.read_text())
            self.assertEqual(metadata['version'], prop['version'])
            self.assertEqual(metadata['versionCode'], int(prop['versionCode']))
            self.assertIsInstance(metadata['versionCode'], int)
            self.assertIn('/zym013579/magisk-tailscaled/', metadata['zipUrl'])
            self.assertIn('/main/', metadata['changelog'])

    def test_rejects_invalid_download(self):
        with self.assertRaises(ValueError):
            builder.check_hash(b'corrupted', '0' * 64, 'fixture')
        with self.assertRaises(ValueError):
            builder.check_elf(b'not an executable', 'arm64')

    def test_offline_installer_extracts_each_architecture(self):
        prop = builder.read_properties(ROOT / 'module.prop')
        package = ROOT / 'dist' / f"Magisk-Tailscaled-{prop['version']}-full.zip"
        # Run the actual binary-installation section in a temporary filesystem.
        # Stop before service setup, which requires a real rooted Android device.
        installer = (ROOT / 'customize.sh').read_text().split('ui_print "- Extracting files..."')[0]
        for arch in ('arm', 'arm64'):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / 'installed'
                script = installer.replace('TS_DIR="/data/adb/tailscale"', 'TS_DIR=' + shlex.quote(str(target)))
                prelude = '''
ui_print() { :; }
abort() { echo "$*" >&2; exit 1; }
wget() { echo 'Offline installation unexpectedly tried to download' >&2; exit 1; }
sha256sum() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest()+"  "+sys.argv[1])' "$1"; }
'''
                result = subprocess.run(['sh'], input=prelude + script, text=True, capture_output=True,
                                        env={**os.environ, 'BOOTMODE': 'true', 'KSU': 'false', 'ARCH': arch,
                                             'ZIPFILE': str(package), 'TMPDIR': folder, 'MODPATH': folder})
                self.assertEqual(result.returncode, 0, result.stderr)
                for binary in ('tailscaled', 'jq'):
                    builder.check_elf((target / 'bin' / binary).read_bytes(), arch)


if __name__ == '__main__':
    unittest.main()
