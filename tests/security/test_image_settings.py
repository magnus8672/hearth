from uuid import uuid4

import pytest
from hearth.contracts import ImageGeneration, ImageOptions, ImageProviderInfo, ImageReceipt
from hearth.image_settings import dimensions, validate_settings
from pydantic import ValidationError

from runtimes.image.fooocus_bridge import Fooocus


def request(**changes):
    return ImageGeneration(id=uuid4(), model='fixture', prompt='An orange square', seed=1, **changes)


@pytest.mark.parametrize(('shape', 'resolution', 'expected'), [
    ('square', 'native', (1024, 1024)), ('landscape', '2k', (2048, 1536)),
    ('portrait', '4k', (3072, 4096)), ('square', '4k', (4096, 4096)),
    ('widescreen', '4k', (3840, 2160)), ('tall', '4k', (2160, 3840)),
])
def test_output_sizes_are_bounded_and_explicit(shape, resolution, expected):
    data = request(shape=shape, options={'resolution': resolution})
    assert dimensions(data.shape, data.options.resolution) == expected
    assert ImageReceipt(id=data.id, model=data.model, state='completed', progress=60, steps=60,
                        seed=1, shape=shape, width=expected[0], height=expected[1],
                        execution_released=True, manifest_sha256='a' * 64, cancel_requested=False)


@pytest.mark.parametrize('options', [{'resolution': '8k'}, {'sharpness': -1}, {'guidance_scale': 31},
                                   {'guidance_scale': float('nan')}, {'styles': ['x'] * 9}, {'checkpoint': '/private/model'}])
def test_advanced_options_are_closed_and_bounded(options):
    with pytest.raises(ValidationError):
        ImageOptions.model_validate(options)


def test_legacy_and_unsupported_provider_options_are_not_silently_ignored():
    profile = {'shapes': ['square'], 'steps': [20]}
    validate_settings(request(), profile)
    for changes in ({'shape': 'widescreen'}, {'steps': 60}, {'options': {'resolution': '4k'}},
                    {'options': {'styles': []}}, {'options': {'sharpness': 2}}):
        with pytest.raises(ValueError):
            validate_settings(request(**changes), profile)
    info = ImageProviderInfo(protocol='hearth.image.v1', model='fixture', model_revision='1', manifest_sha256='a'*64,
                             shapes=['widescreen'], steps=[60], job_cancellation=True, offline=True,
                             options={'resolutions': ['native', '4k'], 'styles': ['Fooocus V2'], 'guidance_scale': 4, 'sharpness': 2})
    validate_settings(request(shape='widescreen', steps=60, options={'resolution': '4k', 'styles': ['Fooocus V2'], 'guidance_scale': 7}), info.model_dump())
    with pytest.raises(ValueError):
        validate_settings(request(shape='widescreen', steps=60, options={'styles': ['../../private']}), info.model_dump())


def test_fooocus_controls_forward_options_without_changing_checkpoint_or_shared_defaults():
    from types import SimpleNamespace
    names = ['generate_image_grid', 'prompt', 'negative_prompt', 'performance_selection', 'aspect_ratios_selection',
             'image_number', 'output_format', 'image_seed', 'base_model', 'refiner_model', 'overwrite_step',
             'overwrite_width', 'overwrite_height', 'input_image_checkbox', 'enhance_checkbox', 'disable_preview',
             'disable_intermediate_results', 'save_metadata_to_images', 'style_selections', 'guidance_scale', 'sharpness']
    ui = SimpleNamespace(**{name: SimpleNamespace(value='original') for name in names})
    ui.ctrls = [None] + [getattr(ui, name) for name in names]
    ui.worker = SimpleNamespace(AsyncTask=lambda values: SimpleNamespace(values=dict(zip(names, values, strict=True))))
    data = request(shape='widescreen', steps=60, options={'resolution': '4k', 'styles': [], 'guidance_scale': 6.5, 'sharpness': 3})
    task = Fooocus(ui).build_task(data, lambda: False)
    assert task.values['overwrite_width'] == 1024 and task.values['overwrite_height'] == 576
    assert task.values['overwrite_step'] == 60
    assert task.values['style_selections'] == []
    assert task.values['guidance_scale'] == 6.5 and task.values['sharpness'] == 3
    assert task.values['base_model'] == 'juggernautXL_v8Rundiffusion.safetensors'
    assert task.values['input_image_checkbox'] is False and task.values['enhance_checkbox'] is False
    assert all(getattr(ui, name).value == 'original' for name in names)


def test_fooocus_only_advertises_upscale_when_model_is_installed(tmp_path):
    from types import SimpleNamespace
    ui = SimpleNamespace(
        style_selections=SimpleNamespace(choices=['Fooocus V2', ('Photograph', 'SAI Photographic')], value=['Fooocus V2']),
        guidance_scale=SimpleNamespace(value=4), sharpness=SimpleNamespace(value=2),
        modules=SimpleNamespace(config=SimpleNamespace(path_upscale_models=tmp_path)),
    )
    assert Fooocus(ui).profile()['options']['resolutions'] == ['native']
    (tmp_path / 'fooocus_upscaler_s409985e5.bin').write_bytes(b'installed')
    profile = Fooocus(ui).profile()
    assert profile['options']['resolutions'] == ['native', '2k', '4k']
    assert profile['options']['styles'] == ['Fooocus V2', 'SAI Photographic']
