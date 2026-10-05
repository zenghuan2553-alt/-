import queue
import unittest

import numpy as np
from core import AudioSegmenter, mono_16k, put_latest, voiced


class AudioChecks(unittest.TestCase):
    def test_pauses_and_continuous_sound_limit(self):
        segmenter = AudioSegmenter(16000)
        silent = np.zeros((1600, 2), dtype=np.float32)
        sound = np.ones((1600, 2), dtype=np.float32) * 0.1
        self.assertIsNone(segmenter.push(silent))
        for _ in range(10):
            self.assertIsNone(segmenter.push(sound))
        for _ in range(3):
            self.assertIsNone(segmenter.push(silent))
        self.assertEqual(segmenter.push(silent).shape, (22400, 2))
        self.assertIsNone(segmenter.push(silent))
        for _ in range(59):
            self.assertIsNone(segmenter.push(sound))
        self.assertEqual(segmenter.push(sound).shape, (96000, 2))

    def test_bounded_queue_keeps_latest(self):
        pending = queue.Queue(maxsize=2)
        self.assertFalse(put_latest(pending, 1))
        self.assertFalse(put_latest(pending, 2))
        self.assertTrue(put_latest(pending, 3))
        self.assertEqual([pending.get(), pending.get()], [2, 3])

    def test_resampling_and_silence(self):
        t = np.arange(48000) / 48000
        stereo = np.stack([0.1 * np.sin(2 * np.pi * 440 * t)] * 2, axis=1)
        result = mono_16k(stereo, 48000)
        self.assertEqual(result.shape, (16000,))
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(voiced(result))
        self.assertFalse(voiced(np.zeros(16000, dtype=np.float32)))
        peak = np.argmax(np.abs(np.fft.rfft(result)))
        self.assertEqual(peak, 440)


if __name__ == "__main__":
    unittest.main()
