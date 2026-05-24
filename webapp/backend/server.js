// MilaWiki backend — Express + transformers.js (local embeddings) + MiniMax (chat).
// Sirve:
//   GET  /api/wiki/index                — listado de páginas
//   GET  /api/wiki/page/:type/:slug     — markdown crudo de una página
//   POST /api/ask  { query, k?, mode? } — top-k chunks por cosine; con mode=oracle, llama a MiniMax

import express from 'express';
import cors from 'cors';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';
import { pipeline } from '@xenova/transformers';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.join(__dirname, '.env') });

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const DATA_DIR = path.join(__dirname, 'data');
const CLEAN_DIR = path.join(REPO_ROOT, 'clean');

const PORT = parseInt(process.env.PORT || '3001', 10);
const ALLOWED_ORIGIN = process.env.ALLOWED_ORIGIN || 'http://localhost:5173';
const MINIMAX_API_KEY = process.env.MINIMAX_API_KEY || '';
const MINIMAX_GROUP_ID = process.env.MINIMAX_GROUP_ID || '';
const MINIMAX_BASE_URL = (process.env.MINIMAX_BASE_URL || 'https://api.minimaxi.chat/v1').replace(/\/$/, '');
const MINIMAX_CHAT_MODEL = process.env.MINIMAX_CHAT_MODEL || 'MiniMax-Text-01';

const [infoRaw, chunksRaw, embBuffer] = await Promise.all([
  fs.readFile(path.join(DATA_DIR, 'info.json'), 'utf-8'),
  fs.readFile(path.join(DATA_DIR, 'chunks.json'), 'utf-8'),
  fs.readFile(path.join(DATA_DIR, 'embeddings.bin')),
]);
const info = JSON.parse(infoRaw);
const chunks = JSON.parse(chunksRaw);
// Copy into a fresh ArrayBuffer: Node's Buffer pool can return non-4-byte-aligned
// byteOffsets, which would make `new Float32Array(buffer, offset, ...)` throw.
const embeddings = new Float32Array(
  embBuffer.buffer.slice(embBuffer.byteOffset, embBuffer.byteOffset + embBuffer.byteLength),
);
console.log(`[load] ${info.n_chunks} chunks, dim=${info.dim}, model=${info.model}`);

const EMB_MODEL_ID = 'Xenova/bge-m3';
console.log(`[embed] cargando ${EMB_MODEL_ID}…`);
const embedder = await pipeline('feature-extraction', EMB_MODEL_ID);
console.log('[embed] modelo listo');

async function embedQuery(text) {
  // bge-m3 expects CLS pooling + L2-normalize to match the Python-side embeddings.
  const out = await embedder(text, { pooling: 'cls', normalize: true });
  return new Float32Array(out.data);
}

function projectChunk(i, score) {
  const c = chunks[i];
  return {
    chunk_id: c.chunk_id,
    source_type: c.source_type,
    source_file: c.source_file,
    date: c.date ?? null,
    session_id: c.session_id ?? null,
    text: c.text,
    score: Number(score.toFixed(4)),
  };
}

function cosineTopK(queryVec, k = 5, filterFn = null) {
  const N = info.n_chunks;
  const D = info.dim;
  const pairs = [];
  for (let i = 0; i < N; i++) {
    if (filterFn && !filterFn(chunks[i])) continue;
    let s = 0;
    const off = i * D;
    for (let j = 0; j < D; j++) s += queryVec[j] * embeddings[off + j];
    pairs.push([i, s]);
  }
  pairs.sort((a, b) => b[1] - a[1]);
  return pairs.slice(0, k).map(([i, s]) => projectChunk(i, s));
}

async function listMdSafe(dir) {
  try {
    const files = await fs.readdir(dir);
    return files.filter(f => f.endsWith('.md') && !f.startsWith('_')).sort();
  } catch {
    return [];
  }
}

