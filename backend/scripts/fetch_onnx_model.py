"""Download a pinned ONNX embedding model used by EMBEDDING_BACKEND=onnx.

    python scripts/fetch_onnx_model.py                  # all-MiniLM-L6-v2 -> models/all-MiniLM-L6-v2
    python scripts/fetch_onnx_model.py /opt/models/mini # same model, custom directory
    python scripts/fetch_onnx_model.py --model granite-embedding-english-r2-int8 [dir]
    python scripts/fetch_onnx_model.py --list

Each model is fetched at a fixed Hugging Face revision and every file's SHA-256
is checked, so a build either gets exactly these bytes or fails. Files already
present with the right hash are not downloaded again. The directory also gets
``pharos_model.json`` (pooling, query/document prefixes, maximum length, ONNX
file), which ``OnnxEmbedder`` reads. Standard library only, so it can run
before any requirements are installed.

Point the app at the result with EMBEDDING_ONNX_DIR=<dir> and
EMBEDDING_MODEL_ID=<the model's id from --list>. Changing the model requires
re-indexing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

# Public commits and file hashes, not credentials; the pragmas keep the secret
# scanner from flagging them.
MODELS = {
    "all-MiniLM-L6-v2": {
        "model_id": "all-MiniLM-L6-v2-onnx",
        "repo": "sentence-transformers/all-MiniLM-L6-v2",  # Apache-2.0
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",  # pragma: allowlist secret
        "files": {
            # local name: (path in the Hugging Face repo, sha256)
            "model.onnx": (
                "onnx/model.onnx",
                "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452",  # pragma: allowlist secret
            ),
            "tokenizer.json": (
                "tokenizer.json",
                "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",  # pragma: allowlist secret
            ),
        },
        "profile": {"pooling": "mean", "max_length": 256},
    },
    "granite-embedding-small-english-r2-int8": {
        "model_id": "granite-embedding-small-english-r2-int8",
        "repo": "onnx-community/granite-embedding-small-english-r2-ONNX",  # Apache-2.0 (ibm-granite)
        "revision": "1dc7835ba0cb9c76a3618d0bf0c427c97671b3c8",  # pragma: allowlist secret
        "files": {
            "model_quantized.onnx": (
                "onnx/model_quantized.onnx",
                "a3fad524afc3f060216a8ddbb1ac89c9b6498fba8995b5718bde879076a2e9ba",  # pragma: allowlist secret
            ),
            "model_quantized.onnx_data": (
                "onnx/model_quantized.onnx_data",
                "1f4cf47e4adec7f7ae09db03d071ba8667e07f9a4203142c7efa8d37fe453597",  # pragma: allowlist secret
            ),
            "tokenizer.json": ("tokenizer.json", "feeb83348dcb033bc6b9d2e1f7906ca9eb2d122845000c9416d894d7c2927149"),  # pragma: allowlist secret
        },
        "profile": {"pooling": "cls", "max_length": 512, "onnx_file": "model_quantized.onnx"},
    },
    "granite-embedding-english-r2-int8": {
        "model_id": "granite-embedding-english-r2-int8",
        "repo": "onnx-community/granite-embedding-english-r2-ONNX",  # Apache-2.0 (ibm-granite)
        "revision": "2a49b9c076aa627b14bc528b36b67462808ccc23",  # pragma: allowlist secret
        "files": {
            "model_quantized.onnx": (
                "onnx/model_quantized.onnx",
                "0be6e9b09fb5f56dc4f58120b66d156218a6e26b8c5bc1362ec5676b61d8e5f3",  # pragma: allowlist secret
            ),
            "model_quantized.onnx_data": (
                "onnx/model_quantized.onnx_data",
                "97edcb23cacd7c46a766463c721f761f9360da03206f0676284cff81d7476c7d",  # pragma: allowlist secret
            ),
            "tokenizer.json": ("tokenizer.json", "feeb83348dcb033bc6b9d2e1f7906ca9eb2d122845000c9416d894d7c2927149"),  # pragma: allowlist secret
        },
        "profile": {"pooling": "cls", "max_length": 512, "onnx_file": "model_quantized.onnx"},
    },
    "granite-embedding-english-r2": {
        "model_id": "granite-embedding-english-r2",
        "repo": "onnx-community/granite-embedding-english-r2-ONNX",
        "revision": "2a49b9c076aa627b14bc528b36b67462808ccc23",  # pragma: allowlist secret
        "files": {
            "model.onnx": (
                "onnx/model.onnx",
                "ce8cf0b24f01ef35797265b7c392da8fc0a79e532ab6972a82e4c1a90f8466cb",  # pragma: allowlist secret
            ),
            "model.onnx_data": (
                "onnx/model.onnx_data",
                "8908e322c264f4ce0618efb5405a2b044541efc8711fa770f56ca9661898cb49",  # pragma: allowlist secret
            ),
            "tokenizer.json": ("tokenizer.json", "feeb83348dcb033bc6b9d2e1f7906ca9eb2d122845000c9416d894d7c2927149"),  # pragma: allowlist secret
        },
        "profile": {"pooling": "cls", "max_length": 512},
    },
    "jina-embeddings-v2-base-code-int8": {
        "model_id": "jina-embeddings-v2-base-code-int8",
        "repo": "jinaai/jina-embeddings-v2-base-code",  # Apache-2.0
        "revision": "516f4baf13dec4ddddda8631e019b5737c8bc250",  # pragma: allowlist secret
        "files": {
            "model_quantized.onnx": (
                "onnx/model_quantized.onnx",
                "ed45870251c9f0cf656e78aab0d37a23489066df8a222bb1c8caf8a45f2cb16d",  # pragma: allowlist secret
            ),
            "tokenizer.json": ("tokenizer.json", "b01c78a902aa4facb2f47f95449f48e2f7bbfea5d2472ee2f6ce92323c6f86e5"),  # pragma: allowlist secret
        },
        "profile": {"pooling": "mean", "max_length": 512, "onnx_file": "model_quantized.onnx"},
    },
}
DEFAULT = "all-MiniLM-L6-v2"
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(dest: Path, name: str = DEFAULT) -> None:
    spec = MODELS[name]
    dest.mkdir(parents=True, exist_ok=True)
    for local, (remote, expected) in spec["files"].items():
        target = dest / local
        if target.is_file() and expected and sha256(target) == expected:
            print(f"{local}: present")
            continue
        url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{remote}"
        partial = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as resp, partial.open("wb") as fh:
            while block := resp.read(1 << 20):
                fh.write(block)
        actual = sha256(partial)
        if expected is None:
            # Not stored in Git LFS, so Hugging Face publishes no hash: pin the one we got.
            partial.unlink()
            raise SystemExit(f"{local}: no pinned sha256; pin {actual} in MODELS[{name!r}] and rerun")
        if actual != expected:
            partial.unlink()
            raise SystemExit(f"{local}: sha256 mismatch (expected {expected}, got {actual})")
        partial.replace(target)
        print(f"{local}: downloaded ({target.stat().st_size} bytes)")
    profile = {"model_id": spec["model_id"], "repo": spec["repo"], "revision": spec["revision"], **spec["profile"]}
    (dest / "pharos_model.json").write_text(json.dumps(profile, indent=1) + "\n")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dest", nargs="?", help="target directory (default: models/<model>)")
    ap.add_argument("--model", default=DEFAULT, choices=sorted(MODELS))
    ap.add_argument("--list", action="store_true", help="list the pinned models")
    args = ap.parse_args(argv)
    if args.list:
        for key, spec in MODELS.items():
            print(f"{key:42s} model id {spec['model_id']:42s} {spec['repo']}@{spec['revision'][:12]}")
        return
    fetch(Path(args.dest) if args.dest else MODELS_DIR / args.model, args.model)


if __name__ == "__main__":
    main()
