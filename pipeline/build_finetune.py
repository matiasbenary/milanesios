"""Paso 3.2 — Construir datasets de fine-tuning.

Tres outputs:

1. `dataset/finetune/narrator_pairs.jsonl`
   Pares (raw recap fragmentos de chat → versión Historia polished). Sólo para
   sesiones con `best_recap_match.jaccard >= 0.5`. Formato OpenAI Chat (con
   campo `messages: [system, user, assistant]`), también compatible con
   Anthropic Messages.

2. `dataset/finetune/narrator_corpus.jsonl`
   Sesiones de Historia plain text (una línea = una sesión, campo `text`).
   Sirve para fine-tune por continuación / "next-token" sin pares.

3. `dataset/finetune/character_corpus/{slug}.jsonl`
   Para cada PC, los chunks donde aparece. Sirve para fine-tunes/RAG
   por personaje.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATASET = BASE_DIR / "dataset"
SESS_DIR = BASE_DIR / "clean" / "sessions_denoised"
CHAT_JSONL = DATASET / "chat_denoised.jsonl"
MATCH_JSONL = DATASET / "session_chat_matches.jsonl"
CHUNKS_JSONL = DATASET / "chunks.jsonl"
ENT_JSONL = DATASET / "entities.jsonl"
MENT_JSONL = DATASET / "entity_mentions.jsonl"

OUT_DIR = DATASET / "finetune"
PAIRS_OUT = OUT_DIR / "narrator_pairs.jsonl"
CORPUS_OUT = OUT_DIR / "narrator_corpus.jsonl"
CHAR_DIR = OUT_DIR / "character_corpus"

MIN_JACCARD = 0.5

NARRATOR_SYSTEM_PROMPT = (
    "Sos el narrador de una campaña de D&D llamada \"Milanesios\". Tu tarea es "
    "transformar los apuntes crudos de una sesión (fragmentos pegados en Discord) "
    "en un resumen narrativo bien escrito, en tercera persona, en español rioplatense, "
    "manteniendo nombres propios, lugares y eventos. Respetá el orden de los hechos "
    "y el tono levemente humorístico/épico del grupo."
)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def strip_meta(text: str) -> str:
    """Saca frontmatter + título + bloques AUTOGEN para quedarse con narrativa pura."""
    m = re.match(r"^---\n.*?\n---\n(.*)$", text, re.DOTALL)
    body = m.group(1) if m else text
    body = re.sub(r"<!-- AUTOGEN-START -->.*?<!-- AUTOGEN-END -->", "", body, flags=re.DOTALL)
    body = re.sub(r"^# .+\n", "", body, count=1, flags=re.MULTILINE)
    return body.strip()


def build_narrator_pairs() -> int:
    """Para cada sesión con recap match alto, armar par (raw chat recap → historia)."""
    matches = load_jsonl(MATCH_JSONL)
    chat = load_jsonl(CHAT_JSONL)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    with PAIRS_OUT.open("w", encoding="utf-8") as f:
        for mt in matches:
            best = mt.get("best_recap_match")
            if not best or best["jaccard"] < MIN_JACCARD:
                continue
            # reconstruir el raw recap concatenando msgs linkeados a esta sesión
            sid = mt["session_id"]
            raw_msgs = [m for m in chat if m.get("linked_session_id") == sid and not m.get("noise")]
            raw_msgs.sort(key=lambda x: (x["date"], x["time"]))
            if not raw_msgs:
                continue
            raw_text = "\n\n".join(m["content"].strip() for m in raw_msgs if m["content"])
            if len(raw_text) < 200:
                continue

            # historia version
            sess_path = SESS_DIR / f"{sid}.md"
            if not sess_path.exists():
                continue
            polished = strip_meta(sess_path.read_text(encoding="utf-8"))
            if len(polished) < 200:
                continue

            record = {
                "session_id": sid,
                "session_number": mt.get("session_number"),
                "session_date": mt.get("session_date"),
                "jaccard": best["jaccard"],
                "messages": [
                    {"role": "system", "content": NARRATOR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Tomá estos apuntes crudos de la sesión y "
                            "reescribilos como un recap narrativo prolijo:\n\n"
                            f"{raw_text}"
                        ),
                    },
                    {"role": "assistant", "content": polished},
                ],
                # metadata útil para análisis
                "raw_n_chars": len(raw_text),
                "polished_n_chars": len(polished),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    print(f"[pairs] {n} pares → {PAIRS_OUT.relative_to(BASE_DIR)}")
    return n


def build_narrator_corpus() -> int:
    """Plain corpus: una línea por sesión."""
    n = 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with CORPUS_OUT.open("w", encoding="utf-8") as f:
        for src in sorted(SESS_DIR.glob("*.md")):
            text = strip_meta(src.read_text(encoding="utf-8"))
            if len(text) < 200:
                continue
            f.write(json.dumps({
                "id": src.stem,
                "text": text,
                "n_chars": len(text),
                "source": f"clean/sessions_denoised/{src.name}",
            }, ensure_ascii=False) + "\n")
            n += 1
    print(f"[corpus] {n} sesiones → {CORPUS_OUT.relative_to(BASE_DIR)}")
    return n


def build_character_corpus() -> int:
    """Por cada PC, juntar chunks donde aparece."""
    CHAR_DIR.mkdir(parents=True, exist_ok=True)
    for old in CHAR_DIR.glob("*.jsonl"):
        old.unlink()

    chunks = load_jsonl(CHUNKS_JSONL)
    entities = load_jsonl(ENT_JSONL)
    pcs = [e for e in entities if e["type"] == "pc"]

    n_files = 0
    for pc in pcs:
        name = pc["name"]
        # regex de nombre + aliases
        names = [name] + (pc.get("aliases") or [])
        pat = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE)
        hits = [c for c in chunks if pat.search(c["text"])]
        if not hits:
            continue
        out_path = CHAR_DIR / f"{pc['id']}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for c in hits:
                rec = {
                    "character": name,
                    "chunk_id": c["chunk_id"],
                    "source_type": c["source_type"],
                    "date": c.get("date"),
                    "session_id": c.get("session_id"),
                    "text": c["text"],
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        n_files += 1
        print(f"[char] {name:10s} → {out_path.relative_to(BASE_DIR)}  ({len(hits)} chunks)")
    return n_files


def main() -> None:
    n_pairs = build_narrator_pairs()
    n_corpus = build_narrator_corpus()
    n_chars = build_character_corpus()
    print(f"\n[summary] {n_pairs} pairs · {n_corpus} sesiones corpus · {n_chars} character files")


if __name__ == "__main__":
    main()
