"""Bounded PCM WAV ingestion without container codecs, URLs or executable metadata."""
import array
import audioop
import io
import sys
import wave

MAX_UPLOAD = 8_388_608
MAX_SECONDS = 120


def normalize(raw):
    if not 44 <= len(raw) <= MAX_UPLOAD or raw[:4] != b'RIFF' or raw[8:12] != b'WAVE' or int.from_bytes(raw[4:8], 'little') + 8 != len(raw):
        raise ValueError('Choose a complete PCM WAV file smaller than 8 MB.')
    try:
        with wave.open(io.BytesIO(raw), 'rb') as wav:
            channels, width, rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
            if channels not in (1, 2) or width != 2 or rate not in (8000, 16000, 24000, 32000, 44100, 48000) or wav.getcomptype() != 'NONE':
                raise ValueError('Use mono or stereo 16-bit PCM WAV at 8, 16, 24, 32, 44.1 or 48 kHz.')
            if not rate // 2 <= frames <= rate * MAX_SECONDS:
                raise ValueError('Choose audio between half a second and two minutes long.')
            pcm = wav.readframes(frames)
            if len(pcm) != frames * channels * width:
                raise ValueError('The WAV file is truncated.')
        if channels == 2:
            pcm = audioop.tomono(pcm, 2, .5, .5)
        if rate != 16000:
            pcm = audioop.ratecv(pcm, 2, 1, rate, 16000, None)[0]
        samples = array.array('h', pcm)
        if sys.byteorder != 'little':
            samples.byteswap()
        if max(abs(value) for value in samples) < 100:
            raise ValueError('No audible signal was found. Check your microphone or choose another recording.')
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm)
        return output.getvalue()
    except (wave.Error, EOFError, audioop.error):
        raise ValueError('The WAV file could not be decoded.') from None
