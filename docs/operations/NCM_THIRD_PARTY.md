# NCM runtime sources

The XSum inference adapter follows the sampling procedure in `scripts/eval_shard.py`
from [HazyResearch/ncm](https://github.com/HazyResearch/ncm), pinned to
`c70274273f489abc73832b2b98584a8483b6b203`. Its MIT license must accompany the
prepared source package. Model checkpoints are separately pinned to
`hazyresearch/ncm-checkpoints` revision `d342ce8aaea58830eef3b8ad473664673e41f692`.
The model repository identifies its license as MIT. GPT-2 tokenizer files use
`openai-community/gpt2` revision `607a30d783dfa663caf39e06633721c8d4cfcd7e`.

This adapter exposes the released English XSum specialist, not an instruction-tuned
chat model. It rejects input over 512 tokens and returns at most 48 decoded tokens.
No benchmark speedup or AMD GPU support is implied. Preserve the licenses and
notices of Python, PyTorch, Transformers, llama.cpp and their dependencies when
redistributing a prepared runtime. A source pin does not establish quality or
Windows hardware qualification.

## Upstream MIT notice

MIT License

Copyright (c) 2025 hermann kumbong

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
