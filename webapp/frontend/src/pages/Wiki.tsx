import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { fetchPage, fetchWikiIndex, WikiSection } from '../api';

const FOLDER_TO_TYPE: Record<string, string> = {
  sessions: 'sessions',
  sessions_denoised: 'sessions',
  chat: 'sessions',
  chat_denoised: 'sessions',
  npcs: 'npcs',
  characters: 'characters',
  places: 'places',
};

function makeMarkdownComponents(externalNewTab: boolean): Components {
  return {
    a: ({ href, children }) => {
      if (href?.startsWith('/clean/')) {
        const [, , folder, name] = href.split('/');
        const stem = name?.replace(/\.md$/, '') ?? '';
        const t = FOLDER_TO_TYPE[folder];
        if (t) return <Link to={`/wiki/${t}/${stem}`}>{children}</Link>;
      }
      return externalNewTab
        ? <a href={href} target="_blank" rel="noreferrer">{children}</a>
        : <a href={href}>{children}</a>;
    },
  };
}

const PAGE_MD_COMPONENTS = makeMarkdownComponents(true);
const AUTOGEN_MD_COMPONENTS = makeMarkdownComponents(false);

export default function WikiPage() {
  const { type, slug } = useParams();
  const navigate = useNavigate();
  const [sections, setSections] = useState<WikiSection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<{ markdown: string } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchWikiIndex().then(setSections).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!type || !slug) {
      setPage(null);
      return;
    }
    setLoading(true);
    fetchPage(type, slug)
      .then(setPage)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [type, slug]);

  useEffect(() => {
    // si entran sin slug, redirige a la primera sesión disponible
    if (!type && sections) {
      const sess = sections.find((s) => s.type === 'sessions');
      const first = sess?.items[0];
      if (first) navigate(`/wiki/sessions/${first.slug}`, { replace: true });
    }
  }, [type, sections, navigate]);

  if (error) return <p className="p-6 text-wine-500">Error: {error}</p>;
  if (!sections) return <LoadingSeal label="Abriendo el códice…" />;

  return (
    <div className="max-w-6xl mx-auto px-6 py-6 grid grid-cols-1 md:grid-cols-[280px_1fr] gap-6">
      <aside className="space-y-6 max-h-[calc(100vh-180px)] overflow-y-auto pr-2">
        {sections.map((s) => (
          <Section key={s.type} section={s} activeSlug={slug} activeType={type} />
        ))}
      </aside>

      <article className="parchment p-8 md:p-12 min-h-[60vh]">
        <AnimatePresence mode="wait">
          {loading && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-ink-500 italic"
            >
              Desplegando pergamino…
            </motion.div>
          )}
          {!loading && page && (
            <motion.div
              key={`${type}/${slug}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.35, ease: 'easeOut' }}
              className="prose-arcane"
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={PAGE_MD_COMPONENTS}>
                {stripAutogen(page.markdown)}
              </ReactMarkdown>
              {hasAutogen(page.markdown) && (
                <AutogenBlock raw={extractAutogen(page.markdown)} />
              )}
            </motion.div>
          )}
          {!loading && !page && (
            <motion.div key="empty" className="text-ink-500 italic">
              Elegí una entrada del códice a la izquierda.
            </motion.div>
          )}
        </AnimatePresence>
      </article>
    </div>
  );
}

function Section({
  section,
  activeSlug,
  activeType,
}: {
  section: WikiSection;
  activeSlug?: string;
  activeType?: string;
}) {
  const [open, setOpen] = useState(true);
  if (!section.items.length) return null;
  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left flex items-center justify-between text-gold-500 font-display tracking-widest text-sm uppercase py-1 hover:text-gold-400"
      >
        <span>{section.label}</span>
        <span className="text-xs">{open ? '▾' : '▸'}</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ul
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-l border-gold-600/30 ml-2 mt-1"
          >
            {section.items.map((item) => {
              const isActive = activeType === section.type && activeSlug === item.slug;
              return (
                <li key={item.slug}>
                  <Link
                    to={`/wiki/${section.type}/${item.slug}`}
                    className={`block pl-3 py-1 text-sm font-body transition-colors ${
                      isActive
                        ? 'text-gold-400 bg-gold-500/10 border-l-2 border-gold-500 -ml-px'
                        : 'text-parchment-200/70 hover:text-parchment-100'
                    }`}
                  >
                    {item.title}
                    {item.date && (
                      <span className="block text-[10px] text-parchment-300/40 font-ui">
                        {item.date}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

function LoadingSeal({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-gold-400/70">
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 12, repeat: Infinity, ease: 'linear' }}
        className="text-5xl"
      >
        ✦
      </motion.div>
      <p className="mt-4 font-display tracking-widest text-sm">{label}</p>
    </div>
  );
}

// ─── helpers para el bloque AUTOGEN ──────────────────────────
const AUTOGEN_RE = /<!-- AUTOGEN-START -->([\s\S]*?)<!-- AUTOGEN-END -->/;
const FRONTMATTER_RE = /^---\n[\s\S]*?\n---\n/;

function stripAutogen(md: string): string {
  return md.replace(FRONTMATTER_RE, '').replace(AUTOGEN_RE, '').trim();
}
function hasAutogen(md: string): boolean {
  return AUTOGEN_RE.test(md);
}
function extractAutogen(md: string): string {
  const m = md.match(AUTOGEN_RE);
  return m ? m[1].trim() : '';
}

function AutogenBlock({ raw }: { raw: string }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.2 }}
      className="mt-8 pt-6 border-t-2 border-double border-gold-600/40"
    >
      <p className="font-display text-xs uppercase tracking-widest text-wine-700/70 mb-2">
        ✦ Anotaciones del archivo ✦
      </p>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={AUTOGEN_MD_COMPONENTS}>
        {raw}
      </ReactMarkdown>
    </motion.div>
  );
}
