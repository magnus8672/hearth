"""Offline CPU speech feasibility probe using explicitly supplied installed Kokoro files.

This is a developer probe, not a registered hearth provider or managed runtime.
Run it using the Python environment in which kokoro-onnx is already installed.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import socket
import time
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--voices', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--voice', default='af_heart')
    args = parser.parse_args()
    model, voices = args.model.resolve(strict=True), args.voices.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ['ONNX_PROVIDER'] = 'CPUExecutionProvider'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'

    def offline(*args, **kwargs):
        raise RuntimeError('This speech probe does not allow network access.')

    # This probe uses only the existing model/voices and installed phonemizer.
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    socket.create_connection = offline
    import numpy as np
    from kokoro_onnx import Kokoro

    started = time.monotonic()
    runtime = Kokoro(str(model), str(voices))
    assert runtime.sess.get_providers() == ['CPUExecutionProvider']
    load_seconds = time.monotonic() - started
    text = 'Welcome home. Your hearth can bring your models together, while your conversations stay on your own machines.'
    started = time.monotonic()
    samples, rate = runtime.create(text, voice=args.voice, speed=1.0, lang='en-us')
    generation_seconds = time.monotonic() - started
    assert samples.ndim == 1 and np.isfinite(samples).all() and rate == 24000
    duration = len(samples) / rate
    assert 3 < duration < 30
    peak = float(np.max(np.abs(samples)))
    assert 0.01 < peak <= 1.0
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype('<i2').tobytes()
    wav_path = args.output / 'hearth-speech-sample.wav'
    with wave.open(str(wav_path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm)
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = {
        'scope': 'Offline local CPU feasibility only. Not a hearth provider, transcription test, or perceptual quality approval.',
        'packages': {key: importlib.metadata.version(key) for key in ['kokoro-onnx', 'onnxruntime', 'numpy']},
        'model_sha256': digest(model), 'voices_sha256': digest(voices),
        'voice': args.voice, 'text': text, 'execution_provider': 'CPUExecutionProvider',
        'network_connect_blocked_in_probe': True, 'model_downloads': 0,
        'load_seconds': round(load_seconds, 3), 'generation_seconds': round(generation_seconds, 3),
        'audio_seconds': round(duration, 3), 'real_time_factor': round(generation_seconds / duration, 3),
        'sample_rate': rate, 'channels': 1, 'bits_per_sample': 16,
        'sample_sha256': digest(wav_path), 'perceptual_listening': 'pending',
    }
    (args.output / 'speech-feasibility.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
