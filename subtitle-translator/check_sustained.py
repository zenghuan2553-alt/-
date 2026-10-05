"""15 minute silent pipeline check using only generated test audio, not user audio."""
import ctypes
import json
import os
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from scipy.io import wavfile
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app import Controls, Translator, ROOT
from core import mono_16k, put_latest


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t) for name in ["PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage"]]


def memory_mb():
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(MemoryCounters), ctypes.c_ulong]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return round(counters.WorkingSetSize / 1024 / 1024, 1)


class SyntheticWorker(Translator):
    def capture(self):
        rate, samples = wavfile.read(ROOT / "test-audio" / "00.wav")
        samples = samples.astype("float32") / 32768
        chunk = mono_16k(samples, rate)
        self.status.emit("Sustained synthetic audio test running")
        while not self.stop_event.is_set():
            put_latest(self.pending, (chunk, time.monotonic()))
            self.stop_event.wait(3)


if __name__ == "__main__":
    app = QApplication([])
    window = Controls()
    worker = SyntheticWorker()
    window.worker = worker
    counts = [0]
    errors = []
    readings = []
    started = time.monotonic()

    def display(text):
        counts[0] += 1
        window.overlay.display(text)

    def sample():
        readings.append({"seconds": round(time.monotonic() - started), "subtitles": counts[0], "memory_mb": memory_mb()})
        print(json.dumps(readings[-1]), flush=True)

    worker.subtitle.connect(display)
    worker.failure.connect(errors.append)
    worker.finished.connect(app.quit)
    timer = QTimer()
    timer.timeout.connect(sample)
    timer.start(60000)
    QTimer.singleShot(900000, worker.stop_event.set)
    worker.start()
    app.exec()
    sample()
    window.worker = None
    window.close()
    result = {"seconds": round(time.monotonic() - started, 1), "subtitles": counts[0], "errors": errors,
              "memory_samples": readings, "source": "synthetic local file; no speaker playback"}
    (ROOT / "sustained-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    assert counts[0] >= 200 and not errors, result
    assert len(readings) >= 10 and readings[-1]["memory_mb"] <= max(x["memory_mb"] for x in readings[:3]) + 150, result
    print("15-minute synthetic pipeline check passed.", flush=True)
