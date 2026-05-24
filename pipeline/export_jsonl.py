"""Paso 1.5 — Export JSONL paralelo:

- `dataset/sessions.jsonl`  : una line por sesión (frontmatter + body).
- `dataset/entities.jsonl`  : una line por entidad (NPC o PC) con paths y categoría.

`dataset/chat.jsonl` ya lo genera `clean_chat.py`.
También escribe `dataset/schema.md`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

BASE_DIR = Path(__file__).resolve().parents[1]
SESS_DIR = BASE_DIR / "clean" / "sessions"
NPC_DIR = BASE_DIR / "clean" / "npcs"
DATASET = BASE_DIR / "dataset"
ENTITIES_YAML = BASE_DIR / "config" / "known_entities.yaml"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_md(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2).lstrip("\n")
    # quitar el "# Título" de la primera línea si está
    if body.startswith("# "):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.lstrip("\n")
    return fm, body


def export_sessions(out: Path) -> int:
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for path in sorted(SESS_DIR.glob("*.md")):
            fm, body = parse_md(path.read_text(encoding="utf-8"))
            record = {
                "id": path.stem,
                "session_number": fm.get("session_number"),
                "date": str(fm.get("date")) if fm.get("date") else None,
                "source": fm.get("source"),
                "raw_heading": fm.get("raw_heading"),
                "char_count": len(body),
                "body": body,
                "file": path.relative_to(BASE_DIR).as_posix(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    return n


def export_entities(out: Path) -> int:
    n = 0
    with out.open("w", encoding="utf-8") as f:
        # NPCs
        for path in sorted(NPC_DIR.glob("*.md")):
            fm, body = parse_md(path.read_text(encoding="utf-8"))
            record = {
                "id": path.stem,
                "name": fm.get("name"),
                "type": fm.get("type", "npc"),
                "category": fm.get("category"),
                "aliases": fm.get("aliases", []),
                "source": fm.get("source"),
                "from_wikilink": fm.get("from_wikilink", False),
                "stub": body.strip() in {"<!-- pendiente de completar -->", ""},
                "body": body.strip(),
                "file": path.relative_to(BASE_DIR).as_posix(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
        # PCs del YAML
        if ENTITIES_YAML.exists():
            cfg = yaml.safe_load(ENTITIES_YAML.read_text(encoding="utf-8")) or {}
            for pc in cfg.get("playable_characters", []) or []:
                record = {
                    "id": pc["slug"],
                    "name": pc["name"],
                    "type": "pc",
                    "category": "Personajes jugables",
                    "aliases": pc.get("aliases", []),
                    "source": "known_entities.yaml",
                    "from_wikilink": False,
                    "stub": True,
                    "body": "",
                    "player": pc.get("player"),
                    "file": None,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                n += 1
    return n


SCHEMA_DOC = """# Dataset schema

Todas las salidas son **JSON Lines** (`.jsonl`): un objeto JSON por línea, UTF-8.
Generadas por `pipeline/run_all.py`. No se commitean al repo (ver `.gitignore`).

## `chat.jsonl`
Una línea por mensaje de Discord. Generado por `clean_chat.py`.

| campo | tipo | descripción |
|---|---|---|
| `date` | str | `YYYY-MM-DD` (hora local del scraper) |
| `time` | str | `HH:MM:SS` |
| `author` | str | nombre visible en Discord (global_name o username) |
| `content` | str | cuerpo del mensaje, custom-emojis de Discord ya colapsados a `:nombre:` |
| `msg_id` | str \\| null | id snowflake de Discord |
| `edited_at` | str \\| null | ISO 8601 si el mensaje fue editado |
| `reply_to_author` | str \\| null | autor del mensaje citado (si es respuesta) |
| `reply_to_snippet` | str \\| null | primeras ~120 chars del mensaje citado |
| `attachments` | list[obj] | `{filename, path, kind}` con kind ∈ {image, file, missing} |
| `embeds` | list[obj] | `{title?, url?, desc?}` por embed |
| `type` | str | `chat` o `recap` (heurística Fase 1; refinable en Fase 2) |

