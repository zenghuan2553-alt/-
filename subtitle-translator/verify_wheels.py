"""Check mirrored wheels against PyPI's own SHA-256 metadata before installing."""
import concurrent.futures
import hashlib
import json
import time
import urllib.request
from pathlib import Path


def verify(wheel):
    name, version = wheel.name.split("-")[:2]
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
                metadata = json.load(response)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(1)
    expected = next(entry["digests"]["sha256"] for entry in metadata["urls"] if entry["filename"] == wheel.name)
    with wheel.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError("Wheel hash mismatch: " + wheel.name)
    return wheel.name


if __name__ == "__main__":
    wheels = list((Path(__file__).resolve().parent / "wheels").glob("*.whl"))
    assert wheels, "No downloaded wheels"
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for name in pool.map(verify, wheels):
            print("Verified: " + name, flush=True)
