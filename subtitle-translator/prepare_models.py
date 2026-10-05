"""Download once; the running translator never accesses a network service."""
import os
import fnmatch
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(ROOT / "models" / "cache"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

def download(repo, folder, patterns):
    folder.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}?blobs=true", timeout=30) as response:
        metadata = json.load(response)
    revision = metadata["sha"]
    for entry in metadata["siblings"]:
        name = entry["rfilename"]
        if not any(fnmatch.fnmatch(name, pattern) for pattern in patterns):
            continue
        target = folder / name
        expected = entry.get("lfs", {}).get("sha256")
        size = entry.get("size")
        if target.exists() and (size is None or target.stat().st_size == size):
            with target.open("rb") as existing:
                valid = not expected or hashlib.file_digest(existing, "sha256").hexdigest() == expected
            if valid:
                continue
        print(f"下载 {repo}/{name}", flush=True)
        partial = target.with_suffix(target.suffix + ".part")
        if partial.exists() and size is not None and partial.stat().st_size >= size:
            with partial.open("rb") as existing:
                valid = partial.stat().st_size == size and (not expected or hashlib.file_digest(existing, "sha256").hexdigest() == expected)
            if not valid:
                partial.write_bytes(b"")
        url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
        for attempt in range(8):
            received = partial.stat().st_size if partial.exists() else 0
            if size is not None and received == size:
                break
            headers = {"Range": f"bytes={received}-"} if received else {}
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 206:
                        received = 0
                    elif not response.headers.get("Content-Range", "").startswith(f"bytes {received}-"):
                        raise RuntimeError("服务器返回了错误的文件范围")
                    with partial.open("ab" if received else "wb") as output:
                        while block := response.read(1024 * 1024):
                            output.write(block)
                            received += len(block)
                            if received % (20 * 1024 * 1024) < len(block):
                                print(f"  {received // (1024 * 1024)} MB", flush=True)
                if size is None or received == size:
                    break
            except (OSError, TimeoutError) as exc:
                print(f"连接中断，将续传（{attempt + 1}/8）：{exc}", flush=True)
            print("下载未完成，继续下载剩余部分…", flush=True)
            time.sleep(1)
        with partial.open("rb") as complete:
            digest = hashlib.file_digest(complete, "sha256").hexdigest()
        if (size is not None and partial.stat().st_size != size) or (expected and digest != expected):
            raise RuntimeError(f"下载文件校验失败：{name}，请重新运行准备")
        partial.replace(target)
    (folder / "source.json").write_text(json.dumps({"repository": repo, "revision": revision}), encoding="utf-8")


def prepare():
    print("下载免费英文识别模型（首次准备需要网络）…", flush=True)
    download(
        "Systran/faster-whisper-base.en", ROOT / "models" / "whisper",
        ["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "README.md"],
    )
    print("下载免费英译中模型…", flush=True)
    download(
        "gaudi/opus-mt-en-zh-ctranslate2", ROOT / "models" / "translation",
        ["config.json", "model.bin", "shared_vocabulary.json", "*.spm", "README.md"],
    )
    if "--download-only" in sys.argv:
        return
    validate_models()


def validate_models():
    from faster_whisper import WhisperModel
    from translation import ChineseTranslator
    WhisperModel(str(ROOT / "models" / "whisper"), device="cpu", compute_type="int8",
                 local_files_only=True)
    translator = ChineseTranslator(ROOT / "models" / "translation")
    sample = translator.translate("Hello, this is an offline translation test.")
    if not any("\u4e00" <= character <= "\u9fff" for character in sample):
        raise RuntimeError("本地中文翻译自检失败")
    print("翻译自检：" + sample, flush=True)
    (ROOT / "models" / "ready").write_text("Models loaded successfully\n", encoding="utf-8")
    print("准备完成。现在可以双击 start.cmd。", flush=True)


if __name__ == "__main__":
    validate_models() if "--check-only" in sys.argv else prepare()
