import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useBusinesses } from '../context/BusinessContext'
import { getOverview } from '../api'
import StatCard from '../components/StatCard'
import SentimentGauge from '../components/SentimentGauge'
import { Loading, ErrorBox } from '../components/Loading'

const TOPIC_COLORS = ['#6366f1', '#06b6d4', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6', '#ec4899', '#64748b']

export default function Overview() {
  const { selectedId } = useBusinesses()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    getOverview(selectedId)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selectedId])

  if (!selectedId) return null
  if (loading) return <Loading label="Loading overview…" />
  if (error) return <ErrorBox message={error} />
  if (!data) return null

  const { business, total_reviews, avg_sentiment, avg_scraped_rating, suspicious_count,
    topic_distribution, top_complaints, rating_forecast, owner_response_insight } = data

  const forecastTrend = rating_forecast.length >= 2
    ? rating_forecast[rating_forecast.length - 1].yhat - rating_forecast[0].yhat
    : 0
  const forecastLabel = rating_forecast.length
    ? `predicted ${forecastTrend < -0.02 ? 'to drop to' : forecastTrend > 0.02 ? 'to rise to' : 'to hold around'} ${rating_forecast[rating_forecast.length - 1].yhat.toFixed(1)}★`
    : 'not enough history yet'

  const withResponse = owner_response_insight?.true
  const withoutResponse = owner_response_insight?.false
  const responseDelta = withResponse && withoutResponse
    ? (withResponse.avg_rating - withoutResponse.avg_rating).toFixed(1)
    : null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{business.name}</h1>
        <p className="text-sm text-slate-500">{business.address}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Current rating" value={`${business.overall_rating}★`} sub={`${business.total_reviews.toLocaleString()} reviews on Google`} />
        <StatCard label="Scraped sample rating" value={avg_scraped_rating ? `${avg_scraped_rating}★` : '—'} sub={`${total_reviews} reviews analyzed`} accent="indigo" />
        <StatCard label="4-week forecast" value={rating_forecast.length ? `${rating_forecast[rating_forecast.length - 1].yhat.toFixed(1)}★` : '—'} sub={forecastLabel} accent={forecastTrend < -0.02 ? 'red' : 'green'} />
        <StatCard
          label="Unusual-style reviews"
          value={suspicious_count}
          sub="writing-style anomaly, ~8% precision"
          accent={suspicious_count > 0 ? 'amber' : 'slate'}
          title="Flags reviews whose writing style (generic phrases, superlatives, punctuation patterns) resembles a sentiment/rating mismatch. Experimental - only about 1 in 13 flags are expected to be true positives. Not a confirmed fraud detector."
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold text-slate-700">Sentiment Score</h2>
          <SentimentGauge score={avg_sentiment} />
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold text-slate-700">Topic Breakdown</h2>
          {topic_distribution.length === 0 ? (
            <div className="text-sm text-slate-400">No topic data yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={topic_distribution.slice(0, 8)}
                  dataKey="count"
                  nameKey="topic_label"
                  innerRadius={50}
                  outerRadius={85}
                  paddingAngle={2}
                >
                  {topic_distribution.slice(0, 8).map((_, i) => (
                    <Cell key={i} fill={TOPIC_COLORS[i % TOPIC_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v, n, p) => [`${v} reviews (${p.payload.pct}%)`, p.payload.topic_label]} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Top Complaints</h2>
        {top_complaints.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-400 shadow-sm">
            No complaints detected — nice.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {top_complaints.slice(0, 3).map((c) => (
              <div key={c.complaint} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-xs font-medium uppercase tracking-wide text-red-500">{c.complaint}</div>
                <div className="mt-1 text-2xl font-bold text-slate-900">{c.count}</div>
                <div className="text-xs text-slate-400">mentions</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {responseDelta !== null && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-800">
          Reviews where the owner responded average{' '}
          <strong>{responseDelta >= 0 ? `${responseDelta}★ higher` : `${Math.abs(responseDelta)}★ lower`}</strong>{' '}
          ({withResponse.avg_rating}★ vs {withoutResponse.avg_rating}★, based on {withResponse.count} responded / {withoutResponse.count} not).
        </div>
      )}
    </div>
  )
}
