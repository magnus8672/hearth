"""Only bounded, ordinary mono PCM WAV files may enter the private audio store."""
import array
import io
import sys
import wave

MAX_AUDIO_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 24000 * 600


def validate_wav(raw, *, frames=None):
    if not 44 <= len(raw) <= MAX_AUDIO_BYTES:
        raise ValueError('Audio exceeds the supported size.')
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE' or int.from_bytes(raw[4:8], 'little') + 8 != len(raw):
        raise ValueError('Audio must be one complete RIFF WAV file.')
    try:
        with wave.open(io.BytesIO(raw), 'rb') as wav:
            count = wav.getnframes()
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 24000, 'NONE'):
                raise ValueError('Audio must be mono 24 kHz, 16-bit PCM.')
            if not 2400 <= count <= MAX_FRAMES or frames is not None and count != frames:
                raise ValueError('Audio duration does not match its receipt or supported limits.')
            samples = wav.readframes(count)
            if len(samples) != count * 2:
                raise ValueError('The audio file was truncated.')
        values = array.array('h', samples)
        if sys.byteorder != 'little':
            values.byteswap()
        if max(abs(value) for value in values) < 100:
            raise ValueError('The audio result is silent.')
        return count
    except (wave.Error, EOFError):
        raise ValueError('The audio file could not be decoded.') from None
