const BASE = import.meta.env.VITE_API_URL || ''

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

export function listBusinesses() {
  return get('/api/businesses')
}

export function getOverview(businessId) {
  return get(`/api/overview?business_id=${businessId}`)
}

export function getReviews(
  businessId,
  { sentiment, topicId, suspiciousOnly, minRating, maxRating, dateFrom, dateTo, page = 1 } = {},
) {
  const params = new URLSearchParams({ business_id: businessId, page })
  if (sentiment) params.set('sentiment', sentiment)
  if (topicId !== undefined && topicId !== null) params.set('topic_id', topicId)
  if (suspiciousOnly) params.set('suspicious_only', 'true')
  if (minRating) params.set('min_rating', minRating)
  if (maxRating) params.set('max_rating', maxRating)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return get(`/api/reviews?${params.toString()}`)
}

export function getCompare(ids) {
  return get(`/api/compare?ids=${ids.join(',')}`)
}

export function getTrends(businessId) {
  return get(`/api/trends?business_id=${businessId}`)
}

export function getComplaints(businessId) {
  return get(`/api/complaints?business_id=${businessId}`)
}

export async function postChat(question, businessId) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, business_id: businessId }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}
