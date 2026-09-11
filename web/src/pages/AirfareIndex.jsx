import { useState } from 'react'
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi, pct } from '../api'
import { Card, EmptyState, ErrorState, LoadingSkeleton, Select } from '../components/UI'

export default function AirfareIndex({ refreshKey }) {
  const [days, setDays] = useState('30')
  const [frequency, setFrequency] = useState('daily')
  const latest = useApi(`/api/index/latest?r=${refreshKey}`)
  const trend = useApi(`/api/index/trend?frequency=${frequency}&days=${days}&r=${refreshKey}`)
  if (latest.loading || trend.loading) return <LoadingSkeleton/>
  if (latest.error || trend.error) return <ErrorState onRetry={() => { latest.refresh(); trend.refresh() }}/>
  return <div className="space-y-5"><div><h2 className="text-2xl font-extrabold text-slate-950">Airfare Price Index</h2><p className="mt-1 text-sm text-slate-500">Configurable weighted price-relative monitoring across the representative route basket.</p></div>
    <Card title="APIx Trend" subtitle={`Base period: ${latest.data.base_period}`} action={<div className="flex gap-3"><Select label="Frequency" value={frequency} onChange={setFrequency}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></Select><Select label="Range" value={days} onChange={setDays}><option value="7">7 days</option><option value="30">30 days</option><option value="90">3 months</option><option value="180">6 months</option></Select></div>}>
      {!trend.data.items.length ? <EmptyState/> : <ResponsiveContainer width="100%" height={390}><AreaChart data={trend.data.items}><defs><linearGradient id="apiFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#1d4ed8" stopOpacity=".25"/><stop offset="1" stopColor="#1d4ed8" stopOpacity="0"/></linearGradient></defs><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="date"/><YAxis domain={['auto', 'auto']}/><Tooltip formatter={v => [v.toFixed(2), 'APIx']}/><ReferenceLine y={100} stroke="#64748b" strokeDasharray="4 4" label="Base 100"/><Area type="monotone" dataKey="value" stroke="#1d4ed8" strokeWidth={3} fill="url(#apiFill)"/></AreaChart></ResponsiveContainer>}
    </Card>
    <div className="grid gap-5 md:grid-cols-3"><Card title="Daily movement"><p className="text-3xl font-extrabold">{pct(latest.data.daily_change)}</p></Card><Card title="Weekly movement"><p className="text-3xl font-extrabold">{pct(latest.data.weekly_change)}</p></Card><Card title="Monthly movement"><p className="text-3xl font-extrabold">{pct(latest.data.monthly_change)}</p></Card></div>
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><p className="font-bold">{latest.data.weights.label}</p><p className="mt-1">Official PSD weights were not present in the repository. The CSV configuration is normalized automatically and can be replaced when authoritative weights are provided.</p></div>
  </div>
}
