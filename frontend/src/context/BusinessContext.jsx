import { createContext, useContext, useEffect, useState } from 'react'
import { listBusinesses } from '../api'

const BusinessContext = createContext(null)

export function BusinessProvider({ children }) {
  const [businesses, setBusinesses] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    listBusinesses()
      .then((data) => {
        setBusinesses(data)
        if (data.length > 0) setSelectedId(data[0].id)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const selected = businesses.find((b) => b.id === selectedId) || null

  return (
    <BusinessContext.Provider
      value={{ businesses, selectedId, setSelectedId, selected, loading, error }}
    >
      {children}
    </BusinessContext.Provider>
  )
}

export function useBusinesses() {
  const ctx = useContext(BusinessContext)
  if (!ctx) throw new Error('useBusinesses must be used within BusinessProvider')
  return ctx
}
