"""Pinned NCM XSum inference adapter. No chat, history, tools or downloads.

Sampling follows HazyResearch/ncm scripts/eval_shard.py at c702742,
MIT licensed. See docs/operations/NCM_THIRD_PARTY.md. Inputs exceeding the checkpoint's 512
GPT-2 tokens are rejected rather than silently sliced as in the evaluation.
"""
import sys
from pathlib import Path


class XSum:
    def __init__(self, root, device='cpu', threads=4):
        import torch
        from omegaconf import OmegaConf
        from transformers import AutoTokenizer

        root = Path(root).resolve()
        sys.path.insert(0, str(root / 'source'))
        from models.next_concept import NextConceptTransformer
        from models.vqvae import VQVAE

        if device not in ('cpu', 'cuda') or not 1 <= threads <= 16:
            raise ValueError('Use cpu or cuda and 1–16 threads.')
        if device == 'cuda' and not torch.cuda.is_available():
            raise ValueError('CUDA was requested but is unavailable. AMD Windows acceleration is not qualified.')
        torch.set_num_threads(threads)
        cfg = OmegaConf.load(root / 'xsum/config.yaml')
        if cfg.task != 'xsum' or cfg.model.prefix_len != 512 or cfg.tokenizer.vqvae.context_length != 48 or cfg.model.use_flex_attention:
            raise ValueError('Unsupported NCM checkpoint configuration.')
        self.tokenizer = AutoTokenizer.from_pretrained(root / 'gpt2', local_files_only=True)
        self.tokenizer.add_special_tokens({'pad_token': '<|pad|>'})
        vq_config = dict(cfg.tokenizer.vqvae)
        vq_config.pop('checkpoint_path', None)
        self.vq = VQVAE(**vq_config)
        self.vq.load_state_dict(torch.load(root / 'xsum/tokenizer.pt', map_location='cpu', weights_only=True)['model'], strict=True)
        self.vq = self.vq.to(device).eval()
        self.net = NextConceptTransformer(vqvae_local=self.vq, config=cfg.model).to(device)
        checkpoint = torch.load(root / 'xsum/generator.pt', map_location='cpu', weights_only=True)
        self.net.load_state_dict(checkpoint['model'], strict=True)
        self.net.eval()
        self.allowance = checkpoint['inference']['token_unigram'].to(device).double()
        self.device, self.cfg = device, cfg

    def summarize(self, text):
        import torch

        ids = self.tokenizer.encode(text, add_special_tokens=False)
        if not 1 <= len(ids) <= 512:
            raise ValueError(f'NCM XSum accepts 1–512 source tokens; received {len(ids)}. No text was truncated.')
        prefix = torch.tensor([ids + [self.tokenizer.pad_token_id] * (512-len(ids))], device=self.device)
        with torch.inference_mode():
            codes = self.net.generate(None, prefix, temperature=1.0, top_k=1, top_p=0.0,
                                      cfg_scale=0.0, cfg_null_eos=self.tokenizer.eos_token_id)
            _, levels = self.vq.vq.idx_to_zhats(codes, return_zlevels=True)
            logits = self.vq.decoder(levels[-1]).double()
            # Reproduce the released XSum decoder's frequency and adjacency policy.
            batch, length, vocab = logits.shape
            allowance = (self.allowance[:vocab] * length)[None, :]
            counts = torch.zeros(batch, vocab, dtype=torch.float64, device=self.device)
            history = []
            for index in range(length):
                step = logits[:, index, :].clone()
                step -= 2.0 * (counts-allowance).clamp_min(0)
                step += ((length-index)/length) * (allowance-counts).clamp_min(0)
                for distance, token in enumerate(reversed(history[-4:])):
                    step.scatter_add_(1, token[:, None], torch.full((batch, 1), -5.0*0.5**distance,
                                                                 dtype=torch.float64, device=self.device))
                token = step.argmax(-1)
                history.append(token)
                counts.scatter_add_(1, token[:, None], torch.ones(batch, 1, dtype=torch.float64, device=self.device))
            output = [int(token[0]) for token in history]
        if self.tokenizer.eos_token_id in output:
            output = output[:output.index(self.tokenizer.eos_token_id)]
        output = [t for t in output if t not in (self.tokenizer.eos_token_id, self.tokenizer.pad_token_id)]
        return {'text': self.tokenizer.decode(output, skip_special_tokens=True),
                'input_tokens': len(ids), 'output_tokens': len(output), 'truncated': False}
