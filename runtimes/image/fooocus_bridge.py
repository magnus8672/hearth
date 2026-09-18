"""Adapter for the pinned Fooocus 2.5.5 worker; shares its queue and GPU model.

Run inside the existing Fooocus environment. The graphical UI stays on loopback.
The authenticated job API is restricted to the configured controller addresses.
This is an adapter for an external installation, not an enrolled hearth worker.
"""
import argparse
import copy
import hashlib
import importlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

from hearth.image_settings import dimensions

if __package__:
    from .hearth_image import SIZES, Cancelled, GenerationError, create_app
else:
    from hearth_image import SIZES, Cancelled, GenerationError, create_app

MODEL = 'fooocus/juggernaut-xl-v8'
CHECKPOINT = 'juggernautXL_v8Rundiffusion.safetensors'


def verify_inventory(root, path):
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest['model'] != MODEL or manifest['fooocus_version'] != '2.5.5':
        raise RuntimeError('Unsupported Fooocus profile.')
    for item in manifest['files']:
        target = (root / item['path']).resolve()
        if not target.is_relative_to(root) or target.stat().st_size != item['bytes']:
            raise RuntimeError('Fooocus inventory changed; review the installation before restarting.')
        with target.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != item['sha256']:
                raise RuntimeError('Fooocus inventory digest changed; review the installation before restarting.')
    return hashlib.sha256(raw).hexdigest()


