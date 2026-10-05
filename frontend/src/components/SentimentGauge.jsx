// sentiment_score from the API is -1..+1 (P(positive) - P(negative)); mapped to 0-100 for display.
export default function SentimentGauge({ score }) {
  if (score === null || score === undefined) {
    return <div className="text-sm text-slate-400">No sentiment data yet.</div>
  }
  const pct = Math.round(((score + 1) / 2) * 100)
  const color = pct >= 66 ? '#16a34a' : pct >= 33 ? '#d97706' : '#dc2626'
  const label = pct >= 66 ? 'Positive' : pct >= 33 ? 'Mixed' : 'Negative'

  return (
    <div>
      <div className="flex items-end justify-between">
        <span className="text-3xl font-bold" style={{ color }}>
          {pct}
        </span>
        <span className="text-sm font-medium" style={{ color }}>
          {label}
        </span>
      </div>
      <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-slate-400">
        <span>0</span>
        <span>50</span>
        <span>100</span>
      </div>
    </div>
  )
}
