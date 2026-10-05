"""Bounded live audio queue and audio conversion, without desktop dependencies."""
import math
import queue

import numpy as np
from scipy.signal import resample_poly

ASR_PROMPT = "Technical terms: ComfyUI, VAE decoder, checkpoint, latent, sampler."


def put_latest(pending, item):
    """Keep recent audio rather than accumulating an unbounded subtitle delay."""
    dropped = False
    try:
        pending.put_nowait(item)
    except queue.Full:
        try:
            pending.get_nowait()
            dropped = True
        except queue.Empty:
            pass
        pending.put_nowait(item)
    return dropped


def mono_16k(samples, rate):
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    divisor = math.gcd(int(rate), 16000)
    return resample_poly(mono, 16000 // divisor, int(rate) // divisor).astype(np.float32)


def voiced(samples):
    # ponytail: cheap silence gate; actual speech filtering is Whisper's Silero VAD.
    return bool(samples.size and np.sqrt(np.mean(samples ** 2)) > 0.001)


class AudioSegmenter:
    """End at a short pause, with a hard limit when there is continuous sound."""
    def __init__(self, rate, pause_seconds=0.4, max_seconds=6):
        self.rate = rate
        self.pause_seconds = pause_seconds
        self.max_seconds = max_seconds
        self.blocks = []
        self.duration = 0
        self.quiet = 0

    def push(self, block):
        speech = voiced(block)
        if not self.blocks and not speech:
            return None
        seconds = len(block) / self.rate
        self.blocks.append(block)
        self.duration += seconds
        self.quiet = 0 if speech else self.quiet + seconds
        # ponytail: energy detects pauses, not speech; Whisper VAD filters music/noise later.
        if self.quiet < self.pause_seconds - 1e-6 and self.duration < self.max_seconds - 1e-6:
            return None
        result = np.concatenate(self.blocks)
        self.blocks.clear()
        self.duration = self.quiet = 0
        return result