## `sessions.jsonl`
Una línea por sesión extraída de `Historia Milanesios.md`. Generado por `export_jsonl.py`.

| campo | tipo | descripción |
|---|---|---|
| `id` | str | slug de archivo, p.ej. `sesion-39-2024-03-22` |
| `session_number` | int \\| null | número de sesión (null para la pre-sesión 38) |
| `date` | str | `YYYY-MM-DD` |
| `source` | str | siempre `historia_milanesios` por ahora |
| `raw_heading` | str | el heading original tal cual venía en el .md fuente |
| `char_count` | int | longitud del cuerpo (sin frontmatter ni título) |
| `body` | str | texto completo del recap |
| `file` | str | path relativo al .md (`clean/sessions/...`) |

## `entities.jsonl`
Una línea por NPC o PC. Generado por `export_jsonl.py`.

| campo | tipo | descripción |
|---|---|---|
| `id` | str | slug, p.ej. `niberath`, `aimee` |
| `name` | str | nombre canónico |
| `type` | str | `npc` o `pc` |
| `category` | str | sección original (Phandalin, Nómades, Personajes jugables…) |
| `aliases` | list[str] | nombres alternativos (a completar manualmente) |
| `source` | str | de dónde vino: `listado_npc` o `known_entities.yaml` |
| `from_wikilink` | bool | true si en el listado venía como `[[Nombre]]` |
| `stub` | bool | true si el cuerpo está vacío / placeholder |
| `body` | str | descripción libre |
| `player` | str | (sólo PCs) jugador que lo controla; `?` hasta completar |
| `file` | str \\| null | path al .md, o null para PCs sin stub aún |

## `entity_mentions.jsonl`
Conteo barato de menciones por entidad y archivo. Generado por `extract_entities.py`.

| campo | tipo | descripción |
|---|---|---|
| `entity` | str | nombre canónico |
| `slug` | str | id de entidad |
| `type` | str | `npc` o `pc` |
| `file` | str | path relativo del archivo donde apareció |
| `count` | int | cantidad de matches case-insensitive con word-boundary |

> **Limitación conocida**: no resuelve aliases ni co-referencias. `entity_candidates.jsonl`
> (Fase 2) ayuda a descubrir aliases pendientes.

---

# Fase 2 — Matching + descubrimiento

## `session_chat_matches.jsonl`
Una línea por sesión con sus candidatos de día(s) de chat y recap(s) duplicados.
Generado por `match_sessions.py`.

| campo | tipo | descripción |
|---|---|---|
| `session_id` | str | slug de la sesión |
| `session_number` | int \\| null | |
| `session_date` | str | `YYYY-MM-DD` |
| `candidate_chat_days` | list[obj] | top 5 days en ventana ±5d ordenados por jaccard desc |
| `recap_msg_matches` | list[obj] | top 5 grupos de recap con jaccard ≥ 0.15 |
| `best_recap_match` | obj \\| null | el de mayor jaccard, si existe |

Cada candidato lleva: `date`, `delta_days` (sólo days), `jaccard`, `n_msgs`, `file`,
y para recaps además `author`, `first_msg_id`.

## `chat_with_links.jsonl`
Copia de `chat.jsonl` con un campo extra. Generado por `match_sessions.py`.

| campo extra | tipo | descripción |
|---|---|---|
| `linked_session_id` | str \\| null | id de la sesión a la que pertenece el recap si jaccard ≥ 0.3 |

## `entity_candidates.jsonl`
Tokens capitalizados frecuentes que NO están en `known_entities.yaml` ni en
`clean/npcs/`. Generado por `discover_entities.py`. Sirven como semillas para
agregar manualmente como NPCs/aliases.

| campo | tipo | descripción |
|---|---|---|
| `candidate` | str | el token tal como aparece (con tildes) |
| `slug` | str | slug ASCII |
| `total_mentions` | int | apariciones totales en `clean/sessions/` + `clean/chat/` |
| `n_files` | int | en cuántos archivos distintos aparece |
| `sample_files` | list[str] | hasta 5 archivos donde aparece |

> **Filtro**: ≥ 5 menciones totales en ≥ 2 archivos, no en stoplist español, no en known entities.
> Sigue habiendo falsos positivos — el usuario debe revisar manualmente.

