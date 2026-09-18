"""Reviewable compatibility patch/inventory for an existing Fooocus 2.5.5 install.

Does not download models or modify services. Run as the installation owner with
Fooocus stopped, after installing requirements-fooocus.txt in its environment.
"""
import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

MODEL = 'fooocus/juggernaut-xl-v8'


def patch_source(root):
    launch = root / 'launch.py'
    worker = root / 'modules/async_worker.py'
    before = worker.read_text()
    if 'hearth_worker_ready' in before:
        return
    replacements = [
        ('async_tasks = []\n', 'async_tasks = []\nhearth_worker_ready = threading.Event()\n'),
        ('        def callback(step, x0, x, total_steps, y):\n',
         '        def callback(step, x0, x, total_steps, y):\n'
         '            if getattr(async_task, "hearth_cancelled", lambda: False)():\n'
         '                raise ldm_patched.modules.model_management.InterruptProcessingException()\n'),
        ('    while True:\n        time.sleep(0.01)\n',
         '    hearth_worker_ready.set()\n    while True:\n        time.sleep(0.01)\n'),
        ('            try:\n                handler(task)\n',
         '            try:\n'
         '                if not getattr(task, "hearth_cancelled", lambda: False)():\n'
         '                    handler(task)\n'),
        ('            except:\n                traceback.print_exc()\n                task.yields.append',
         '            except:\n                task.hearth_failed = True\n                traceback.print_exc()\n                task.yields.append'),
        ('                if pid in modules.patch.patch_settings:\n                    del modules.patch.patch_settings[pid]\n',
         '                if pid in modules.patch.patch_settings:\n                    del modules.patch.patch_settings[pid]\n'
         '                task.processing = False\n'
         '                if hasattr(task, "hearth_released"):\n'
         '                    torch.cuda.synchronize()\n'
         '                    task.hearth_released.set()\n'),
    ]
    after = before
    for old, new in replacements:
        if after.count(old) != 1:
            raise RuntimeError('Fooocus source does not match the reviewed 2.5.5 worker.')
        after = after.replace(old, new)
    backup = root / 'hearth-backups' / datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True, mode=0o700)
    for path in (worker, launch):
        shutil.copy2(path, backup / path.name)
    worker.write_text(after)
    launch.write_text(launch.read_text().replace('ssl._create_default_https_context = ssl._create_unverified_context',
                                                '# hearth: retain certificate verification for downloads.'))


def patch_upscale(root):
    worker = root / 'modules/async_worker.py'
    before = worker.read_text()
    if 'hearth_postprocess' in before:
        return
    old = '                    handler(task)\n'
    if before.count(old) != 1:
        raise RuntimeError('The reviewed worker hook is missing.')
    backup = root / 'hearth-backups' / ('upscale-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(worker, backup / worker.name)
    worker.write_text(before.replace(old, old +
        '                    if hasattr(task, "hearth_postprocess") and not task.hearth_cancelled():\n'
        '                        task.hearth_postprocess()\n'))


def inventory(root, destination):
    files = []
    paths = [p for p in root.rglob('*.py') if 'fooocus_env' not in p.parts and 'hearth-backups' not in p.parts]
    paths += [p for p in (root / 'models').rglob('*') if p.is_file() and p.stat().st_size]
    paths += list((root / 'sdxl_styles').glob('*.json'))
    paths += [root / 'config.txt', root / 'presets/default.json', root / 'requirements_versions.txt']
    for path in sorted(set(paths)):
        if not path.resolve().is_relative_to(root):
            raise RuntimeError('Inventory must stay inside the Fooocus installation.')
        with path.open('rb') as source:
            files.append({'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size,
                          'sha256': hashlib.file_digest(source, 'sha256').hexdigest()})
    destination.write_text(json.dumps({'model': MODEL, 'fooocus_version': '2.5.5', 'files': files}, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fooocus', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    root = args.fooocus.resolve()
    version = (root / 'fooocus_version.py').read_text()
    if '2.5.5' not in version:
        raise RuntimeError('This adapter is qualified only for Fooocus 2.5.5.')
    patch_source(root)
    patch_upscale(root)
    inventory(root, args.manifest)
    print('Fooocus compatibility patch and local inventory prepared.')


if __name__ == '__main__':
    main()
