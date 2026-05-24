# Fase 3 — Corpus listo para IA

La pipeline (Fases 1+2+3) produce todos los artefactos necesarios para:

1. **RAG / búsqueda semántica** sobre el corpus completo de la campaña.
2. **Fine-tune de un narrador** estilo Niky/Dani (recap pulido a partir de apuntes crudos).
3. **Personajes conversacionales** por PC (corpus por personaje listo).

## Setup

```bash
# 1. Pipeline Fases 1+2+3 (rápido, ~4s, sin embeddings)
python pipeline/run_all.py

# 2. Embeddings locales (descarga ~470MB la primera vez)
pip install sentence-transformers  # ya está en .venv si seguiste los pasos
python pipeline/embed_chunks.py

# o todo junto:
python pipeline/run_all.py --with-embeddings
```

## RAG / búsqueda semántica

CLI mínimo en `rag.py`:

```bash
python rag.py "qué pasó con Eru y Aimee"
python rag.py "el laberinto de Boreth" --source session --top 5
python rag.py "la pelea contra el Aboleth" --top 3 --show-chars 500
```

Devuelve los top-k chunks por cosine similarity. Cada resultado incluye score, archivo fuente, fecha y un extracto.

**Cómo funciona internamente**

- `dataset/chunks.jsonl` — 860 chunks (~2400 chars c/u) de sesiones + chat denoised.
- `dataset/embeddings.npy` — array (860, 384) float32 L2-normalizado.
- `dataset/embeddings_meta.jsonl` — metadata gemela.
- Modelo: `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers).
- Búsqueda: brute-force dot product (no hace falta vectorstore para 860 chunks).

## Fine-tune

### a) Narrador (par raw → polished)

`dataset/finetune/narrator_pairs.jsonl` — 17 ejemplos en formato OpenAI Chat (compatible con Anthropic Messages).

```json
{
  "session_id": "sesion-39-2024-03-22",
  "jaccard": 0.999,
  "messages": [
    {"role": "system", "content": "Sos el narrador de una campaña de D&D..."},
    {"role": "user", "content": "Tomá estos apuntes crudos y reescribilos...\n\n[raw recap del chat]"},
    {"role": "assistant", "content": "[recap pulido del Historia]"}
  ]
}
```

> **Nota sobre tamaño**: 17 ejemplos es poco para fine-tune full. Sirve mejor para
> few-shot prompting o para una LoRA tipo "estilo Niky" con regularización fuerte.

### b) Corpus narrativo (LM continuation)

`dataset/finetune/narrator_corpus.jsonl` — 21 sesiones plain text, una por línea.
Útil para domain-adaptation por next-token prediction.

### c) Corpus por personaje

`dataset/finetune/character_corpus/{slug}.jsonl` — chunks donde aparece cada PC.

| PC | Chunks |
|---|---:|
| Alexia | 661 |
| Aimee | 628 |
| Osito | 472 |
| Sylvean | 407 |
| Yul | 388 |
| Fafy | 194 |
| Orion | 125 |

Cada line: `{character, chunk_id, source_type, date, session_id, text}`.

## Limitaciones conocidas

1. **PC↔jugador mapping incompleto.** `config/known_entities.yaml` tiene los slots con `?` — completar manualmente para distinguir habla in/out of character en Fase 4.
2. **Aliases no resueltos.** "Fafi" vs "Fafy", "Niverath" vs "Niberath", "Orión" vs "Orion" (este último ya está en SEED_PCS) aparecen como entidades separadas. Mejorar agregándolos al campo `aliases` del YAML.
3. **Detección de recap por contenido es heurística.** Se basa en mensaje largo que arranca con "Sesion N…". Sigue ~2/21 sesiones sin recap match alto. No es bloqueante para RAG; sí podría mejorar el dataset de pares narrador.
4. **GPU vs CPU.** El sistema tiene CUDA instalada pero kernel incompatible con la GPU física, así que `embed_chunks.py` y `rag.py` corren forzados a CPU. Cargar el modelo + embed 860 chunks toma ~25s.

## Reset / regenerar todo

```bash
rm -rf clean/sessions/* clean/chat/* clean/npcs/* clean/characters/* \
       clean/sessions_denoised clean/chat_denoised clean/_index.md \
       dataset/*.jsonl dataset/*.npy dataset/*.json dataset/schema.md dataset/finetune
python pipeline/run_all.py --with-embeddings
```

## Próximos pasos sugeridos (Fase 4)

- Completar `config/known_entities.yaml` (jugador↔PC, aliases).
- Revisar y promocionar candidatos de `dataset/entity_candidates.jsonl` a stubs.
- Reemplazar `extract_entities` por NER multilingüe (spaCy `es_core_news_lg` o LLM) para co-referencia.
- Filtrado de Fase 2.5 más agresivo: hay paráfrasis de reglas de D&D dentro de recaps que aún no se filtran (e.g. "Reglas del laberinto: …" en `sesion-pre`).
- RAG con re-ranking (BM25 + embeddings) para queries con nombres propios donde matchear textual gana.
