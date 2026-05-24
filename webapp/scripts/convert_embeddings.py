"""Convierte dataset/embeddings.npy (numpy float32) a:

- webapp/backend/data/embeddings.bin — Float32Array raw, layout (N * dim) row-major.
- webapp/backend/data/chunks.json — metadata + texto, mismo orden que el .bin.
- webapp/backend/data/info.json — {model, dim, n_chunks}.

Node puede leer el .bin como Buffer y reinterpretarlo como Float32Array sin
necesidad de un parser de numpy.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[2]
EMB_IN = BASE / "dataset" / "embeddings.npy"
META_IN = BASE / "dataset" / "embeddings_meta.jsonl"
INFO_IN = BASE / "dataset" / "embeddings_info.json"

OUT_DIR = BASE / "webapp" / "backend" / "data"
EMB_OUT = OUT_DIR / "embeddings.bin"
CHUNKS_OUT = OUT_DIR / "chunks.json"
INFO_OUT = OUT_DIR / "info.json"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    emb = np.load(EMB_IN).astype(np.float32)
    assert emb.dtype == np.float32
    # asegurar contiguidad row-major
    emb = np.ascontiguousarray(emb)
    with EMB_OUT.open("wb") as f:
        emb.tofile(f)

    chunks = []
    with META_IN.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    assert len(chunks) == emb.shape[0], f"meta {len(chunks)} vs emb {emb.shape[0]}"
    CHUNKS_OUT.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")

    info = json.loads(INFO_IN.read_text(encoding="utf-8"))
    info["bytes_per_vector"] = int(emb.shape[1] * 4)
    info["total_bytes"] = int(emb.nbytes)
    INFO_OUT.write_text(json.dumps(info, indent=2), encoding="utf-8")

    print(f"[out] {EMB_OUT.relative_to(BASE)}  shape={emb.shape} dtype={emb.dtype} ({emb.nbytes:,} bytes)")
    print(f"[out] {CHUNKS_OUT.relative_to(BASE)}  {len(chunks)} chunks")
    print(f"[out] {INFO_OUT.relative_to(BASE)}  {info}")


if __name__ == "__main__":
    main()
