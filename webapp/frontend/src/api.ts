export type Mode = 'chunks' | 'oracle';
export type Source = 'all' | 'session' | 'chat';
export const SOURCES: readonly Source[] = ['all', 'session', 'chat'];

export type PageItem = {
  slug: string;
  title: string;
  category: string | null;
  date: string | null;
  session_number: number | null;
};

export type WikiSection = {
  type: 'sessions' | 'characters' | 'npcs' | 'places';
  label: string;
  items: PageItem[];
};

export type Chunk = {
  chunk_id: string;
  source_type: 'session' | 'chat';
  source_file: string;
  date: string | null;
  session_id: string | null;
  n_chars: number;
  text: string;
  score: number;
};

export type AskResponse =
  | { mode: 'chunks'; chunks: Chunk[] }
  | { mode: 'oracle'; answer: string; chunks: Chunk[]; usage: { total_tokens?: number } | null };

export async function fetchWikiIndex(): Promise<WikiSection[]> {
  const r = await fetch('/api/wiki/index');
  if (!r.ok) throw new Error('No pude cargar el índice');
  return r.json();
}

export async function fetchPage(
  type: string,
  slug: string,
): Promise<{ type: string; slug: string; markdown: string }> {
  const r = await fetch(`/api/wiki/page/${type}/${slug}`);
  if (!r.ok) throw new Error('Página no encontrada');
  return r.json();
}

export async function askOracle(
  query: string,
  opts: { k?: number; mode: Mode; source?: Source } = { mode: 'chunks' },
): Promise<AskResponse> {
  const r = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, k: opts.k ?? 5, mode: opts.mode, source: opts.source ?? 'all' }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'Error en /api/ask');
  return data;
}

export async function fetchHealth(): Promise<{
  ok: boolean;
  n_chunks: number;
  embedding_model: string;
  chat_model: string;
  has_minimax_key: boolean;
}> {
  const r = await fetch('/api/health');
  return r.json();
}
