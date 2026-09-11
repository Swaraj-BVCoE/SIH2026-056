import { useState } from 'react'
import { useApi, inr, pct } from '../api'
import { Card, EmptyState, ErrorState, LoadingSkeleton, Select } from '../components/UI'

const tone = value => value == null ? 'border-slate-200 bg-slate-50 text-slate-500' : value <= -8 ? 'border-emerald-300 bg-emerald-100 text-emerald-900' : value < -2 ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : value <= 2 ? 'border-slate-200 bg-slate-100 text-slate-800' : value < 8 ? 'border-orange-200 bg-orange-50 text-orange-900' : 'border-red-300 bg-red-100 text-red-900'

export default function SectorHeatmap({ refreshKey }) {
  const [period, setPeriod] = useState('weekly')
  const data = useApi(`/api/index/routes?period=${period}&r=${refreshKey}`)
  if (data.loading) return <LoadingSkeleton/>
  if (data.error) return <ErrorState onRetry={data.refresh}/>
  return <div className="space-y-5"><div className="flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-extrabold">Sector-wise Airfare Inflation Heatmap</h2><p className="mt-1 text-sm text-slate-500">Route movement compared with the previous equivalent collection period.</p></div><Select label="Comparison" value={period} onChange={setPeriod}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></Select></div>
    <Card><div className="mb-5 flex flex-wrap gap-3 text-xs font-semibold"><Legend cls="bg-emerald-100" text="Strong decrease ≤ -8%"/><Legend cls="bg-emerald-50" text="Moderate decrease"/><Legend cls="bg-slate-100" text="Stable ±2%"/><Legend cls="bg-orange-50" text="Moderate increase"/><Legend cls="bg-red-100" text="Strong increase ≥ 8%"/></div>
      {!data.data.items.length ? <EmptyState title="No comparable sectors" message="At least two equivalent observation periods are needed to calculate route inflation."/> : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">{data.data.items.map(item => <article key={item.route} title={`Current ${inr(item.current_avg_fare)} · Previous ${inr(item.previous_avg_fare)} · ${item.observations} observations · ${item.source_coverage} sources`} className={`rounded-xl border p-4 ${tone(item.change_percent)}`}><div className="flex items-start justify-between"><div><p className="text-base font-extrabold">{item.origin} → {item.destination}</p><p className="mt-1 text-xs opacity-70">{item.observations} observations · {item.source_coverage} sources</p></div><p className="text-xl font-extrabold">{pct(item.change_percent)}</p></div><div className="mt-4 flex justify-between text-xs"><span>Current {inr(item.current_avg_fare)}</span><span>Prior {inr(item.previous_avg_fare)}</span></div></article>)}</div>}
    </Card>
  </div>
}
function Legend({ cls, text }) { return <span className="flex items-center gap-2"><i className={`h-3 w-3 rounded-sm border border-slate-300 ${cls}`}/>{text}</span> }
