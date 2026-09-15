"""Known synthetic audio checks modality support, not broad accent/noise accuracy."""
import re
from pathlib import Path

REFERENCE = 'Welcome home. Your hearth brings your models together.'


def word_error_rate(expected, actual):
    left, right = re.findall(r'[a-z0-9]+', expected.lower()), re.findall(r'[a-z0-9]+', actual.lower())
    row = list(range(len(right) + 1))
    for i, word in enumerate(left, 1):
        following = [i]
        for j, other in enumerate(right, 1):
            following.append(min(following[-1] + 1, row[j] + 1, row[j - 1] + (word != other)))
        row = following
    return row[-1] / max(1, len(left))


def recording():
    return Path(__file__).with_name('assets').joinpath('transcription-probe.wav').read_bytes()
