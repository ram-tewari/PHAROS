"""Download the pinned ONNX embedding model used by EMBEDDING_BACKEND=onnx.

    python scripts/fetch_onnx_model.py                  # -> models/all-MiniLM-L6-v2
    python scripts/fetch_onnx_model.py /opt/models/mini # custom directory

Fetches model.onnx and tokenizer.json for sentence-transformers/all-MiniLM-L6-v2
(Apache-2.0) at a fixed Hugging Face revision and checks each file's SHA-256, so
a build either gets exactly these bytes or fails. Files that are already present
with the right hash are not downloaded again. Standard library only, so it can
run before any requirements are installed.

Point the app at the result with EMBEDDING_ONNX_DIR=<dir> and
EMBEDDING_MODEL_ID=all-MiniLM-L6-v2-onnx. Changing the model requires
re-indexing.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
FILES = {
    # local name: (path in the Hugging Face repo, sha256)
    "model.onnx": ("onnx/model.onnx", "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"),
    "tokenizer.json": ("tokenizer.json", "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"),
}
DEFAULT_DIR = Path(__file__).resolve().parents[1] / "models" / "all-MiniLM-L6-v2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name, (remote, expected) in FILES.items():
        target = dest / name
        if target.is_file() and sha256(target) == expected:
            print(f"{name}: present")
            continue
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{remote}"
        partial = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as resp, partial.open("wb") as fh:
            while block := resp.read(1 << 20):
                fh.write(block)
        actual = sha256(partial)
        if actual != expected:
            partial.unlink()
            raise SystemExit(f"{name}: sha256 mismatch (expected {expected}, got {actual})")
        partial.replace(target)
        print(f"{name}: downloaded ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    fetch(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR)
