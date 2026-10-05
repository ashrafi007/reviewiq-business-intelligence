export default function StatCard({ label, value, sub, accent = 'slate', title }) {
  const accents = {
    slate: 'text-slate-900',
    green: 'text-emerald-600',
    red: 'text-red-600',
    amber: 'text-amber-600',
    indigo: 'text-indigo-600',
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" title={title}>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-3xl font-bold ${accents[accent]}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </div>
  )
}