class Fooocus:
    def __init__(self, ui):
        self.ui, self.task = ui, None

    def profile(self):
        styles = [item[1] if isinstance(item, (list, tuple)) else item for item in self.ui.style_selections.choices]
        upscaler = Path(self.ui.modules.config.path_upscale_models) / 'fooocus_upscaler_s409985e5.bin'
        return {'shapes': list(SIZES), 'steps': [20, 30, 40, 60], 'options': {
            'resolutions': ['native', '2k', '4k'] if upscaler.is_file() else ['native'], 'styles': styles,
            'default_styles': list(self.ui.style_selections.value),
            'guidance_scale': self.ui.guidance_scale.value, 'sharpness': self.ui.sharpness.value}}

    def build_task(self, data, cancelled):
        # Fooocus interprets these as filesystem-backed wildcard/LoRA requests.
        # Remote controls never select filesystem paths, checkpoints or LoRAs.
        if any('__' in text or re.search(r'<\s*lora\s*:', text, re.I) for text in (data.prompt, data.negative_prompt)):
            raise GenerationError('Wildcard and LoRA directives are not supported by this image profile.')
        width, height = SIZES[data.shape]
        values = [copy.deepcopy(component.value) for component in self.ui.ctrls[1:]]
        changes = {
            'generate_image_grid': False, 'prompt': data.prompt, 'negative_prompt': data.negative_prompt,
            'performance_selection': 'Speed', 'aspect_ratios_selection': f'{width}×{height}',
            'image_number': 1, 'output_format': 'png', 'image_seed': data.seed,
            'base_model': CHECKPOINT, 'refiner_model': 'None', 'overwrite_step': data.steps,
            'overwrite_width': width, 'overwrite_height': height, 'input_image_checkbox': False,
            'enhance_checkbox': False, 'disable_preview': True, 'disable_intermediate_results': True,
            'save_metadata_to_images': False,
        }
        if data.options.styles is not None:
            changes['style_selections'] = data.options.styles
        for name in ('guidance_scale', 'sharpness'):
            if getattr(data.options, name) is not None:
                changes[name] = getattr(data.options, name)
        for name, value in changes.items():
            component = getattr(self.ui, name)
            for index, control in enumerate(self.ui.ctrls[1:]):
                if control is component:
                    values[index] = value
                    break
            else:
                raise GenerationError('The installed Fooocus controls changed. Review the adapter.')
        task = self.ui.worker.AsyncTask(values)
        task.hearth_released = threading.Event()
        task.hearth_cancelled = cancelled
        task.hearth_failed = False
        return task

    def upscale(self, task, data, cancelled, progress):
        # Called by the same Fooocus worker, before its CUDA completion receipt.
        # Never overlaps another graphical/API task or releases capacity early.
        if len(task.results) != 1 or cancelled():
            return
        import numpy as np
        import torch
        from modules.upscaler import perform_upscale
        from PIL import Image
        if not (Path(self.ui.modules.config.path_upscale_models) / 'fooocus_upscaler_s409985e5.bin').is_file():
            raise GenerationError('Prepare the Fooocus upscaler before requesting larger images.')
        path = Path(task.results[0]).resolve()
        if not path.is_relative_to(Path(self.ui.modules.config.temp_path).resolve()):
            raise GenerationError('Fooocus returned an unexpected output location.')
        progress(data.steps)
        with Image.open(path) as image:
            pixels = np.array(image.convert('RGB'))
        with torch.inference_mode():
            pixels = perform_upscale(pixels)
        if cancelled():
            return
        image = Image.fromarray(pixels)
        size = dimensions(data.shape, data.options.resolution)
        if image.size[0] < size[0] or image.size[1] < size[1]:
            raise GenerationError('The upscaler did not reach the requested resolution.')
        if image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        image.save(path, format='PNG')

    def generate(self, data, cancelled, progress, output):
        self.task = None
        if cancelled():
            raise Cancelled()
        task = self.build_task(data, cancelled)
        if data.options.resolution != 'native':
            task.hearth_postprocess = lambda: self.upscale(task, data, cancelled, progress)
        self.task = task
        self.ui.worker.async_tasks.append(task)
        deadline = time.monotonic() + 1200
        while not task.hearth_released.wait(.1):
            if time.monotonic() > deadline:
                # release() refuses to free the slot while the worker is uncertain.
                raise GenerationError('The Fooocus worker did not finish in time; restart the service.')
            while task.yields:
                kind, value = task.yields.pop(0)
                if kind == 'preview':
                    match = re.search(r'Sampling step (\d+)/', value[1])
                    if match:
                        progress(min(data.steps, int(match.group(1))))
        if cancelled():
            raise Cancelled()
        if task.hearth_failed or len(task.results) != 1:
            raise GenerationError('Fooocus could not complete this image. Check the provider service log.')
        from PIL import Image
        path = Path(task.results[0]).resolve()
        permitted = Path(self.ui.modules.config.temp_path).resolve()
        if not path.is_relative_to(permitted):
            raise GenerationError('Fooocus returned an unexpected output location.')
        try:
            with Image.open(path) as picture:
                picture.load()
                if picture.size != dimensions(data.shape, data.options.resolution):
                    raise GenerationError('Fooocus returned unexpected image dimensions.')
                picture.save(output, format='PNG')
            progress(data.steps)
        finally:
            path.unlink(missing_ok=True)

    def release(self):
        if self.task is not None and not self.task.hearth_released.is_set():
            raise RuntimeError('Worker completion is uncertain.')
        if self.task is not None:
            permitted = Path(self.ui.modules.config.temp_path).resolve()
            for result in self.task.results:
                if isinstance(result, str):
                    path = Path(result).resolve()
                    if path.is_relative_to(permitted):
                        path.unlink(missing_ok=True)
        # The worker acknowledges after CUDA synchronization. Keep the resident
        # weights loaded; execution release is not model eviction.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    config = json.loads(parser.parse_args().config.read_text())
    root = Path(config['fooocus']).resolve()
    digest = verify_inventory(root, Path(config['manifest']))
    os.chdir(root)
    sys.path.insert(0, str(root))
    cache = Path(config['jobs']).parent / 'cache'
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    for key, value in {'GRADIO_ANALYTICS_ENABLED': 'False', 'HF_HUB_OFFLINE': '1',
                       'HF_HOME': str(cache / 'huggingface'), 'XDG_CACHE_HOME': str(cache),
                       'MPLCONFIGDIR': str(cache / 'matplotlib'),
                       'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'}.items():
        os.environ[key] = value
    # Import launch exactly once: importing webui later imports launch itself.
    sys.argv = ['launch.py', '--listen', '127.0.0.1', '--port', '7865', '--disable-in-browser',
                '--disable-analytics', '--disable-preset-download', '--disable-offload-from-vram',
                '--disable-image-log', '--disable-preset-selection']
    import gradio
    original_launch = gradio.Blocks.launch

    def launch(blocks, **kwargs):
        kwargs['prevent_thread_lock'] = True
        original_launch(blocks, **kwargs)
        ui = sys.modules['webui']
        if not ui.worker.hearth_worker_ready.wait(180):
            raise RuntimeError('Fooocus worker failed to initialize.')
        engine = Fooocus(ui)
        app = create_app(Path(config['jobs']), root, Path(config['token_file']).read_text().strip(),
                         engine=engine, manifest_digest=digest, model=MODEL, revision='fooocus-2.5.5-juggernaut-v8-upscale',
                         allowed_hosts=config['allowed_hosts'], allowed_controllers=config['allowed_controllers'], profile=engine.profile())
        import uvicorn
        uvicorn.run(app, host=config['listen'], port=config['port'], access_log=False, proxy_headers=False)

    gradio.Blocks.launch = launch
    importlib.import_module('launch')


if __name__ == '__main__':
    main()
