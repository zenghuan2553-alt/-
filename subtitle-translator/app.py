"""Windows loopback → English ASR → offline Chinese subtitles."""
import os
import queue
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ.setdefault("HF_HOME", str(ROOT / "models" / "cache"))

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QComboBox
from core import ASR_PROMPT, AudioSegmenter, mono_16k, put_latest, voiced


class Translator(QThread):
    status = Signal(str)
    subtitle = Signal(str)
    failure = Signal(str)

    def __init__(self, device_index=None):
        super().__init__()
        self.device_index = device_index
        self.stop_event = threading.Event()
        self.pending = queue.Queue(maxsize=2)

    def capture(self):
        import pyaudiowpatch as pa
        try:
            with pa.PyAudio() as audio:
                device = (audio.get_default_wasapi_loopback() if self.device_index is None
                          else audio.get_device_info_by_index(self.device_index))
                rate = int(device["defaultSampleRate"])
                channels = int(device["maxInputChannels"])
                frames = max(1, rate // 10)
                with audio.open(format=pa.paFloat32, channels=channels, rate=rate,
                                input=True, input_device_index=device["index"], frames_per_buffer=frames) as stream:
                    self.status.emit("监听中：" + device["name"])
                    segmenter = AudioSegmenter(rate)
                    last_buffer = time.monotonic()
                    silence = np.zeros((frames, channels), dtype=np.float32)
                    while not self.stop_event.is_set():
                        available = stream.get_read_available()
                        now = time.monotonic()
                        if available:
                            data = stream.read(min(frames, available), exception_on_overflow=False)
                            block = np.frombuffer(data, dtype=np.float32).reshape(-1, channels).copy()
                            last_buffer = now
                        elif segmenter.blocks and now - last_buffer >= 0.1:
                            # WASAPI can stop delivering packets when all players are silent.
                            block = silence
                            last_buffer = now
                        else:
                            self.stop_event.wait(0.02)
                            continue
                        segment = segmenter.push(block)
                        if segment is not None:
                            chunk = mono_16k(segment, rate)
                            if voiced(chunk) and put_latest(self.pending, (chunk, time.monotonic())):
                                self.status.emit("处理较慢，已跳过旧片段；请只播放一个音源。")
        except Exception as exc:
            if not self.stop_event.is_set():
                self.failure.emit("无法捕获系统声音，请检查输出设备：" + str(exc))
            self.stop_event.set()

    def run(self):
        capture_thread = None
        try:
            self.status.emit("加载本地模型，请稍候…")
            from faster_whisper import WhisperModel
            from translation import ChineseTranslator
            asr = WhisperModel(str(ROOT / "models" / "whisper"), device="cpu", compute_type="int8",
                               cpu_threads=4, local_files_only=True)
            model = ChineseTranslator(ROOT / "models" / "translation")
            if self.stop_event.is_set():
                return
            capture_thread = threading.Thread(target=self.capture, daemon=True)
            capture_thread.start()
            while not self.stop_event.is_set():
                try:
                    samples, captured = self.pending.get(timeout=0.2)
                except queue.Empty:
                    continue
                if time.monotonic() - captured > 8:
                    self.status.emit("已跳过过时音频，保持字幕接近当前播放。")
                    continue
                segments, _ = asr.transcribe(samples, language="en", beam_size=1,
                                            vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
                                            initial_prompt=ASR_PROMPT,
                                            condition_on_previous_text=False)
                text = " ".join(s.text.strip() for s in segments).strip()
                if not text or self.stop_event.is_set():
                    continue
                chinese = model.translate(text)
                if not self.stop_event.is_set() and chinese:
                    self.subtitle.emit(chinese)
                    self.status.emit(f"监听中 · 本地 CPU · 片段结束后耗时 {time.monotonic() - captured:.1f} 秒")
        except Exception as exc:
            self.failure.emit("运行失败：" + str(exc) + "\n模型未准备时请先运行 setup.cmd。")
        finally:
            self.stop_event.set()
            if capture_thread:
                capture_thread.join(timeout=3)


class Subtitles(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label = QLabel("中文字幕将在这里显示")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("background:rgba(0,0,0,185);color:white;font-size:26px;padding:14px;border-radius:10px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        area = QApplication.primaryScreen().availableGeometry()
        width = min(900, area.width() - 40)
        self.setFixedWidth(width)
        self.resize(width, 110)
        self.move(area.x() + (area.width() - width) // 2, area.bottom() - 150)
        self.drag_offset = None
        self.clear_timer = QTimer(self)
        self.clear_timer.setSingleShot(True)
        self.clear_timer.timeout.connect(self.hide)

    def display(self, text):
        self.label.setText(text)
        self.adjustSize()
        self.show()
        self.clear_timer.start(10000)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None


class Controls(QWidget):
    def __init__(self):
        super().__init__()
        if "Microsoft YaHei UI" not in QFontDatabase.families():
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc"))
        QApplication.instance().setFont(QFont("Microsoft YaHei UI", 10))
        self.setWindowTitle("本地实时中文字幕 · 零付费版")
        self.resize(460, 230)
        self.worker = None
        self.closing = False
        self.overlay = Subtitles()
        layout = QVBoxLayout(self)
        description = QLabel("播放英文视频后，点击开始。识别与翻译均在本机运行。")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.devices = QComboBox()
        self.devices.addItem("系统默认输出设备", None)
        self.state = QLabel("就绪 · 全程本地运行" if (ROOT / "models" / "ready").exists()
                            else "已停止 · 首次使用请先运行 setup.cmd")
        self.state.setWordWrap(True)
        try:
            import pyaudiowpatch as pa
            with pa.PyAudio() as audio:
                for device in audio.get_loopback_device_info_generator():
                    self.devices.addItem(device["name"], int(device["index"]))
        except Exception as exc:
            self.state.setText("设备检测失败：" + str(exc))
        layout.addWidget(self.devices)
        row = QHBoxLayout()
        self.start_button = QPushButton("开始翻译")
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        layout.addWidget(self.state)
        layout.addWidget(QLabel("字幕可拖动；请尽量只播放一个音源。"))

    def start(self):
        if not (ROOT / "models" / "ready").exists():
            self.state.setText("免费模型尚未准备，请先双击 setup.cmd，完成后再点击开始。")
            return
        self.overlay.display("正在加载模型…")
        self.start_button.setEnabled(False)
        self.devices.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.worker = Translator(self.devices.currentData())
        self.worker.status.connect(self.on_status)
        self.worker.subtitle.connect(self.on_subtitle)
        self.worker.failure.connect(self.on_failure)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def on_status(self, message):
        if self.worker and not self.worker.stop_event.is_set():
            self.state.setText(message)

    def on_subtitle(self, text):
        if self.worker and not self.worker.stop_event.is_set():
            self.overlay.display(text)

    def on_failure(self, message):
        self.state.setText(message)
        self.overlay.hide()

    def stop(self):
        if self.worker:
            self.worker.stop_event.set()
            self.state.setText("正在停止，请等待当前本地计算结束…")
            self.stop_button.setEnabled(False)
        self.overlay.clear_timer.stop()
        self.overlay.hide()

    def finished(self):
        self.start_button.setEnabled(True)
        self.devices.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.overlay.hide()
        self.worker.deleteLater()
        self.worker = None
        if self.state.text().startswith("正在停止"):
            self.state.setText("已停止")
        if self.closing:
            self.close()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.stop()
            event.ignore()
        else:
            self.overlay.close()
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Controls()
    window.show()
    sys.exit(app.exec())
