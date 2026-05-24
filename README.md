# MilaWiki — Archivo conversable de la campaña Milanesios

Pipeline + webapp que toma el historial de Discord de una campaña de D&D
(canal `1024479912918269963`, server `1012910616446513275`) y la wiki Quartz
asociada, y produce:

- Un **códice navegable** (wiki React con sesiones, PCs, NPCs y lugares).
- Un **Oráculo** (RAG sobre el corpus completo: sesiones + chat, con modo LLM
  opcional vía MiniMax).
- Datasets de **fine-tuning** (narrador raw→polished, corpus por personaje).

Capturas: `wiki-screen.png`, `oracle-empty.png`, `oracle-result.png`.

---

## Arquitectura en 4 etapas

```
Discord API + Quartz wiki
        │
        ▼ scrape.py
messages/YYYY-MM-DD.md  +  images/
        │
        ▼ pipeline/run_all.py  (Fases 1+2+3)
clean/      ←  sesiones, chat, NPCs, PCs, places (todo .md con frontmatter)
dataset/    ←  *.jsonl normalizados + chunks + finetune/
        │
        ▼ pipeline/embed_chunks.py  (--with-embeddings)
dataset/embeddings.npy + embeddings_meta.jsonl
        │
        ▼ rag.py                         |   webapp/scripts/convert_embeddings.py
CLI de búsqueda semántica                ▼
                                webapp/backend/data/{embeddings.bin, chunks.json, info.json}
                                         │
                                         ▼  webapp/ (Node + Vite)
                                  El Códice + El Oráculo
```

---

## Setup rápido

```bash
# 1. dependencias Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. credenciales Discord
cp .env.example .env
# editar .env (ver sección "Scrape" abajo)

# 3. scrape del canal
python scrape.py

# 4. pipeline completa (con embeddings)
python pipeline/run_all.py --with-embeddings

# 5. webapp
.venv/bin/python webapp/scripts/convert_embeddings.py
( cd webapp/backend  && cp .env.example .env && npm install && npm run dev )  # :3001
( cd webapp/frontend && npm install && npm run dev )                          # :5173
```

---

## Estructura del repo

```
.
├── scrape.py                ← descarga historial Discord → messages/
├── messages/                ← un .md por día (output de scrape)
├── images/                  ← attachments descargados
├── quartz_scrape/           ← copia local de la wiki Quartz (Historia + NPCs)
├── pipeline/                ← Fases 1+2+3 (split, clean, match, embed…)
├── clean/                   ← corpus normalizado (sessions/, chat/, npcs/, characters/, places/)
├── config/known_entities.yaml ← seed PCs / aliases / mapping jugador↔PC
├── dataset/                 ← *.jsonl + embeddings.npy + finetune/
├── rag.py                   ← CLI de búsqueda semántica
├── webapp/
│   ├── backend/             ← Express + transformers.js + MiniMax
│   ├── frontend/            ← React + Vite + Tailwind + Framer Motion (theme grimorio)
│   └── scripts/             ← convert_embeddings.py (npy → bin)
├── README.md                ← este archivo
├── FASE3.md                 ← detalles de RAG + fine-tune
└── webapp/README.md         ← detalles de la webapp
```

---

## 1. Scrape (`scrape.py`)

Descarga **todo** el historial del canal vía REST API y archiva:

- `messages/YYYY-MM-DD.md` — un markdown por día (hora local).
- `images/YYYY-MM-DD/<msg_id>_<att_id>_<filename>` — adjuntos.

### Token (en `.env`)

| Opción | Cómo conseguirlo | TOS |
|---|---|---|
| **Bot** (recomendado) | https://discord.com/developers/applications → Bot → token. Activar `MESSAGE CONTENT INTENT`. Invitar al server con `View Channel` + `Read Message History`. | ✅ |
| **User token** (selfbot) | DevTools → Network → header `Authorization`. | ❌ riesgo de baneo |

