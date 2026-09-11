import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi, inr, number, pct } from '../api'
import { Card, EmptyState, ErrorState, KPICard, LoadingSkeleton, Select } from '../components/UI'
import { CircleDollarSign, Database, Plane, Server } from 'lucide-react'

export default function RouteAnalytics({ refreshKey }) {
  const routes = useApi(`/api/routes?r=${refreshKey}`)
  const [route, setRoute] = useState('')
  const selectedRoute = route || routes.data?.find(r => r.observations)?.route || routes.data?.[0]?.route || 'DEL-BOM'
  const [origin, destination] = selectedRoute.split('-')
  const detail = useApi(`/api/routes/${origin}/${destination}?r=${refreshKey}`)
  if (routes.loading || (route && detail.loading)) return <LoadingSkeleton/>
  if (routes.error || detail.error) return <ErrorState onRetry={() => { routes.refresh(); detail.refresh() }}/>
  const d = detail.data
  return <div className="space-y-5"><div className="flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-extrabold">Route Analytics</h2><p className="mt-1 text-sm text-slate-500">Sector fare levels, movement, lead-time effects, airlines and sources.</p></div><Select label="Route" value={selectedRoute} onChange={setRoute}>{routes.data?.map(r => <option key={r.route} value={r.route}>{r.route} · {r.observations} obs.</option>)}</Select></div>
    {!d || !d.observations ? <EmptyState title={`${selectedRoute} has no observations`} message="Choose a covered route or collect more data."/> : <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><KPICard label="Average Fare" value={inr(d.average_fare)} detail={`${pct(d.weekly_change)} weekly`} icon={CircleDollarSign}/><KPICard label="Fare Range" value={`${inr(d.minimum_fare)} – ${inr(d.maximum_fare)}`} detail={`Median ${inr(d.median_fare)}`} icon={Database} tone="indigo"/><KPICard label="Observations" value={number(d.observations)} detail={`${d.airlines_available} airlines`} icon={Plane} tone="green"/><KPICard label="Sources" value={d.sources_available} detail="Distinct collection portals" icon={Server} tone="amber"/></div>
      <div className="grid gap-5 xl:grid-cols-2"><Card title="Fare Trend"><ResponsiveContainer width="100%" height={290}><LineChart data={d.trend}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="date"/><YAxis tickFormatter={v => `₹${Math.round(v/1000)}k`}/><Tooltip formatter={inr}/><Line dataKey="average_fare" name="Average fare" stroke="#1d4ed8" strokeWidth={3}/></LineChart></ResponsiveContainer></Card><Card title="Advance Purchase Curve"><ResponsiveContainer width="100%" height={290}><LineChart data={d.lead_time}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="label"/><YAxis tickFormatter={v => `₹${Math.round(v/1000)}k`}/><Tooltip formatter={inr}/><Line dataKey="average_fare" name="Average fare" stroke="#0891b2" strokeWidth={3}/></LineChart></ResponsiveContainer></Card></div>
      <div className="grid gap-5 xl:grid-cols-2"><Comparison title="Airline Comparison" data={d.airlines}/><Comparison title="Source Comparison" data={d.sources}/></div>
    </>}
  </div>
}

function Comparison({ title, data }) { return <Card title={title}>{!data?.length ? <EmptyState/> : <ResponsiveContainer width="100%" height={260}><BarChart data={data}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="name"/><YAxis tickFormatter={v => `₹${Math.round(v/1000)}k`}/><Tooltip formatter={inr}/><Bar dataKey="average_fare" name="Average fare" fill="#334e75" radius={[6,6,0,0]}/></BarChart></ResponsiveContainer>}</Card> }
