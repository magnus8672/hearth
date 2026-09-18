import json
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import geometry_transport
from hearth.contracts import GeometryGeneration, GeometryReceipt, HunyuanOptions, TrellisOptions
from hearth.inference import ProviderError
from pydantic import ValidationError

from runtimes.geometry.hearth_geometry import generation_command
from runtimes.hunyuan.hunyuan_runner import shape_parameters


@pytest.mark.parametrize('model,values', [
    (TrellisOptions, {'sparse_guidance': float('nan')}), (TrellisOptions, {'max_tokens': 999999}),
    (TrellisOptions, {'unwrap': '--output /tmp/other'}), (TrellisOptions, {'texture': 'false'}),
    (TrellisOptions, {'atlas_size': 8192}), (TrellisOptions, {'steps': 12}),
    (HunyuanOptions, {'steps': 0}), (HunyuanOptions, {'steps': 1.5}),
    (HunyuanOptions, {'paint_guidance': float('inf')}), (HunyuanOptions, {'chunks': 999999}),
    (HunyuanOptions, {'texture_size': 8192}), (HunyuanOptions, {'models': '/unapproved'}),
])
def test_tuning_rejects_unbounded_or_unrecognized_values(model, values):
    with pytest.raises(ValidationError):
        model(**values)


def request(**options):
    return GeometryGeneration(id=uuid4(), model='fixture', image_sha256='a' * 64, **options)


def test_trellis_options_become_explicit_safe_cli_arguments():
    data = request(trellis=TrellisOptions(sparse_guidance=6, shape_guidance=8, max_tokens=8192,
                   background='threshold', texture=False, unwrap='box', remesh_band=2,
                   decimation=128, atlas_size=512, texture_resolution=512))
    command = generation_command(Path('/approved'), 'trellis', data, 'input', 'output')
    for flag, value in {'--gss': '6.0', '--gsh': '8.0', '--max-tokens': '8192', '--bg-removal': 'threshold',
                        '--band': '2', '--decim': '128', '--atlas': '512', '--tex-res': '512', '--webp': 'off'}.items():
        assert command[command.index(flag) + 1] == value
    assert '--box-uv' in command and '--no-texture' in command and '--require-gpu' in command
    with pytest.raises(ValueError):
        generation_command(Path('/approved'), 'hunyuan3d-2.0', data, 'input', 'output')


def test_hunyuan_options_reach_runner_and_shape_pipeline():
    options = HunyuanOptions(steps=12, guidance=4, octree_resolution=256, chunks=4000,
                             surface_level=.01, bounds=1.1, texture=False, max_faces=10000,
                             paint_steps=15, paint_seed=42, texture_size=1024, render_size=1024)
    command = generation_command(Path('/approved'), 'hunyuan3d-2.0', request(hunyuan=options), 'input', 'output')
    assert json.loads(command[command.index('--options') + 1]) == options.model_dump()
    assert shape_parameters(options) == {'num_inference_steps': 12, 'guidance_scale': 4,
        'octree_resolution': 256, 'num_chunks': 4000, 'mc_level': .01, 'box_v': 1.1}
    with pytest.raises(ValueError):
        request(hunyuan=options).check_tuning('trellis-v1')
    with pytest.raises(ValueError):
        request(hunyuan=options).check_tuning(None)


@pytest.mark.parametrize('changed', [False, True])
def test_receipt_checks_nested_settings(monkeypatch, changed):
    data = request(hunyuan=HunyuanOptions(steps=20))
    receipt = GeometryReceipt(**data.model_dump(), state='cancelled', progress=0,
                              manifest_sha256='b' * 64, execution_released=True, cancel_requested=True)
    if changed:
        receipt.hunyuan.steps = 50
    monkeypatch.setattr(geometry_transport, 'rpc', lambda *args, **kwargs: receipt)
    if changed:
        with pytest.raises(ProviderError, match='another request'):
            geometry_transport.render('', '', None, data, b'image')
    else:
        assert geometry_transport.render('', '', None, data, b'image')[0].hunyuan.steps == 20


def test_legacy_requests_omit_new_fields_on_wire(monkeypatch):
    data = request()
    def rpc(*args, **kwargs):
        assert 'trellis' not in kwargs['payload']['request'] and 'hunyuan' not in kwargs['payload']['request']
        return GeometryReceipt(**data.model_dump(), state='cancelled', progress=0,
            manifest_sha256='b' * 64, execution_released=True, cancel_requested=True)
    monkeypatch.setattr(geometry_transport, 'rpc', rpc)
    geometry_transport.render('', '', None, data, b'image')
    data.check_tuning(None)
    assert TrellisOptions().sparse_guidance == 7.5
    assert HunyuanOptions().steps == 50 and HunyuanOptions().paint_steps == 30