## `chat_denoised.jsonl`
Copia de `chat_with_links.jsonl` con flags de ruido. Generado por `denoise.py`.
Misma estructura + campos:

| campo extra | tipo | descripción |
|---|---|---|
| `noise` | bool | true si el mensaje fue clasificado como ruido (no narrativo) |
| `noise_reason` | str \\| null | etiqueta del filtro que lo descartó: `bot_author`, `scheduling_session`, `inspiration_award`, `dm_rules_meta`, `admin_request`, `dm_clarification`, `mention_only`, `url_only`, `media_link`, `short_reaction`, `emoji_only`, etc. |

Para chunkear el corpus narrativo se usan SÓLO los msgs con `noise=false`.

---

# Fase 3 — Corpus para IA

## `chunks.jsonl`
Corpus chunkeado para embeddings/RAG. Generado por `build_chunks.py`.
Target ~2400 chars (~600 tokens) con overlap 200 chars, cortes en `\\n\\n` cuando es posible.

| campo | tipo | descripción |
|---|---|---|
| `chunk_id` | str | id estable, p.ej. `sesion-39-2024-03-22-c0` o `chat-2024-04-19-c2` |
| `source_type` | str | `session` o `chat` |
| `source_file` | str | path al .md de origen (denoised) |
| `date` | str \\| null | `YYYY-MM-DD` |
| `session_id` | str \\| null | slug de la sesión si `source_type == session` |
| `session_number` | int \\| null | sólo sessions |
| `char_start` | int | offset en el archivo original |
| `char_end` | int | |
| `n_chars` | int | longitud del chunk |
| `text` | str | el contenido |

## `embeddings.npy` + `embeddings_meta.jsonl` + `embeddings_info.json`
Embeddings semánticos de `chunks.jsonl`. Generados por `embed_chunks.py`.

- `.npy`: array float32 shape (N, 384), L2-normalizado.
- `_meta.jsonl`: 1 line por chunk, mismo orden que el array.
- `_info.json`: `{model, dim, n_chunks, normalized}`.

Modelo por default: `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers, ~470MB, dim=384, soporta español).
Búsqueda: cosine similarity = dot product. Ver `rag.py`.

## `finetune/narrator_pairs.jsonl`
Pares (raw recap chat → versión Historia polished). Formato OpenAI Chat / Anthropic Messages.
Generado por `build_finetune.py`. Sólo para sesiones con `best_recap_match.jaccard >= 0.5`.

| campo | tipo | descripción |
|---|---|---|
| `session_id` | str | |
| `session_number` | int | |
| `session_date` | str | |
| `jaccard` | float | calidad del par |
| `messages` | list[obj] | `[{role: system, content}, {role: user, content}, {role: assistant, content}]` |
| `raw_n_chars` | int | |
| `polished_n_chars` | int | |

## `finetune/narrator_corpus.jsonl`
Sesiones de Historia en plain text para fine-tune por continuación (LM).

| campo | tipo |
|---|---|
| `id` | str |
| `text` | str |
| `n_chars` | int |
| `source` | str |

## `finetune/character_corpus/{slug}.jsonl`
Una carpeta con un .jsonl por PC. Cada .jsonl contiene los chunks donde
aparece ese personaje (regex name+aliases case-insensitive).

| campo | tipo |
|---|---|
| `character` | str |
| `chunk_id` | str |
| `source_type` | str |
| `date` | str |
| `session_id` | str \\| null |
| `text` | str |
"""


def main() -> None:
    DATASET.mkdir(parents=True, exist_ok=True)

    n_sess = export_sessions(DATASET / "sessions.jsonl")
    print(f"[sess] {n_sess} sesiones → dataset/sessions.jsonl")

    n_ent = export_entities(DATASET / "entities.jsonl")
    print(f"[ent ] {n_ent} entidades → dataset/entities.jsonl")

    (DATASET / "schema.md").write_text(SCHEMA_DOC, encoding="utf-8")
    print("[doc ] dataset/schema.md")


if __name__ == "__main__":
    main()