async function readFrontmatter(filePath) {
  const text = await fs.readFile(filePath, 'utf-8');
  const m = text.match(/^---\n([\s\S]*?)\n---\n/);
  if (!m) return {};
  const fm = {};
  for (const line of m[1].split('\n')) {
    const kv = line.match(/^([a-zA-Z_]+):\s*(.+)$/);
    if (!kv) continue;
    fm[kv[1]] = kv[2].trim().replace(/^(['"])(.*)\1$/, '$2');
  }
  return fm;
}

const SECTIONS = [
  { type: 'sessions',   dir: 'sessions',   label: 'Sesiones' },
  { type: 'characters', dir: 'characters', label: 'Personajes jugables' },
  { type: 'npcs',       dir: 'npcs',       label: 'NPCs' },
  { type: 'places',     dir: 'places',     label: 'Lugares' },
];
const VALID_TYPES = new Set(SECTIONS.map(s => s.type));

async function buildSectionItems(s) {
  const dir = path.join(CLEAN_DIR, s.dir);
  const files = await listMdSafe(dir);
  const items = await Promise.all(files.map(async f => {
    const slug = f.replace(/\.md$/, '');
    const fm = await readFrontmatter(path.join(dir, f));
    return {
      slug,
      title: fm.name || fm.title || slug,
      category: fm.category || null,
      date: fm.date || null,
      session_number: fm.session_number ? Number(fm.session_number) : null,
    };
  }));
  if (s.type === 'sessions') {
    items.sort((a, b) => (a.session_number ?? 999) - (b.session_number ?? 999));
  }
  return { type: s.type, label: s.label, items };
}

async function buildIndex() {
  return Promise.all(SECTIONS.map(buildSectionItems));
}

// 60s TTL — wiki content only changes when the pipeline reruns, so don't re-scan
// disk on every request. Failures invalidate the cache so the next call retries.
const INDEX_TTL_MS = 60_000;
let indexCache = { promise: null, expiresAt: 0 };
function getCachedIndex() {
  const now = Date.now();
  if (!indexCache.promise || now > indexCache.expiresAt) {
    const promise = buildIndex().catch(err => {
      if (indexCache.promise === promise) indexCache = { promise: null, expiresAt: 0 };
      throw err;
    });
    indexCache = { promise, expiresAt: now + INDEX_TTL_MS };
  }
  return indexCache.promise;
}

const ORACLE_SYSTEM = `Sos el Oráculo de la campaña de D&D "Milanesios". Respondés en español rioplatense, en tono evocador y conciso (3-6 párrafos cortos máximo). Te basás EXCLUSIVAMENTE en los fragmentos del corpus que te paso como contexto. Si la respuesta no está en el contexto, decilo claramente. Citá fechas o números de sesión cuando aparezcan en el contexto.`;

async function callMiniMaxChat(query, contextChunks) {
  if (!MINIMAX_API_KEY) {
    throw new Error('MINIMAX_API_KEY no configurada en .env');
  }
  const contextText = contextChunks
    .map((c, i) => {
      const tag = c.source_type === 'session'
        ? `[Sesión ${c.session_id || ''} ${c.date || ''}]`
        : `[Chat ${c.date || ''}]`;
      return `Fragmento ${i + 1} ${tag}:\n${c.text}`;
    })
    .join('\n\n---\n\n');

  const body = {
    model: MINIMAX_CHAT_MODEL,
    messages: [
      { role: 'system', content: ORACLE_SYSTEM },
      { role: 'user', content: `Pregunta: ${query}\n\nContexto del corpus:\n\n${contextText}\n\nRespondé la pregunta usando sólo el contexto. Citá las fechas/sesiones relevantes.` },
    ],
    temperature: 0.4,
    // MiniMax-M2 is a reasoning model — burns internal tokens before producing content,
    // so a higher ceiling is needed to leave room for the actual answer.
    max_tokens: 4000,
  };

  // GroupId is passed as query param, not header, per MiniMax docs.
  const url = `${MINIMAX_BASE_URL}/text/chatcompletion_v2${MINIMAX_GROUP_ID ? `?GroupId=${MINIMAX_GROUP_ID}` : ''}`;
  const r = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${MINIMAX_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok || data.base_resp?.status_code) {
    const msg = data.base_resp?.status_msg || data.error?.message || `HTTP ${r.status}`;
    throw new Error(`MiniMax error: ${msg}`);
  }
  const msg = data.choices?.[0]?.message || {};
  // Fallback for reasoning models (e.g. M2): when `content` is empty because the
  // model exhausted max_tokens on reasoning, surface `reasoning_content` instead.
  const content = msg.content || msg.reasoning_content || '';
  return { content, raw_usage: data.usage || null };
}

const app = express();
app.use(cors({ origin: ALLOWED_ORIGIN }));
app.use(express.json({ limit: '1mb' }));

app.get('/api/health', (_, res) => {
  res.json({
    ok: true,
    n_chunks: info.n_chunks,
    embedding_model: info.model,
    chat_model: MINIMAX_CHAT_MODEL,
    has_minimax_key: !!MINIMAX_API_KEY,
  });
});

app.get('/api/wiki/index', async (_, res) => {
  try {
    res.json(await getCachedIndex());
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

app.get('/api/wiki/page/:type/:slug', async (req, res) => {
  const { type, slug } = req.params;
  if (!VALID_TYPES.has(type)) return res.status(400).json({ error: 'invalid type' });
  if (!/^[a-zA-Z0-9\-_]+$/.test(slug)) return res.status(400).json({ error: 'invalid slug' });
  const filePath = path.join(CLEAN_DIR, type, `${slug}.md`);
  try {
    const text = await fs.readFile(filePath, 'utf-8');
    res.json({ type, slug, markdown: text });
  } catch (err) {
    res.status(404).json({ error: 'not found', detail: String(err) });
  }
});

const VALID_MODES = new Set(['chunks', 'oracle']);
// Mirror of `SOURCES` in webapp/frontend/src/api.ts — keep in sync.
const VALID_SOURCES = new Set(['all', 'session', 'chat']);

app.post('/api/ask', async (req, res) => {
  try {
    const { query, k = 5, mode = 'chunks', source = 'all' } = req.body || {};
    if (typeof query !== 'string' || !query.trim()) {
      return res.status(400).json({ error: 'query requerida' });
    }
    if (!VALID_MODES.has(mode)) {
      return res.status(400).json({ error: `invalid mode (allowed: ${[...VALID_MODES].join(', ')})` });
    }
    if (!VALID_SOURCES.has(source)) {
      return res.status(400).json({ error: `invalid source (allowed: ${[...VALID_SOURCES].join(', ')})` });
    }
    const qVec = await embedQuery(query);
    const filterFn = source === 'all' ? null : (c) => c.source_type === source;
    const topChunks = cosineTopK(qVec, Math.max(1, Math.min(20, Number(k) || 5)), filterFn);

    if (mode === 'oracle') {
      const llm = await callMiniMaxChat(query, topChunks);
      return res.json({
        mode: 'oracle',
        answer: llm.content,
        chunks: topChunks,
        usage: llm.raw_usage,
      });
    }

    return res.json({ mode: 'chunks', chunks: topChunks });
  } catch (err) {
    console.error('[ask error]', err);
    res.status(500).json({ error: String(err.message || err) });
  }
});

app.listen(PORT, () => {
  console.log(`[server] listening on http://localhost:${PORT}`);
  console.log(`[server] CORS origin: ${ALLOWED_ORIGIN}`);
});
