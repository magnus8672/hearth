import json
import struct

import pytest
from hearth.geometry_validation import validate_glb


def triangle(update=None):
    doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 36}],
           'bufferViews': [{'buffer': 0, 'byteLength': 36}],
           'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3'}],
           'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
           'nodes': [{'mesh': 0}], 'scenes': [{'nodes': [0]}], 'scene': 0}
    if update:
        update(doc)
    data = json.dumps(doc).encode()
    data += b' ' * (-len(data) % 4)
    binary = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)
    return struct.pack('<4sIII4s', b'glTF', 2, 28 + len(data) + len(binary), len(data), b'JSON') + data + struct.pack('<I4s', len(binary), b'BIN\0') + binary


def test_glb_bounds_external_resources_and_scene_cycles():
    assert validate_glb(triangle())['triangles'] == 1
    for change in (lambda d: d['buffers'][0].update(uri='https://example.test/private'),
                   lambda d: d['bufferViews'][0].update(byteLength=100000),
                   lambda d: d['accessors'][0].update(count=1000000),
                   lambda d: d['nodes'][0].update(children=[0]),
                   lambda d: d.update(extensionsUsed=['EXT_unknown'])):
        with pytest.raises(ValueError):
            validate_glb(triangle(change))
    with pytest.raises(ValueError):
        validate_glb(triangle()[:-1])


@pytest.mark.parametrize('backend', ['trellis', 'hunyuan3d-2.0'])
def test_geometry_runtime_cancel_reaps_child(tmp_path, monkeypatch, backend):
    import base64
    import hashlib
    import subprocess
    import sys
    import time
    from uuid import uuid4

    from hearth.contracts import GeometryGeneration
    from hearth.geometry_probe import reference

    from runtimes.geometry.hearth_geometry import Jobs, Submission
    popen = subprocess.Popen
    processes = []
    def child(args, **kwargs):
        assert ('--resolution' in args) == (backend == 'hunyuan3d-2.0')
        if backend == 'hunyuan3d-2.0':
            assert args[1].endswith('/app/hunyuan_runner.py')
            work = jobs.root / f'{data.id}.work'
            work.mkdir()
            (work / 'reference.png').write_bytes(b'private intermediate')
        script = 'import subprocess,sys,time; child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(120)"]); '
        script += f'open({str(jobs.root / "child.pid")!r},"w").write(str(child.pid)); time.sleep(120)'
        process = popen([sys.executable, '-c', script], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr('runtimes.geometry.hearth_geometry.subprocess.Popen', child)
    engine = tmp_path / 'installation'
    (engine / 'engine').mkdir(parents=True)
    (engine / 'inventory.json').write_text(json.dumps({'files': [], 'model': 'fixture', 'model_revision': 'fixture', 'backend': backend, 'resolutions': [512]}))
    (engine / 'engine-inventory.json').write_text('[]')
    executable = engine / 'engine/trellis-cli'
    executable.write_text('#!/bin/sh\nsleep 120\n')
    executable.chmod(0o755)
    jobs = Jobs(tmp_path / 'jobs', engine)
    image = reference()
    data = GeometryGeneration(id=uuid4(), model='fixture', image_sha256=hashlib.sha256(image).hexdigest())
    try:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as error:
            jobs.submit(Submission(request=data.model_copy(update={'resolution': 1024}), image=base64.b64encode(image).decode()))
        assert error.value.status_code == 422
        assert not processes
        jobs.submit(Submission(request=data, image=base64.b64encode(image).decode()))
        until = time.monotonic() + 5
        while not (jobs.root / 'child.pid').exists() and time.monotonic() < until:
            time.sleep(.01)
        assert (jobs.root / 'child.pid').exists()
        assert processes and processes[0].poll() is None
        with jobs.db() as db:
            db.execute('UPDATE jobs SET cancel=1 WHERE id=?', (str(data.id),))
        until = time.monotonic() + 5
        while not jobs.get(data.id)['execution_released'] and time.monotonic() < until:
            time.sleep(.02)
        assert jobs.get(data.id)['state'] == 'cancelled'
        assert jobs.get(data.id)['execution_released']
        assert processes[0].poll() is not None
        import os
        with pytest.raises(ProcessLookupError):
            os.killpg(processes[0].pid, 0)
        assert not (jobs.root / f'{data.id}.jpg').exists()
        assert not (jobs.root / f'{data.id}.work').exists()
    finally:
        jobs.executor.shutdown(wait=True)
        jobs.lock.close()
