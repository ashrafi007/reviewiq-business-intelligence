export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center py-16 text-sm text-slate-400">
      {label}
    </div>
  )
}

export function ErrorBox({ message }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      {message}
    </div>
  )
}
