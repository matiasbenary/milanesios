import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Link } from 'react-router-dom';
import { askOracle, AskResponse, Chunk, fetchHealth, Mode, Source } from '../api';

export default function OraclePage() {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<Mode>('chunks');
  const [source, setSource] = useState<Source>('all');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasKey, setHasKey] = useState(false);

  useEffect(() => {
    fetchHealth().then((h) => setHasKey(h.has_minimax_key));
  }, []);

  const ask = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await askOracle(query, { mode, source, k: 6 });
      setResult(r);
    } catch (e: any) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex flex-col items-center mb-6">
        <CrystalBall loading={loading} active={!!result || loading} />
        <p className="mt-4 font-display tracking-widest text-gold-500 text-sm">
          EL ORÁCULO DE MILANESIOS
        </p>
        <p className="text-parchment-200/60 text-sm italic font-body">
          Preguntá sobre cualquier evento, personaje, lugar o sesión.
        </p>
      </div>

      <div className="flex flex-col gap-3 mb-4">
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && ask()}
            placeholder="¿Qué le pasó a Finrod? ¿Por qué Aimee se enojó con Eru?"
            className="flex-1 px-4 py-3 bg-ink-700/80 border border-gold-600/40 rounded-sm text-parchment-100 placeholder-parchment-300/30 font-body text-lg focus:outline-none focus:border-gold-500"
          />
          <button onClick={ask} disabled={loading} className="btn-arcane">
            {loading ? 'Consultando…' : 'Consultar 🔮'}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-parchment-300/60 uppercase tracking-widest text-xs font-display">
              Modo
            </span>
            <ModeToggle mode={mode} setMode={setMode} hasKey={hasKey} />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-parchment-300/60 uppercase tracking-widest text-xs font-display">
              Fuente
            </span>
            <SourceToggle source={source} setSource={setSource} />
          </div>
          {mode === 'oracle' && !hasKey && (
            <span className="text-wine-500 text-xs italic">
              ⚠ Falta MINIMAX_API_KEY en backend/.env
            </span>
          )}
        </div>
      </div>

      <AnimatePresence mode="wait">
        {error && (
          <motion.div
            key="err"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="parchment p-4 text-wine-700"
          >
            ⚠ {error}
          </motion.div>
        )}
        {result && (
          <motion.div
            key="res"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="space-y-6"
          >
            {result.mode === 'oracle' && (
              <div className="parchment p-8">
                <h2 className="font-display text-wine-700 text-2xl mb-3">
                  ✦ La visión ✦
                </h2>
                <div className="prose-arcane">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.answer}</ReactMarkdown>
                </div>
              </div>
            )}
            <div>
              <h3 className="font-display text-gold-500 tracking-widest text-sm mb-3 uppercase">
                Fragmentos consultados
              </h3>
              <div className="space-y-3">
                {result.chunks.map((c, i) => (
                  <ChunkCard key={c.chunk_id} chunk={c} rank={i + 1} />
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function CrystalBall({ loading, active }: { loading: boolean; active: boolean }) {
  return (
    <div className="relative w-48 h-48 flex items-center justify-center">
      {/* base de hierro */}
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-32 h-6 bg-gradient-to-b from-ink-700 to-ink-900 rounded-full shadow-lg border-t border-gold-600/30" />
      {/* halo */}
      <motion.div
        animate={
          loading
            ? { scale: [1, 1.15, 1], opacity: [0.5, 0.8, 0.5] }
            : { scale: 1, opacity: active ? 0.4 : 0.2 }
        }
        transition={
          loading
            ? { duration: 1.6, repeat: Infinity, ease: 'easeInOut' }
            : { duration: 0.5 }
        }
        className="absolute inset-0 rounded-full bg-oracle-400 blur-3xl"
        style={{ filter: 'blur(40px)' }}
      />
      {/* esfera */}
      <motion.div
        animate={loading ? { rotate: 360 } : { rotate: 0 }}
        transition={
          loading
            ? { duration: 8, repeat: Infinity, ease: 'linear' }
            : { duration: 0.5 }
        }
        className="relative w-36 h-36 rounded-full"
        style={{
          background:
            'radial-gradient(circle at 35% 30%, rgba(255,255,255,0.6) 0%, rgba(150,180,240,0.4) 18%, rgba(60,80,180,0.6) 50%, rgba(20,15,60,0.95) 90%)',
          boxShadow:
            '0 0 60px 10px rgba(120,100,220,0.5), inset 0 0 60px rgba(180,200,255,0.3), inset 5px 8px 20px rgba(255,255,255,0.4)',
        }}
      >
        {/* swirl interno */}
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 24, repeat: Infinity, ease: 'linear' }}
          className="absolute inset-2 rounded-full"
          style={{
            background:
              'conic-gradient(from 0deg, transparent, rgba(255,220,150,0.15), transparent, rgba(180,160,255,0.2), transparent)',
            mixBlendMode: 'screen',
          }}
        />
        {/* glow “mágico” cuando está cargando */}
        {loading && (
          <motion.div
            animate={{ opacity: [0.2, 0.9, 0.2] }}
            transition={{ duration: 1.4, repeat: Infinity }}
            className="absolute inset-0 rounded-full"
            style={{
              background:
                'radial-gradient(circle at 50% 50%, rgba(255,230,160,0.5) 0%, transparent 60%)',
            }}
          />
        )}
        {/* highlight */}
        <div
          className="absolute top-3 left-6 w-12 h-8 rounded-full opacity-60"
          style={{ background: 'radial-gradient(ellipse, rgba(255,255,255,0.9), transparent)' }}
        />
      </motion.div>
    </div>
  );
}

function ModeToggle({
  mode,
  setMode,
  hasKey,
}: {
  mode: Mode;
  setMode: (m: Mode) => void;
  hasKey: boolean;
}) {
  return (
    <div className="inline-flex rounded-sm overflow-hidden border border-gold-600/40">
      <button
        onClick={() => setMode('chunks')}
        className={`px-3 py-1.5 font-display text-xs uppercase tracking-wider ${
          mode === 'chunks'
            ? 'bg-gold-500 text-ink-900'
            : 'bg-ink-700 text-parchment-200/70 hover:text-parchment-100'
        }`}
      >
        Fragmentos
      </button>
      <button
        onClick={() => setMode('oracle')}
        title={!hasKey ? 'Necesita MINIMAX_API_KEY en backend/.env' : ''}
        className={`px-3 py-1.5 font-display text-xs uppercase tracking-wider ${
          mode === 'oracle'
            ? 'bg-oracle-600 text-parchment-50'
            : 'bg-ink-700 text-parchment-200/70 hover:text-parchment-100'
        }`}
      >
        Visión LLM
      </button>
    </div>
  );
}

function SourceToggle({
  source,
  setSource,
}: {
  source: Source;
  setSource: (s: Source) => void;
}) {
  const opts: Array<{ v: Source; label: string }> = [
    { v: 'all', label: 'Todo' },
    { v: 'session', label: 'Historia' },
    { v: 'chat', label: 'Chat' },
  ];
  return (
    <div className="inline-flex rounded-sm overflow-hidden border border-gold-600/40">
      {opts.map((o) => (
        <button
          key={o.v}
          onClick={() => setSource(o.v)}
          className={`px-3 py-1.5 font-display text-xs uppercase tracking-wider ${
            source === o.v
              ? 'bg-gold-500 text-ink-900'
              : 'bg-ink-700 text-parchment-200/70 hover:text-parchment-100'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ChunkCard({ chunk, rank }: { chunk: Chunk; rank: number }) {
  const linkable =
    chunk.source_type === 'session' && chunk.session_id ? (
      <Link
        to={`/wiki/sessions/${chunk.session_id}`}
        className="text-gold-400 hover:text-gold-500 text-xs font-ui"
      >
        Ver en el tomo →
      </Link>
    ) : null;

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: rank * 0.05 }}
      className="parchment p-5"
    >
      <div className="flex items-center justify-between mb-2 text-xs font-ui">
        <span className="font-display text-wine-700 tracking-widest uppercase">
          #{rank} · {chunk.source_type === 'session' ? 'Historia' : 'Chat'}
          {chunk.date ? ` · ${chunk.date}` : ''}
        </span>
        <span className="text-ink-500/60">score {chunk.score}</span>
      </div>
      <p className="prose-arcane">
        <span className="whitespace-pre-wrap">{chunk.text.slice(0, 500)}</span>
        {chunk.text.length > 500 ? '…' : ''}
      </p>
      {linkable && <div className="mt-2">{linkable}</div>}
    </motion.div>
  );
}
