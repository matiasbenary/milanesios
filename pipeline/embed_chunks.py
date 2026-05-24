"""Paso 3.3 — Embeddings locales de los chunks.

Usa sentence-transformers con `BAAI/bge-m3` (~2.2GB, multilingüe, dim=1024,
soporta hasta 8192 tokens, CLS pooling + L2 norm).

Outputs:
- `dataset/embeddings.npy` — array (N, 1024) float32 con embeddings normalizados.
- `dataset/embeddings_meta.jsonl` — un objeto por chunk con {chunk_id, source_type,
  source_file, date, session_id, n_chars}, mismo orden que el array.
- `dataset/embeddings_info.json` — modelo usado, dim, total.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATASET = BASE_DIR / "dataset"
CHUNKS = DATASET / "chunks.jsonl"
EMB_OUT = DATASET / "embeddings.npy"
META_OUT = DATASET / "embeddings_meta.jsonl"
INFO_OUT = DATASET / "embeddings_info.json"

MODEL_NAME = "BAAI/bge-m3"


def main() -> None:
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        print(f"[skip] dependencias no disponibles ({exc}).")
        print(f"       instalar: pip install sentence-transformers")
        return

    if not CHUNKS.exists():
        print(f"[skip] {CHUNKS} no existe — corré build_chunks.py primero.")
        return

    chunks = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not chunks:
        print("[skip] no hay chunks.")
        return

    print(f"[load] cargando modelo {MODEL_NAME} (CPU)…")
    try:
        # forzar CPU: la GPU del sistema puede no tener kernel compatible
        model = SentenceTransformer(MODEL_NAME, device="cpu")
        # default 512 truncaría chunks que rondan ~700 tokens
        model.max_seq_length = 2048
    except Exception as exc:
        print(f"[error] no se pudo cargar el modelo: {exc}")
        print("       posibles causas: sin internet para bajar weights, o disco lleno.")
        sys.exit(1)

    texts = [c["text"] for c in chunks]
    print(f"[embed] {len(texts)} chunks (puede tardar varios minutos en CPU)…")
    embeddings = model.encode(
        texts,
        batch_size=8,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    embeddings = embeddings.astype("float32")

    DATASET.mkdir(parents=True, exist_ok=True)
    np.save(EMB_OUT, embeddings)

    with META_OUT.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps({
                "chunk_id": c["chunk_id"],
                "source_type": c["source_type"],
                "source_file": c["source_file"],
                "date": c.get("date"),
                "session_id": c.get("session_id"),
                "n_chars": c["n_chars"],
                # text is duplicated here so RAG consumers can show snippets without a second lookup
                "text": c["text"],
            }, ensure_ascii=False) + "\n")

    INFO_OUT.write_text(json.dumps({
        "model": MODEL_NAME,
        "dim": int(embeddings.shape[1]),
        "n_chunks": int(embeddings.shape[0]),
        "normalized": True,
    }, indent=2), encoding="utf-8")

    print(f"[out] {EMB_OUT.relative_to(BASE_DIR)}  shape={embeddings.shape}")
    print(f"[out] {META_OUT.relative_to(BASE_DIR)}")
    print(f"[out] {INFO_OUT.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
