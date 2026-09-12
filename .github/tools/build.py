#!/usr/bin/env python3
"""Build lightweight and offline Magisk packages without changing source files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def read_properties(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'magisk-tailscaled-builder'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_hash(data, expected, label):
    if sha256(data) != expected:
        raise ValueError(f'SHA256 mismatch: {label}')


def check_elf(data, arch):
    if data[:4] != b'\x7fELF' or data[5] != 1:
        raise ValueError(f'{arch}: not a little-endian ELF binary')
    if struct.unpack_from('<H', data, 18)[0] != {'arm': 40, 'arm64': 183}[arch]:
        raise ValueError(f'{arch}: wrong ELF architecture')


def release_binary(config, arch, binary_dir):
    name = f"tailscale_{config['TAILSCALE_VERSION']}_{arch}.tgz"
    if binary_dir:
        data = (binary_dir / name).read_bytes()
    else:
        base = f"https://github.com/{config['TAILSCALE_REPO']}/releases/download/{config['TAILSCALE_TAG']}"
        checks = dict((line.split()[1].lstrip('*'), line.split()[0])
                      for line in fetch(base + '/SHA256SUMS').decode().splitlines() if line.strip())
        data = fetch(base + '/' + name)
        check_hash(data, checks[name], name)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        entry = archive.getmember('tailscaled')
        if not entry.isfile():
            raise ValueError(f'{name}: tailscaled must be a regular file')
        binary = archive.extractfile(entry).read()
    check_elf(binary, arch)
    return binary


def jq_binary(config, arch):
    cache = ROOT / 'build' / 'downloads' / f'jq-{arch}'
    if cache.exists():
        data = cache.read_bytes()
    else:
        asset = config[f'JQ_ASSET_{arch.upper()}']
        data = fetch(f"https://github.com/{config['JQ_REPO']}/releases/download/{config['JQ_TAG']}/{asset}")
    check_hash(data, config[f'JQ_SHA256_{arch.upper()}'], f'jq-{arch}')
    check_elf(data, arch)
    return data


def source_files():
    names = ['module.prop', 'customize.sh', 'service.sh', 'uninstall.sh', 'binaries.env', 'LICENSE']
    files = {name: (ROOT / name).read_bytes() for name in names}
    for folder in ['META-INF', 'tailscale/scripts']:
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    files['tailscale/settings.sh'] = (ROOT / 'tailscale/settings.sh').read_bytes()
    return files


def write_zip(path, files):
    # Explicit allowlist and stable metadata avoid adding .git, caches or stale binaries.
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            executable = name.endswith('.sh') or '/scripts/' in name or '/bin/' in name or name.endswith('update-binary')
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            out.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(path) as check:
        if check.testzip():
            raise ValueError(f'Archive CRC failed: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary-dir', type=Path, help='Use locally built tailscale_*.tgz files')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    prop, config = read_properties(ROOT / 'module.prop'), read_properties(ROOT / 'binaries.env')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', prop['version']):
        raise ValueError('Invalid module version')
    if config['TAILSCALE_TAG'] != 'v' + config['TAILSCALE_VERSION'] + '-android':
        raise ValueError('Tailscale tag/version mismatch')
    files = source_files()
    full = dict(files)
    for arch in ('arm', 'arm64'):
        full[f'tailscale/bin/tailscaled-{arch}'] = release_binary(config, arch, args.binary_dir)
        full[f'tailscale/bin/jq-{arch}'] = jq_binary(config, arch)
    manifest = {name: sha256(data) for name, data in full.items() if '/bin/' in name}
    full['tailscale/binaries.sha256'] = ''.join(f'{digest}  {name.rsplit("/", 1)[1]}\n' for name, digest in sorted(manifest.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    basename = 'Magisk-Tailscaled-' + prop['version']
    for suffix, contents in [('', files), ('-full', full)]:
        output = args.output / f'{basename}{suffix}.zip'
        write_zip(output, contents)
        print(f'Built {output} ({output.stat().st_size:,} bytes)')
    packages = sorted(args.output.glob(f'{basename}*.zip'))
    (args.output / 'SHA256SUMS').write_text(''.join(f'{sha256(p.read_bytes())}  {p.name}\n' for p in packages))
    (args.output / 'build-info.json').write_text(json.dumps({
        'module_version': prop['version'], 'tailscale_version': config['TAILSCALE_VERSION'],
        'tailscale_ref': config['TAILSCALE_REF'], 'binaries': manifest,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