```
DISCORD_TOKEN=<token>
TOKEN_TYPE=bot                 # o "user"
MAX_MESSAGES=0                 # 0 = todo el historial
```

### Notas

- Pagina con `before` de a 100 msgs. Respeta `429 retry_after`.
- Re-ejecutar es seguro: no redescarga adjuntos que ya existen, reescribe los `.md`.
- Mensajes borrados antes del scrape no se pueden recuperar — la API no los devuelve.
- Adjuntos viejos pueden dar 404 si Discord invalidó la URL de CDN.

---

## 2. Pipeline (`pipeline/run_all.py`)

Orquesta 11 pasos. Por defecto Fases 1+2 (~3-5s). Con `--with-embeddings` agrega
Fase 3 (~30s, descarga modelo ~2.2GB la primera vez).

```bash
python pipeline/run_all.py                  # 1 + 2
python pipeline/run_all.py --with-embeddings  # 1 + 2 + 3
```

### Fase 1 — Limpieza

| Paso | Script | Output |
|---|---|---|
| 1.1 | `split_historia.py` | Splittea `quartz_scrape/.../Historia Milanesios.md` → `clean/sessions/sesion-NN-YYYY-MM-DD.md` |
| 1.2 | `clean_chat.py` | Parsea `messages/*.md` → `clean/chat/YYYY-MM-DD.md` + `dataset/chat.jsonl` |
| 1.3 | `build_stubs.py` | Genera `clean/npcs/{slug}.md` + seed `config/known_entities.yaml` |
| 1.4 | `extract_entities.py` | Cuenta menciones exactas → `dataset/entity_mentions.jsonl` |
| 1.5 | `export_jsonl.py` | `dataset/sessions.jsonl` + `dataset/entities.jsonl` + `dataset/schema.md` |

### Fase 2 — Matching & wiki

| Paso | Script | Output |
|---|---|---|
| 2.1 | `match_sessions.py` | Sesiones ↔ recaps del chat por Jaccard → `session_chat_matches.jsonl` + `chat_with_links.jsonl` |
| 2.2 | `discover_entities.py` | Candidatos a entidades nuevas → `entity_candidates.jsonl` |
| 2.3 | `build_wiki_index.py` | `clean/_index.md` + secciones `<!-- AUTOGEN -->` en sesiones/NPCs/PCs |
| 2.5 | `denoise.py` | Filtra ruido (bots, scheduling, reacciones) → `clean/{sessions,chat}_denoised/` + `chat_denoised.jsonl` |

### Fase 3 — Embeddings + datasets

| Paso | Script | Output |
|---|---|---|
| 3.1 | `build_chunks.py` | Chunks ~2400 chars con overlap 200 → `dataset/chunks.jsonl` |
| 3.2 | `build_finetune.py` | `narrator_pairs.jsonl`, `narrator_corpus.jsonl`, `character_corpus/{slug}.jsonl` |
| 3.3 | `embed_chunks.py` | `BAAI/bge-m3` (1024-dim, CLS + L2) → `dataset/embeddings.npy` + `embeddings_meta.jsonl` |

> Las secciones `<!-- AUTOGEN-START --> ... <!-- AUTOGEN-END -->` dentro de los
> `.md` se regeneran en cada corrida — no editar a mano.

---

## 3. RAG CLI (`rag.py`)

Búsqueda semántica brute-force sobre los ~860 chunks.

```bash
python rag.py "qué pasó con Eru y Aimee"
python rag.py "el laberinto de Boreth" --source session --top 5
python rag.py "la pelea contra el Aboleth" --top 3 --show-chars 500
```

Devuelve top-k por cosine similarity (= dot product, ya están L2-normalizados).
Detalle completo y limitaciones en [`FASE3.md`](./FASE3.md).

---

## 4. Webapp (`webapp/`)

Dos pantallas con theme D&D estilo grimorio (Cinzel + Cormorant Garamond,
pergamino + vino + oro, bola de cristal animada con Framer Motion).

