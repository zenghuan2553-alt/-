"""Real WASAPI playback check; plays three local synthetic English samples."""
import json
import os
import time
import winsound

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app import Controls, ROOT


if __name__ == "__main__":
    app = QApplication([])
    window = Controls()
    messages = []
    started = time.monotonic()
    failure = []
    playing = False

    def state_changed(message):
        global playing
        print(message, flush=True)
        if message.startswith("监听中：") and not playing:
            playing = True
            for delay, index in [(1000, 0), (7000, 2), (13000, 9)]:
                QTimer.singleShot(delay, lambda index=index: winsound.PlaySound(
                    str(ROOT / "test-audio" / f"{index:02}.wav"), winsound.SND_FILENAME | winsound.SND_ASYNC))
            QTimer.singleShot(22000, window.stop)

    def subtitle(text):
        messages.append({"elapsed": round(time.monotonic() - started, 2), "chinese": text})
        print(text, flush=True)

    window.start()
    assert window.worker, "Prepare models first"
    window.worker.status.connect(state_changed)
    window.worker.subtitle.connect(subtitle)
    window.worker.failure.connect(failure.append)
    window.worker.finished.connect(app.quit)
    QTimer.singleShot(60000, window.stop)
    app.exec()
    winsound.PlaySound(None, 0)
    result = {"subtitles": messages, "errors": failure, "passed": len(messages) >= 3 and not failure,
              "seconds": round(time.monotonic() - started, 2)}
    (ROOT / "live-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    assert result["passed"], result
    print("Real loopback → offline ASR → Chinese subtitle → stop: passed.", flush=True)
