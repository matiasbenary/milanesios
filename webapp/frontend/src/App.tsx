import { NavLink, Outlet } from 'react-router-dom';

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-gold-600/40 bg-ink-900/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <DragonGlyph />
            <h1 className="font-display text-2xl text-gold-500 tracking-widest m-0">
              MilaWiki · El Códice
            </h1>
          </div>
          <nav className="flex gap-2">
            <NavLink to="/wiki">
              {({ isActive }) => (
                <span className="btn-arcane" data-active={isActive}>📜 Tomo</span>
              )}
            </NavLink>
            <NavLink to="/oracle">
              {({ isActive }) => (
                <span className="btn-arcane" data-active={isActive}>🔮 Oráculo</span>
              )}
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="text-center text-xs text-parchment-300/40 py-3">
        Forjado en hierro, pergamino y silicio · Campaña Milanesios
      </footer>
    </div>
  );
}

function DragonGlyph() {
  // SVG decorativo simple — un sello con un dragón estilizado
  return (
    <svg width="36" height="36" viewBox="0 0 64 64" className="text-gold-500">
      <circle cx="32" cy="32" r="30" fill="none" stroke="currentColor" strokeWidth="2" />
      <path
        d="M32 14 L36 26 L48 24 L40 32 L48 40 L36 38 L32 50 L28 38 L16 40 L24 32 L16 24 L28 26 Z"
        fill="currentColor"
        opacity="0.85"
      />
      <circle cx="32" cy="32" r="3" fill="#1c130a" />
    </svg>
  );
}
