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

    def build_task(self, data, cancelled):
        # Fooocus interprets these as filesystem-backed wildcard/LoRA requests.
        # The remote API intentionally offers one fixed text-to-image profile.
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
        for name, value in changes.items():
            component = getattr(self.ui, name)
            for index, control in enumerate(self.ui.ctrls[1:]):
                if control is component:
                    values[index] = value
                    break
        task = self.ui.worker.AsyncTask(values)
        task.hearth_released = threading.Event()
        task.hearth_cancelled = cancelled
        task.hearth_failed = False
        return task

    def generate(self, data, cancelled, progress, output):
        self.task = None
        if cancelled():
            raise Cancelled()
        task = self.build_task(data, cancelled)
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
                if picture.size != SIZES[data.shape]:
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
        app = create_app(Path(config['jobs']), root, Path(config['token_file']).read_text().strip(),
                         engine=Fooocus(ui), manifest_digest=digest, model=MODEL, revision='fooocus-2.5.5-juggernaut-v8',
                         allowed_hosts=config['allowed_hosts'], allowed_controllers=config['allowed_controllers'])
        import uvicorn
        uvicorn.run(app, host=config['listen'], port=config['port'], access_log=False, proxy_headers=False)

    gradio.Blocks.launch = launch
    importlib.import_module('launch')


if __name__ == '__main__':
    main()
