import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useBusinesses } from './context/BusinessContext'

const NAV_LINKS = [
  { to: '/', label: 'Overview', end: true },
  { to: '/reviews', label: 'Review Feed' },
  { to: '/competitors', label: 'Competitors' },
  { to: '/trends', label: 'Trends' },
  { to: '/chatbot', label: 'Chatbot' },
]

function BusinessSelector() {
  const { businesses, selectedId, setSelectedId, loading } = useBusinesses()

  if (loading) {
    return <div className="text-sm text-slate-400">Loading businesses…</div>
  }

  return (
    <select
      value={selectedId ?? ''}
      onChange={(e) => setSelectedId(Number(e.target.value))}
      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 sm:w-auto"
    >
      {businesses.map((b) => (
        <option key={b.id} value={b.id}>
          {b.name} ({b.category})
        </option>
      ))}
    </select>
  )
}

function NavLinks({ className, linkClassName, onNavigate }) {
  return (
    <nav className={className}>
      {NAV_LINKS.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            `${linkClassName} ${
              isActive
                ? 'bg-indigo-50 text-indigo-700'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`
          }
        >
          {link.label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function App() {
  const { error } = useBusinesses()
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:gap-4 sm:px-6 sm:py-4">
          <div className="flex min-w-0 items-center gap-4 sm:gap-8">
            <span className="shrink-0 text-lg font-bold tracking-tight text-indigo-600">ReviewIQ</span>
            <NavLinks
              className="hidden min-w-0 gap-1 overflow-x-auto sm:flex"
              linkClassName="shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition"
            />
          </div>

          <div className="hidden sm:block">
            <BusinessSelector />
          </div>

          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            className="rounded-md p-2 text-slate-600 hover:bg-slate-100 sm:hidden"
          >
            {menuOpen ? (
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M6 6 18 18M18 6 6 18" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M4 7h16M4 12h16M4 17h16" />
              </svg>
            )}
          </button>
        </div>

        {menuOpen && (
          <div className="border-t border-slate-200 px-4 py-3 sm:hidden">
            <NavLinks
              className="flex flex-col gap-1"
              linkClassName="rounded-md px-3 py-2 text-sm font-medium transition"
              onNavigate={() => setMenuOpen(false)}
            />
            <div className="mt-3">
              <BusinessSelector />
            </div>
          </div>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load businesses: {error}. Is the API running on port 8000?
          </div>
        ) : (
          <Outlet />
        )}
      </main>
    </div>
  )
}
