"""Orquestador de la pipeline de procesamiento.

Por defecto corre Fase 1 + Fase 2 (rápido, ~3-5s). Con `--with-embeddings`
agrega Fase 3 (chunkear + embeddings + fine-tune datasets, ~30s).

Uso:
    python pipeline/run_all.py                  # Fase 1 + 2
    python pipeline/run_all.py --with-embeddings  # + Fase 3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import split_historia  # noqa: E402
import clean_chat  # noqa: E402
import build_stubs  # noqa: E402
import extract_entities  # noqa: E402
import export_jsonl  # noqa: E402
import match_sessions  # noqa: E402
import discover_entities  # noqa: E402
import build_wiki_index  # noqa: E402
import denoise  # noqa: E402
import build_chunks  # noqa: E402
import build_finetune  # noqa: E402
import embed_chunks  # noqa: E402

STEPS_CORE = [
    ("1.1 split_historia    ", split_historia.main),
    ("1.2 clean_chat        ", clean_chat.main),
    ("1.3 build_stubs       ", build_stubs.main),
    ("1.4 extract_entities  ", extract_entities.main),
    ("1.5 export_jsonl      ", export_jsonl.main),
    ("2.1 match_sessions    ", match_sessions.main),
    ("2.2 discover_entities ", discover_entities.main),
    ("2.3 build_wiki_index  ", build_wiki_index.main),
    ("2.5 denoise           ", denoise.main),
    ("3.1 build_chunks      ", build_chunks.main),
    ("3.2 build_finetune    ", build_finetune.main),
]

STEPS_EMBEDDINGS = [
    ("3.3 embed_chunks      ", embed_chunks.main),
]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--with-embeddings", action="store_true",
                   help="incluir paso 3.3 (descarga modelo ~470MB la primera vez)")
    args = p.parse_args()

    steps = list(STEPS_CORE)
    if args.with_embeddings:
        steps += STEPS_EMBEDDINGS

    start = time.time()
    for label, fn in steps:
        print(f"\n{'=' * 60}\n>>> {label}\n{'=' * 60}")
        t0 = time.time()
        fn()
        print(f"    ({time.time() - t0:.1f}s)")
    print(f"\n{'=' * 60}\nPipeline lista en {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
