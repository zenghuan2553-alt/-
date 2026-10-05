"""Offline model and UI checks on locally synthesized English test audio."""
import json
import os
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from PySide6.QtWidgets import QApplication
from faster_whisper import WhisperModel
from app import Controls, ROOT
from translation import ChineseTranslator
from core import ASR_PROMPT


def check():
    started = time.monotonic()
    asr = WhisperModel(str(ROOT / "models" / "whisper"), device="cpu", compute_type="int8", local_files_only=True)
    translator = ChineseTranslator(ROOT / "models" / "translation")
    originals = json.loads((ROOT / "test-audio" / "sentences.json").read_text(encoding="utf-8-sig"))
    results = []
    for index, original in enumerate(originals):
        begin = time.monotonic()
        segments, _ = asr.transcribe(str(ROOT / "test-audio" / f"{index:02}.wav"), language="en",
                                    beam_size=1, vad_filter=True, condition_on_previous_text=False,
                                    initial_prompt=ASR_PROMPT)
        recognized = " ".join(segment.text.strip() for segment in segments)
        chinese = translator.translate(recognized)
        assert recognized and any("\u4e00" <= char <= "\u9fff" for char in chinese), (recognized, chinese)
        results.append({"input": original, "recognized": recognized, "chinese": chinese,
                        "processing_seconds": round(time.monotonic() - begin, 3)})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    app = QApplication([])
    window = Controls()
    window.show()
    window.overlay.display("现在连接 VAE 解码器。\n这是一条本地中文字幕测试。")
    app.processEvents()
    window.grab().save(str(ROOT / "control-preview.png"))
    window.overlay.grab().save(str(ROOT / "subtitle-preview.png"))
    assert window.devices.count() >= 1
    window.close()
    report = {"offline": True, "samples": results, "total_seconds": round(time.monotonic() - started, 2)}
    (ROOT / "integration-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Offline models and offscreen UI checks passed.", flush=True)


if __name__ == "__main__":
    check()