- **El Códice** (`/wiki/...`) — sidebar navegable de sesiones / PCs / NPCs / lugares.
  Renderiza markdown con cross-links automáticos (`/clean/...` → ruta de wiki).
- **El Oráculo** (`/oracle`) — input de consulta + modo `chunks` (top-k crudo)
  o `oracle` (LLM MiniMax sobre los chunks como contexto). Filtros por fuente
  (`all` / `session` / `chat`).

### Cómo corre

```bash
# (una sola vez, después de cada regeneración de embeddings)
.venv/bin/python webapp/scripts/convert_embeddings.py
#  → webapp/backend/data/{embeddings.bin, chunks.json, info.json}

cd webapp/backend && cp .env.example .env && npm install && npm run dev   # :3001
cd webapp/frontend && npm install && npm run dev                          # :5173
```

### Endpoints

| Método | Path | Devuelve |
|---|---|---|
| GET | `/api/health` | `{ok, n_chunks, embedding_model, chat_model, has_minimax_key}` |
| GET | `/api/wiki/index` | Secciones `{type, label, items[]}` |
| GET | `/api/wiki/page/:type/:slug` | `{type, slug, markdown}` |
| POST | `/api/ask` `{query, k?, mode?, source?}` | `chunks`: `{mode, chunks}` / `oracle`: `{mode, answer, chunks, usage}` |

Variables de entorno y decisiones técnicas (embeddings reusados, ONNX en Node,
brute-force cosine, formato MiniMax) en [`webapp/README.md`](./webapp/README.md).

---

## Reset / regenerar todo

```bash
# corpus + embeddings + datasets
rm -rf clean/sessions/* clean/chat/* clean/npcs/* clean/characters/* \
       clean/sessions_denoised clean/chat_denoised clean/_index.md \
       dataset/*.jsonl dataset/*.npy dataset/*.json dataset/schema.md dataset/finetune
python pipeline/run_all.py --with-embeddings

# webapp (después de regenerar embeddings)
.venv/bin/python webapp/scripts/convert_embeddings.py
```

Para volver a scrapear desde cero (¡borra el historial local!):

```bash
rm -rf messages images
python scrape.py
```

---

## Limitaciones conocidas

- **PC↔jugador mapping incompleto** en `config/known_entities.yaml` — completar
  los `?` para distinguir habla in/out of character.
- **Aliases sin resolver**: `Fafi`↔`Fafy`, `Niverath`↔`Niberath` aparecen como
  entidades separadas — agregar al campo `aliases` del YAML.
- **Detección de recap heurística** (mensaje largo que arranca con "Sesion N…").
  ~2/21 sesiones siguen sin match alto; no bloquea RAG.
- **CPU only**: la GPU del host tiene CUDA pero kernel incompatible. `embed_chunks.py`
  y `rag.py` corren forzados a CPU; primer arranque ~25s.
- **Sin auth** en la webapp — no exponer a internet sin reverse proxy + auth.
- El chat day-by-day no tiene página individual en la wiki (sólo aparece como
  fuente del Oráculo).

---

## Próximos pasos sugeridos

- Completar `config/known_entities.yaml` (jugador↔PC, aliases).
- Promocionar candidatos de `dataset/entity_candidates.jsonl` a stubs reales.
- Reemplazar `extract_entities` por NER multilingüe (spaCy `es_core_news_lg` o LLM)
  con co-referencia.
- Filtrado Fase 2.5 más agresivo: hay paráfrasis de reglas dentro de recaps
  (e.g. "Reglas del laberinto: …").
- RAG con re-ranking (BM25 + embeddings) para queries con muchos nombres propios.

---

## Docs detallados

- [`FASE3.md`](./FASE3.md) — RAG, fine-tune datasets, modelo de embeddings, métricas.
- [`webapp/README.md`](./webapp/README.md) — webapp: theme, endpoints, decisiones técnicas, env vars.
