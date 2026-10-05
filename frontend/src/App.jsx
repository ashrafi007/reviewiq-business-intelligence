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
      className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
    >
      {businesses.map((b) => (
        <option key={b.id} value={b.id}>
          {b.name} ({b.category})
        </option>
      ))}
    </select>
  )
}

export default function App() {
  const { error } = useBusinesses()

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:gap-4 sm:px-6 sm:py-4">
          <div className="flex min-w-0 items-center gap-4 sm:gap-8">
            <span className="shrink-0 text-lg font-bold tracking-tight text-indigo-600">ReviewIQ</span>
            <nav className="flex min-w-0 gap-1 overflow-x-auto">
              {NAV_LINKS.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.end}
                  className={({ isActive }) =>
                    `shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition ${
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
          </div>
          <BusinessSelector />
        </div>
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
