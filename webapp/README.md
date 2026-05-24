# MilaWiki webapp · El Códice + El Oráculo

Frontend en React + Vite + Tailwind + Framer Motion (theme D&D estilo grimorio).
Backend en Node + Express con `@xenova/transformers` (mismo modelo que `rag.py`,
en ONNX) y MiniMax para el modo "Visión LLM" de la bola de cristal.

## Estructura

```
webapp/
├── backend/             ← Node + Express
│   ├── server.js
│   ├── package.json
│   ├── data/            ← generado: embeddings.bin + chunks.json + info.json
│   ├── .env.example
│   └── .env             ← creá vos con tus claves
├── frontend/            ← Vite + React + TS
│   ├── src/
│   │   ├── App.tsx              ← header con tabs
│   │   ├── pages/Wiki.tsx       ← códice (sidebar + parchment markdown)
│   │   └── pages/Oracle.tsx     ← bola de cristal + chat RAG
│   ├── index.html
│   ├── tailwind.config.js
│   └── vite.config.ts
└── scripts/
    └── convert_embeddings.py    ← reusa dataset/embeddings.npy
```

## Setup (primera vez)

```bash
# 1. Generar binario de embeddings legible por Node
.venv/bin/python webapp/scripts/convert_embeddings.py
# → webapp/backend/data/embeddings.bin + chunks.json + info.json

# 2. Backend
cd webapp/backend
cp .env.example .env
# editar .env con tu MINIMAX_API_KEY y MINIMAX_GROUP_ID
npm install
npm run dev        # http://localhost:3001

# 3. Frontend (otra terminal)
cd webapp/frontend
npm install
npm run dev        # http://localhost:5173
```

## Variables de entorno (`webapp/backend/.env`)

| Variable | Default | Descripción |
|---|---|---|
| `MINIMAX_API_KEY` | _(vacío)_ | Token Bearer. Sin esto el modo "Visión LLM" no funciona; los chunks RAG siguen andando. |
| `MINIMAX_GROUP_ID` | _(vacío)_ | Algunos endpoints lo piden como query param `GroupId`. |
| `MINIMAX_BASE_URL` | `https://api.minimaxi.chat/v1` | Cambialo a `https://api.minimax.chat/v1` si tu cuenta es china. |
| `MINIMAX_CHAT_MODEL` | `MiniMax-Text-01` | También aceptables: `MiniMax-M2`, `abab6.5s-chat`, `abab6.5-chat`. |
| `PORT` | `3001` | Puerto del backend. |
| `ALLOWED_ORIGIN` | `http://localhost:5173` | CORS. Cambiar si servís el frontend de otro origen. |

## Endpoints

| Método | Path | Body / params | Devuelve |
|---|---|---|---|
| GET | `/api/health` | — | `{ok, n_chunks, embedding_model, chat_model, has_minimax_key}` |
| GET | `/api/wiki/index` | — | array de secciones `{type, label, items}` |
| GET | `/api/wiki/page/:type/:slug` | type ∈ {sessions, characters, npcs, places} | `{type, slug, markdown}` |
| POST | `/api/ask` | `{query, k?=5, mode?='chunks', source?='all'}` | `chunks` mode: `{mode, chunks}`. `oracle` mode: `{mode, answer, chunks, usage}` |

## Theme D&D

- Fuentes: **Cinzel** (display, headings — estilo épico romano) + **Cormorant Garamond** (body — serif elegante).
- Paleta: pergamino (`#f5e8c8`), vino (`#7e2a2e`), oro (`#c9a44e`), hierro (`#1c130a`), oráculo (azules místicos para la bola).
- Pergamino: pseudo-elementos `::before`/`::after` con gradientes radiales para simular bordes quemados y textura.
- Bola de cristal: tres capas animadas con Framer Motion — halo blurreado, esfera con gradient radial y highlight, swirl interno con conic-gradient.

## Decisiones técnicas

- **Embeddings reusados**: `dataset/embeddings.npy` se convierte a `embeddings.bin` (Float32Array crudo). Node lo `mmap`-ea efectivamente vía `fs.readFile` + `new Float32Array(buffer.buffer)`. Cero parsing.
- **Query embedding en Node**: `@xenova/transformers` corre la versión ONNX del mismo modelo `Xenova/paraphrase-multilingual-MiniLM-L12-v2`. La primera vez baja ~50MB de weights ONNX a `~/.cache/`.
- **Búsqueda**: brute-force cosine sobre 865 vectores. Toma <5ms en CPU. No vale la pena un vectorstore.
- **MiniMax**: endpoint `/v1/text/chatcompletion_v2`, compatible OpenAI Chat. `GroupId` va como query param.

## Limitaciones conocidas

- Wiki sólo expone `clean/sessions/`, `clean/characters/`, `clean/npcs/`, `clean/places/`. El chat day-by-day no está como página individual (sólo como fuente RAG).
- Recargar `webapp/backend/data/` requiere correr `convert_embeddings.py` después de regenerar embeddings con `pipeline/embed_chunks.py`.
- Sin auth — no exponer a internet sin un reverse proxy + auth.
