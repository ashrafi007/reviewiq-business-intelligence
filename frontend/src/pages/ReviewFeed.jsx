import { useEffect, useState } from 'react'
import { useBusinesses } from '../context/BusinessContext'
import { getReviews, getOverview } from '../api'
import { Loading, ErrorBox } from '../components/Loading'

const SENTIMENT_BADGE = {
  positive: 'bg-emerald-100 text-emerald-700',
  negative: 'bg-red-100 text-red-700',
  neutral: 'bg-amber-100 text-amber-700',
}

function ReviewCard({ review }) {
  return (
    <div
      className={`rounded-xl border bg-white p-4 shadow-sm ${
        review.is_suspicious ? 'border-amber-300 ring-1 ring-amber-200' : 'border-slate-200'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-medium text-slate-800">{review.reviewer_name || 'Anonymous'}</span>
          <span className="text-xs text-slate-400">{review.review_date}</span>
          <span className="text-sm text-amber-500">
            {review.review_rating ? '★'.repeat(review.review_rating) : 'rating unknown'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {review.is_suspicious && (
            <span
              className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700"
              title="Writing-style anomaly signal (generic phrases, superlatives, punctuation patterns) - experimental, ~8% precision. Not a confirmed fraud detector."
            >
              ⚠️ unusual style
            </span>
          )}
          {review.sentiment_label && (
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SENTIMENT_BADGE[review.sentiment_label]}`}>
              {review.sentiment_label}
            </span>
          )}
          {review.topic_label && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              {review.topic_label}
            </span>
          )}
        </div>
      </div>
      <p className="mt-2 text-sm text-slate-700">{review.review_text}</p>
      {review.complaints?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {review.complaints.map((c) => (
            <span key={c} className="rounded bg-red-50 px-1.5 py-0.5 text-[11px] font-medium text-red-600">
              {c}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ReviewFeed() {
  const { selectedId } = useBusinesses()
  const [topics, setTopics] = useState([])
  const [filters, setFilters] = useState({ sentiment: '', topicId: '', suspiciousOnly: false, minRating: '', dateFrom: '', dateTo: '' })
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!selectedId) return
    getOverview(selectedId).then((d) => setTopics(d.topic_distribution)).catch(() => {})
  }, [selectedId])

  useEffect(() => {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    getReviews(selectedId, {
      sentiment: filters.sentiment || undefined,
      topicId: filters.topicId !== '' ? filters.topicId : undefined,
      suspiciousOnly: filters.suspiciousOnly,
      minRating: filters.minRating || undefined,
      dateFrom: filters.dateFrom || undefined,
      dateTo: filters.dateTo || undefined,
      page,
    })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selectedId, filters, page])

  const setFilter = (key, value) => {
    setFilters((f) => ({ ...f, [key]: value }))
    setPage(1)
  }

  if (!selectedId) return null

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Review Feed</h1>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <select
          value={filters.sentiment}
          onChange={(e) => setFilter('sentiment', e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm"
        >
          <option value="">All sentiment</option>
          <option value="positive">Positive</option>
          <option value="neutral">Neutral</option>
          <option value="negative">Negative</option>
        </select>

        <select
          value={filters.topicId}
          onChange={(e) => setFilter('topicId', e.target.value)}
          className="max-w-[220px] rounded-md border border-slate-300 px-2 py-1 text-sm"
        >
          <option value="">All topics</option>
          {topics.map((t) => (
            <option key={t.topic_id} value={t.topic_id}>
              {t.topic_label} ({t.count})
            </option>
          ))}
        </select>

        <select
          value={filters.minRating}
          onChange={(e) => setFilter('minRating', e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm"
        >
          <option value="">Any rating</option>
          {[5, 4, 3, 2, 1].map((n) => (
            <option key={n} value={n}>
              {n}★ and up
            </option>
          ))}
        </select>

        <input
          type="date"
          value={filters.dateFrom}
          onChange={(e) => setFilter('dateFrom', e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-600"
        />
        <span className="text-xs text-slate-400">to</span>
        <input
          type="date"
          value={filters.dateTo}
          onChange={(e) => setFilter('dateTo', e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-600"
        />

        <label
          className="flex items-center gap-1.5 text-sm text-slate-600"
          title="Writing-style anomaly signal - experimental, ~8% precision. Not a confirmed fraud detector."
        >
          <input
            type="checkbox"
            checked={filters.suspiciousOnly}
            onChange={(e) => setFilter('suspiciousOnly', e.target.checked)}
          />
          Unusual style only
        </label>
      </div>

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <div className="text-sm text-slate-500">{data.total} reviews match these filters</div>
          <div className="space-y-3">
            {data.reviews.map((r) => (
              <ReviewCard key={r.review_id} review={r} />
            ))}
            {data.reviews.length === 0 && (
              <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-400 shadow-sm">
                No reviews match these filters.
              </div>
            )}
          </div>

          {data.total_pages > 1 && (
            <div className="flex items-center justify-center gap-3 py-4">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="rounded-md border border-slate-300 px-3 py-1 text-sm disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-sm text-slate-500">
                Page {data.page} of {data.total_pages}
              </span>
              <button
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-md border border-slate-300 px-3 py-1 text-sm disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
