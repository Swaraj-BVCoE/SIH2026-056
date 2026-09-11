import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi, inr, number } from '../api'
import { Card, EmptyState, ErrorState, KPICard, LoadingSkeleton, Select } from '../components/UI'
import { CalendarClock } from 'lucide-react'

export default function AdvancePurchase({ refreshKey }) {
  const routes = useApi(`/api/routes?r=${refreshKey}`)
  const [route, setRoute] = useState('ALL')
  const selected = route === 'ALL' ? '' : `&origin=${route.slice(0,3)}&destination=${route.slice(4)}`
  const lead = useApi(`/api/lead-time?r=${refreshKey}${selected}`)
  if (routes.loading || lead.loading) return <LoadingSkeleton cards={5}/>
  if (routes.error || lead.error) return <ErrorState onRetry={() => { routes.refresh(); lead.refresh() }}/>
  const available = lead.data.items.some(item => item.average_fare != null)
  return <div className="space-y-5"><div className="flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-extrabold">Lead-Time / Advance Purchase Analysis</h2><p className="mt-1 text-sm text-slate-500">How does the observed fare change depending on how early the passenger books?</p></div><Select label="Route" value={route} onChange={setRoute}><option value="ALL">All monitored routes</option>{routes.data.map(r => <option key={r.route}>{r.route}</option>)}</Select></div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">{lead.data.items.map(item => <KPICard key={item.label} label={`${item.label} Average`} value={inr(item.average_fare)} detail={`${number(item.observations)} observations`} icon={CalendarClock} tone={item.advance_days >= 30 ? 'green' : 'blue'}/>)}</div>
    <Card title="Advance Purchase Fare Curve" subtitle="Windows map observations to T+1, T+7, T+15, T+30 and T+45; missing points are not interpolated.">{available ? <ResponsiveContainer width="100%" height={380}><LineChart data={lead.data.items}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="label"/><YAxis tickFormatter={v => `₹${Math.round(v/1000)}k`}/><Tooltip formatter={inr}/><Line type="monotone" dataKey="average_fare" name="Average fare" stroke="#0369a1" strokeWidth={4} connectNulls={false}/></LineChart></ResponsiveContainer> : <EmptyState title="Insufficient lead-time data" message="No valid observations are available for the selected route."/>}{lead.data.insight && <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-900">{lead.data.insight}</p>}</Card>
  </div>
}
