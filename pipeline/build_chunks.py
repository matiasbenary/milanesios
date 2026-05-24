"""Paso 3.1 — Chunkear el corpus denoised para embeddings/RAG.

Lee:
- `clean/sessions_denoised/*.md` (frontmatter conservado, body limpio)
- `dataset/chat_denoised.jsonl` (mensajes no-ruido, líneas ya limpias)

Produce `dataset/chunks.jsonl` con un objeto por chunk:
  {
    "chunk_id": "ses-39-c0",
    "source_type": "session" | "chat",
    "source_file": "clean/sessions_denoised/sesion-39-2024-03-22.md",
    "date": "2024-03-22",
    "session_id": "sesion-39-2024-03-22" | null,
    "char_start": 0,
    "char_end": 2400,
    "n_chars": 2400,
    "text": "..."
  }

Estrategia de chunking:
- Target: ~2400 chars (~600 tokens) con overlap de 200 chars.
- Intenta cortar en `\n\n` (paragraph boundary) cercano al target.
- Para chat: concatena msgs del mismo día con encabezado `[HH:MM Autor]:` antes de chunkear.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

BASE_DIR = Path(__file__).resolve().parents[1]
SESS_DIR = BASE_DIR / "clean" / "sessions_denoised"
CHAT_JSONL = BASE_DIR / "dataset" / "chat_denoised.jsonl"
OUT = BASE_DIR / "dataset" / "chunks.jsonl"

TARGET_CHARS = 2400
OVERLAP = 200
MIN_CHUNK = 300  # no emit chunks más cortos que esto (excepto el último)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
AUTOGEN_RE = re.compile(r"<!-- AUTOGEN-START -->.*?<!-- AUTOGEN-END -->", re.DOTALL)
TITLE_RE = re.compile(r"^# .+\n", re.MULTILINE)


def strip_meta(text: str) -> tuple[dict, str]:
    """Saca frontmatter, título H1, y bloques autogen. Devuelve (fm_dict, body)."""
    fm: dict = {}
    m = FRONTMATTER_RE.match(text)
    if m:
        fm = yaml.safe_load(m.group(1)) or {}
        body = m.group(2)
    else:
        body = text
    body = AUTOGEN_RE.sub("", body)
    body = TITLE_RE.sub("", body, count=1)
    return fm, body.strip()


def chunk_text(text: str, target: int = TARGET_CHARS, overlap: int = OVERLAP) -> list[tuple[int, int, str]]:
    """Devuelve lista de (char_start, char_end, chunk_text)."""
    if len(text) <= target:
        return [(0, len(text), text)]
    chunks: list[tuple[int, int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end_ideal = start + target
        if end_ideal >= n:
            chunk = text[start:]
            if chunk.strip():
                chunks.append((start, n, chunk))
            break
        # buscar `\n\n` más cercano a end_ideal dentro de ±300 chars
        window_start = max(start + MIN_CHUNK, end_ideal - 300)
        window_end = min(n, end_ideal + 300)
        candidates = [
            m.start() for m in re.finditer(r"\n\n", text[window_start:window_end])
        ]
        if candidates:
            # tomar el más cercano a end_ideal
            local_ideal = end_ideal - window_start
            best = min(candidates, key=lambda c: abs(c - local_ideal))
            cut = window_start + best
        else:
            cut = end_ideal
        chunks.append((start, cut, text[start:cut]))
        # overlap: retroceder
        start = max(cut - overlap, start + MIN_CHUNK)
    return chunks


def process_sessions() -> list[dict]:
    out: list[dict] = []
    for src in sorted(SESS_DIR.glob("*.md")):
        text = src.read_text(encoding="utf-8")
        fm, body = strip_meta(text)
        sid = src.stem
        rel = src.relative_to(BASE_DIR).as_posix()
        date = str(fm.get("date")) if fm.get("date") else None
        for i, (s, e, t) in enumerate(chunk_text(body)):
            out.append({
                "chunk_id": f"{sid}-c{i}",
                "source_type": "session",
                "source_file": rel,
                "date": date,
                "session_id": sid,
                "session_number": fm.get("session_number"),
                "char_start": s,
                "char_end": e,
                "n_chars": len(t),
                "text": t.strip(),
            })
    return out


def process_chat() -> list[dict]:
    msgs = [json.loads(l) for l in CHAT_JSONL.read_text(encoding="utf-8").splitlines()]
    kept = [m for m in msgs if not m.get("noise")]
    # agrupar por día
    by_day: dict[str, list[dict]] = {}
    for m in kept:
        by_day.setdefault(m["date"], []).append(m)
    for d in by_day:
        by_day[d].sort(key=lambda x: x["time"])

    out: list[dict] = []
    for day, day_msgs in sorted(by_day.items()):
        # concatenar con encabezado por mensaje
        parts: list[str] = []
        for m in day_msgs:
            tag = f"[{m['time']} {m['author']}]"
            if m.get("type") == "recap":
                tag += " (RECAP)"
            if m.get("linked_session_id"):
                tag += f" → {m['linked_session_id']}"
            content = (m.get("content") or "").strip()
            if not content:
                continue
            parts.append(f"{tag}\n{content}")
        body = "\n\n".join(parts)
        if not body.strip():
            continue
        for i, (s, e, t) in enumerate(chunk_text(body)):
            out.append({
                "chunk_id": f"chat-{day}-c{i}",
                "source_type": "chat",
                "source_file": f"clean/chat_denoised/{day}.md",
                "date": day,
                "session_id": None,
                "char_start": s,
                "char_end": e,
                "n_chars": len(t),
                "text": t.strip(),
            })
    return out


def main() -> None:
    sess_chunks = process_sessions()
    chat_chunks = process_chat()
    all_chunks = sess_chunks + chat_chunks

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    n_sess_files = len(set(c["session_id"] for c in sess_chunks))
    n_chat_days = len(set(c["date"] for c in chat_chunks))
    print(f"[chunks] sesiones: {len(sess_chunks)} chunks de {n_sess_files} archivos")
    print(f"[chunks] chat:     {len(chat_chunks)} chunks de {n_chat_days} días")
    print(f"[chunks] total:    {len(all_chunks)} chunks → {OUT.relative_to(BASE_DIR)}")
    if all_chunks:
        sizes = [c["n_chars"] for c in all_chunks]
        print(f"[chunks] tamaño: min={min(sizes)} avg={sum(sizes)//len(sizes)} max={max(sizes)} chars")


if __name__ == "__main__":
    main()
