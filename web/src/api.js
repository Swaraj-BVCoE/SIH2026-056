import { useCallback, useEffect, useState } from 'react'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export async function apiFetch(path) {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) throw new Error(`API request failed (${response.status})`)
  return response.json()
}

export function useApi(path, { interval = 0 } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshedAt, setRefreshedAt] = useState(null)
  const load = useCallback(async () => {
    try {
      setError(null)
      const result = await apiFetch(path)
      setData(result)
      setRefreshedAt(new Date())
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [path])
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- fetching is the external synchronization performed by this hook
    load()
    if (!interval) return undefined
    const timer = window.setInterval(load, interval)
    return () => window.clearInterval(timer)
  }, [load, interval])
  return { data, loading, error, refresh: load, refreshedAt }
}

export const inr = value => value == null ? '—' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value)
export const number = value => value == null ? '—' : new Intl.NumberFormat('en-IN').format(value)
export const pct = value => value == null ? 'Insufficient data' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
export const istDateTime = value => value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) + ' IST' : 'No observations'
