"""CLI de búsqueda semántica sobre el corpus.

Uso:
    python rag.py "qué pasó con Eru en la sesión 54"
    python rag.py "Aimee se enoja con Eru" --top 5
    python rag.py "el laberinto de Boreth" --source session

Carga `dataset/embeddings.npy` + `dataset/embeddings_meta.jsonl`, codifica la query
con el mismo modelo (paraphrase-multilingual-MiniLM-L12-v2), y devuelve los top-k
chunks por cosine similarity (= dot product porque están L2-normalizados).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATASET = BASE_DIR / "dataset"
EMB_NPY = DATASET / "embeddings.npy"
META_JSONL = DATASET / "embeddings_meta.jsonl"
INFO_JSON = DATASET / "embeddings_info.json"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", help="texto a buscar en el corpus")
    p.add_argument("--top", "-k", type=int, default=5, help="cantidad de resultados (default 5)")
    p.add_argument("--source", choices=["session", "chat", "all"], default="all",
                   help="filtrar por tipo de fuente")
    p.add_argument("--show-chars", type=int, default=400,
                   help="cantidad de chars del chunk a mostrar (default 400)")
    args = p.parse_args()

    if not EMB_NPY.exists():
        sys.exit(
            "No encontré embeddings.npy. Corré primero:\n"
            "    pip install sentence-transformers\n"
            "    python pipeline/embed_chunks.py"
        )

    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit("Falta sentence-transformers: pip install sentence-transformers")

    info = json.loads(INFO_JSON.read_text(encoding="utf-8"))
    model = SentenceTransformer(info["model"], device="cpu")

    emb = np.load(EMB_NPY)
    meta = [json.loads(l) for l in META_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(meta) == emb.shape[0], f"meta {len(meta)} vs emb {emb.shape[0]} mismatch"

    q = model.encode([args.query], normalize_embeddings=True, convert_to_numpy=True)[0]

    # cosine = dot product (ambos L2-normalizados)
    scores = emb @ q

    # filtrar por source si corresponde
    if args.source != "all":
        mask = np.array([m["source_type"] == args.source for m in meta], dtype=bool)
        scores = np.where(mask, scores, -1.0)

    top_idx = np.argsort(-scores)[: args.top]

    print(f"\nQuery: {args.query!r}\n{'=' * 70}")
    for rank, i in enumerate(top_idx, 1):
        m = meta[int(i)]
        s = float(scores[int(i)])
        text = m["text"][: args.show_chars]
        ell = "…" if len(m["text"]) > args.show_chars else ""
        print(f"\n[{rank}] score={s:.3f}  {m['source_type']:7s}  {m['date']}  {m['chunk_id']}")
        print(f"     {m['source_file']}")
        print(f"     {text}{ell}")


if __name__ == "__main__":
    main()
