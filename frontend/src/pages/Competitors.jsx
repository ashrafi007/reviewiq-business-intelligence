import { useEffect, useState } from 'react'
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useBusinesses } from '../context/BusinessContext'
import { getCompare } from '../api'
import StatCard from '../components/StatCard'
import { Loading, ErrorBox } from '../components/Loading'

const SERIES_COLORS = ['#6366f1', '#f59e0b', '#ef4444']

export default function Competitors() {
  const { businesses, selectedId } = useBusinesses()
  const [selectedIds, setSelectedIds] = useState([])
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (selectedId && selectedIds.length === 0) {
      setSelectedIds([selectedId])
    }
  }, [selectedId])

  useEffect(() => {
    if (selectedIds.length === 0) {
      setData(null)
      return
    }
    setLoading(true)
    setError(null)
    getCompare(selectedIds)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selectedIds])

  const toggleId = (id) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 3) return prev
      return [...prev, id]
    })
  }

  const radarData = data
    ? ['Food Quality', 'Service', 'Price', 'Ambiance', 'Packaging'].map((aspect) => {
        const row = { aspect }
        data.forEach((d) => {
          row[d.business.name] = d.aspect_scores[aspect]
        })
        return row
      })
    : []

  const barData = data
    ? data.map((d) => ({ name: d.business.name, rating: d.avg_scraped_rating }))
    : []

  const ranked = data
    ? [...data].sort((a, b) => (b.avg_sentiment ?? -1) - (a.avg_sentiment ?? -1))
    : []
  const myRank = selectedId ? ranked.findIndex((d) => d.business.id === selectedId) + 1 : 0

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Competitors</h1>

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-2 text-sm font-medium text-slate-600">
          Select up to 3 restaurants to compare ({selectedIds.length}/3)
        </div>
        <div className="flex flex-wrap gap-2">
          {businesses.map((b) => {
            const active = selectedIds.includes(b.id)
            const disabled = !active && selectedIds.length >= 3
            return (
              <button
                key={b.id}
                disabled={disabled}
                onClick={() => toggleId(b.id)}
                className={`rounded-full border px-3 py-1 text-sm transition ${
                  active
                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                    : disabled
                      ? 'border-slate-200 text-slate-300'
                      : 'border-slate-300 text-slate-600 hover:border-indigo-300'
                }`}
              >
                {b.name}
              </button>
            )
          })}
        </div>
      </div>

      {loading && <Loading label="Loading comparison…" />}
      {error && <ErrorBox message={error} />}

      {data && data.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.map((d) => (
              <StatCard
                key={d.business.id}
                label={d.business.name}
                value={d.avg_scraped_rating ? `${d.avg_scraped_rating}★` : '—'}
                sub={`${d.total_reviews} reviews · top complaint: ${d.top_complaint || 'none'}`}
                accent={d.business.id === selectedId ? 'indigo' : 'slate'}
              />
            ))}
          </div>

          {myRank > 0 && data.length > 1 && (
            <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-800">
              You rank <strong>#{myRank}</strong> out of {data.length} by average sentiment score.
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-sm font-semibold text-slate-700">Aspect Comparison</h2>
              <ResponsiveContainer width="100%" height={300}>
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="aspect" tick={{ fontSize: 12 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
                  {data.map((d, i) => (
                    <Radar
                      key={d.business.id}
                      name={d.business.name}
                      dataKey={d.business.name}
                      stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                      fill={SERIES_COLORS[i % SERIES_COLORS.length]}
                      fillOpacity={0.15}
                    />
                  ))}
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Tooltip />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-sm font-semibold text-slate-700">Average Rating</h2>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={barData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 5]} />
                  <Tooltip />
                  <Bar dataKey="rating" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      {selectedIds.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-400 shadow-sm">
          Select at least one restaurant above to see a comparison.
        </div>
      )}
    </div>
  )
}
