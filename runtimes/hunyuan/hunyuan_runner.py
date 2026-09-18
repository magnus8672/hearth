"""Fixed offline Hunyuan3D 2.0 shape/paint stages; children share the job cgroup."""
import argparse
import os
import subprocess
import sys
from pathlib import Path


def shape(args, work):
    import torch
    from hy3dgen.shapegen import FaceReducer, Hunyuan3DDiTFlowMatchingPipeline
    from PIL import Image
    from rembg import new_session, remove

    torch.set_num_threads(4)
    image = remove(Image.open(args.image).convert('RGB'), session=new_session('u2net'), bgcolor=[255, 255, 255, 0])
    image.save(work / 'reference.png')
    # Shape alone fits this 16 GiB profile. The pinned upstream shape offload
    # method expects a missing `components` property, so do not invoke it.
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(str(args.models), subfolder='hunyuan3d-dit-v2-0', device='cuda', use_safetensors=True)
    mesh = pipeline(image=image, num_inference_steps=50, guidance_scale=5.5,
                    generator=torch.Generator().manual_seed(args.seed), octree_resolution=args.resolution,
                    num_chunks=8000)[0]
    mesh = FaceReducer()(mesh, max_facenum=50000)
    mesh.export(work / 'shape.ply')


def paint(args, work):
    import torch
    import trimesh
    from accelerate import init_empty_weights
    from diffusers import AutoencoderKL, DDIMScheduler, EulerAncestralDiscreteScheduler, UNet2DConditionModel
    from hy3dgen.texgen.hunyuanpaint.pipeline import HunyuanPaintPipeline
    from hy3dgen.texgen.hunyuanpaint.unet.modules import UNet2p5DConditionModel
    from hy3dgen.texgen.pipelines import Hunyuan3DPaintPipeline, Hunyuan3DTexGenConfig
    from hy3dgen.texgen.utils.dehighlight_utils import Light_Shadow_Remover
    from hy3dgen.texgen.utils.multiview_utils import Multiview_Diffusion_Net
    from PIL import Image
    from safetensors.torch import load_file
    from transformers import CLIPImageProcessor, CLIPTextModel, CLIPTokenizer

    class LocalMultiview(Multiview_Diffusion_Net):
        def __init__(self, config):
            self.device, self.view_size = 'cpu', 512
            path = args.models / 'hunyuan3d-paint-v2-0'
            # The model index points to a loose `modules.py` and a duplicate
            # pickle checkpoint. Use reviewed engine code and pinned safetensors
            # directly. Meta initialization avoids a second full CPU copy.
            with init_empty_weights():
                unet = UNet2p5DConditionModel(UNet2DConditionModel.from_config(
                    UNet2DConditionModel.load_config(str(path / 'unet'))))
            unet.load_state_dict(load_file(str(path / 'unet/diffusion_pytorch_model.safetensors')), strict=True, assign=True)
            unet = unet.to(dtype=torch.float16)
            self.pipeline = HunyuanPaintPipeline(
                vae=AutoencoderKL.from_pretrained(str(path / 'vae'), torch_dtype=torch.float16, local_files_only=True),
                text_encoder=CLIPTextModel.from_pretrained(str(path / 'text_encoder'), torch_dtype=torch.float16, local_files_only=True),
                tokenizer=CLIPTokenizer.from_pretrained(str(path / 'tokenizer'), local_files_only=True),
                feature_extractor=CLIPImageProcessor.from_pretrained(str(path / 'feature_extractor'), local_files_only=True),
                scheduler=DDIMScheduler.from_pretrained(str(path / 'scheduler'), local_files_only=True),
                unet=unet,
            )
            self.pipeline.scheduler = EulerAncestralDiscreteScheduler.from_config(self.pipeline.scheduler.config, timestep_spacing='trailing')
            self.pipeline.set_progress_bar_config(disable=True)

        def __call__(self, *args, **kwargs):
            # This custom pipeline reads learned UNet parameters outside its
            # forward hook, so generic model CPU offload mixes CPU/CUDA tensors.
            # Keep the multiview pipeline resident only for its own call, after
            # the delight pipeline has offloaded itself.
            self.pipeline.to('cuda')
            try:
                return super().__call__(*args, **kwargs)
            finally:
                self.pipeline.to('cpu')
                torch.cuda.empty_cache()

    class LocalPaint(Hunyuan3DPaintPipeline):
        def load_models(self):
            self.models['delight_model'] = Light_Shadow_Remover(self.config)
            self.models['multiview_model'] = LocalMultiview(self.config)

    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    config = Hunyuan3DTexGenConfig(str(args.models / 'hunyuan3d-delight-v2-0'),
                                  str(args.models / 'hunyuan3d-paint-v2-0'), 'hunyuan3d-paint-v2-0')
    # Load on CPU first. Move each paint pipeline to CUDA only when it executes.
    config.device = 'cpu'
    pipeline = LocalPaint(config)
    pipeline.models['delight_model'].pipeline.enable_model_cpu_offload()
    for component in pipeline.models.values():
        component.pipeline.enable_vae_slicing()
        component.pipeline.enable_vae_tiling()
    mesh = trimesh.load(work / 'shape.ply', force='mesh', process=False)
    mesh = pipeline(mesh, Image.open(work / 'reference.png').convert('RGBA'))
    mesh.export(args.output, file_type='glb')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--models', required=True, type=Path)
    parser.add_argument('--resolution', type=int, choices=[512], required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--stage', choices=['shape', 'paint'])
    args = parser.parse_args()
    if not 0 <= args.seed <= 2147483647:
        parser.error('Seed outside the supported range.')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'engine'))
    sys.path.insert(0, str(root / 'engine/hy3dgen/texgen/custom_rasterizer'))
    work = args.output.with_suffix('.work')
    work.mkdir(mode=0o700, exist_ok=True)
    if args.stage:
        (shape if args.stage == 'shape' else paint)(args, work)
        return
    environment = os.environ | {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                                'HF_HOME': str(work / 'cache/huggingface'), 'XDG_CACHE_HOME': str(work / 'cache'),
                                'U2NET_HOME': str(args.models / 'background'), 'OMP_NUM_THREADS': '4',
                                'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True'}
    for stage in ['shape', 'paint']:
        print('Hunyuan3D 2.0: ' + stage, flush=True)
        # Separate processes release shape CPU/GPU allocations before texture loading.
        # No new session: cancellation kills this entire process group before release.
        subprocess.run([sys.executable, str(Path(__file__).resolve()), str(args.image), str(args.output),
                        '--models', str(args.models), '--resolution', str(args.resolution),
                        '--seed', str(args.seed), '--stage', stage], env=environment, check=True)


if __name__ == '__main__':
    main()
