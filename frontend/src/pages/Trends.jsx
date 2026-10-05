import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useBusinesses } from '../context/BusinessContext'
import { getTrends } from '../api'
import { Loading, ErrorBox } from '../components/Loading'

function formatWeek(week) {
  return typeof week === 'string' ? week.slice(0, 10) : week
}

function heatColor(count, maxCount) {
  if (!count) return '#f1f5f9'
  const intensity = Math.min(1, count / maxCount)
  const alpha = 0.15 + intensity * 0.65
  return `rgba(99, 102, 241, ${alpha.toFixed(2)})`
}

export default function Trends() {
  const { selectedId } = useBusinesses()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    getTrends(selectedId)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selectedId])

  if (!selectedId) return null
  if (loading) return <Loading label="Loading trends…" />
  if (error) return <ErrorBox message={error} />
  if (!data) return null

  const { weekly_stats, topic_trends, forecast, day_of_week } = data

  const ratingChartData = [
    ...weekly_stats.map((w) => ({ week: w.week, rating: w.avg_rating })),
    ...forecast.map((f) => ({ week: f.week, forecast: f.yhat, forecast_lower: f.yhat_lower, forecast_upper: f.yhat_upper })),
  ]

  const maxDowCount = Math.max(1, ...day_of_week.map((d) => d.count))

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Trends</h1>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Weekly Sentiment Trend</h2>
        {weekly_stats.length === 0 ? (
          <div className="text-sm text-slate-400">Not enough history yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={weekly_stats}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="week" tick={{ fontSize: 11 }} tickFormatter={formatWeek} />
              <YAxis domain={[-1, 1]} />
              <Tooltip />
              <Line type="monotone" dataKey="avg_sentiment" name="Avg sentiment" stroke="#10b981" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Rating Trend + 4-Week Forecast</h2>
        {ratingChartData.length === 0 ? (
          <div className="text-sm text-slate-400">Not enough history yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={ratingChartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="week" tick={{ fontSize: 11 }} tickFormatter={formatWeek} />
              <YAxis domain={[1, 5]} allowDataOverflow />
              <Tooltip labelFormatter={formatWeek} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="rating" name="Actual rating" stroke="#6366f1" dot={false} strokeWidth={2} connectNulls />
              <Line type="monotone" dataKey="forecast_upper" name="Forecast upper" stroke="#f59e0b" strokeDasharray="2 2" dot={false} strokeWidth={1} connectNulls />
              <Line type="monotone" dataKey="forecast" name="Forecast" stroke="#f59e0b" strokeDasharray="5 5" dot={false} strokeWidth={2} connectNulls />
              <Line type="monotone" dataKey="forecast_lower" name="Forecast lower" stroke="#f59e0b" strokeDasharray="2 2" dot={false} strokeWidth={1} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Topic Trends (last 30 vs. prior 30 days)</h2>
        {topic_trends.length === 0 ? (
          <div className="text-sm text-slate-400">Not enough recent activity to compare.</div>
        ) : (
          <div className="space-y-1.5">
            {topic_trends.slice(0, 8).map((t) => (
              <div key={t.topic_label} className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm hover:bg-slate-50">
                <span className="text-slate-700">{t.topic_label}</span>
                <span className="flex items-center gap-2 text-slate-500">
                  <span>{t.last_month} → {t.this_month} mentions</span>
                  {t.pct_change !== null && (
                    <span className={`font-medium ${t.pct_change > 0 ? 'text-red-600' : t.pct_change < 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                      {t.pct_change > 0 ? '▲' : t.pct_change < 0 ? '▼' : '—'} {Math.abs(t.pct_change)}%
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Review Volume by Day of Week</h2>
        <div className="grid grid-cols-7 gap-2">
          {day_of_week.map((d) => (
            <div key={d.day} className="text-center">
              <div
                className="flex h-16 flex-col items-center justify-center rounded-lg text-xs font-medium text-slate-700"
                style={{ backgroundColor: heatColor(d.count, maxDowCount) }}
                title={`${d.count} reviews, avg ${d.avg_rating ?? '—'}★`}
              >
                <div className="font-bold">{d.count}</div>
                <div className="text-[10px] text-slate-500">{d.avg_rating ? `${d.avg_rating}★` : '—'}</div>
              </div>
              <div className="mt-1 text-xs text-slate-500">{d.day}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
