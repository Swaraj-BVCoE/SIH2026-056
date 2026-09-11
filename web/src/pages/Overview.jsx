import { Activity, Database, Gauge, Plane, Route, TrendingUp } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi, inr, number, pct, istDateTime } from '../api'
import { Card, DataTable, EmptyState, ErrorState, KPICard, LoadingSkeleton, StatusBadge } from '../components/UI'

export default function Overview({ refreshKey }) {
  const overview = useApi(`/api/overview?r=${refreshKey}`, { interval: 60000 })
  const trend = useApi(`/api/index/trend?frequency=daily&days=180&r=${refreshKey}`, { interval: 60000 })
  const contrib = useApi(`/api/index/contributions?period=weekly&r=${refreshKey}`, { interval: 60000 })
  const lead = useApi(`/api/lead-time?r=${refreshKey}`, { interval: 60000 })
  const sources = useApi(`/api/sources/status?r=${refreshKey}`, { interval: 60000 })
  if (overview.loading) return <LoadingSkeleton cards={6}/>
  if (overview.error) return <ErrorState onRetry={overview.refresh}/>
  const data = overview.data
  const index = data.index
  const movementDetail = value => value == null ? 'Insufficient historical data' : value >= 0 ? 'Increase from comparison period' : 'Decrease from comparison period'
  const cols = [
    { key: 'route', label: 'Route' }, { key: 'current_avg_fare', label: 'Current avg', render: inr },
    { key: 'change_percent', label: 'Change', render: pct }, { key: 'weighted_contribution', label: 'Contribution', render: v => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(3)}` },
  ]
  return <div className="space-y-6">
    <div className="overview-intro">
      <div className="flex flex-wrap items-start justify-between gap-5"><div className="max-w-2xl"><p className="intro-kicker">Domestic aviation · Price statistics</p><h2 className="mt-2">Real-Time Airfare Price Index</h2><p className="mt-2 text-sm leading-6">High-frequency domestic airfare monitoring for CPI research and evidence-based policy analysis.</p></div><div className="intro-meta rounded-lg px-4 py-3"><StatusBadge status={index.freshness.status}/><p className="mt-2 text-xs leading-5">Latest collection<br/><span className="font-semibold">{istDateTime(index.last_updated)}</span></p></div></div>
      <p className="intro-note mt-5 border-t pt-3">Prototype methodology · Not an officially published MoSPI CPI index</p>
    </div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <KPICard label="Current APIx" value={index.value?.toFixed(2) ?? 'No data'} detail={index.monthly_change == null ? 'Base 100 · configurable weights' : `${pct(index.monthly_change)} vs previous month`} icon={Gauge}/>
      <KPICard label="Daily Change" value={pct(index.daily_change)} detail={movementDetail(index.daily_change)} icon={Activity} tone={index.daily_change < 0 ? 'green' : 'blue'}/>
      <KPICard label="Weekly Change" value={pct(index.weekly_change)} detail={movementDetail(index.weekly_change)} icon={TrendingUp} tone={index.weekly_change < 0 ? 'green' : 'indigo'}/>
      <KPICard label="Routes Monitored" value={`${data.routes_monitored} / ${data.routes_configured}`} detail="Representative city-pair basket" icon={Route} tone="amber"/>
      <KPICard label="Data Points" value={number(data.data_points)} detail={`${number(index.records_used)} in latest index period`} icon={Database}/>
      <KPICard label="Source Health" value={`${data.sources_active} / ${data.sources_configured}`} detail="Healthy or partial sources" icon={Plane} tone="green"/>
    </div>
    <Card title="Airfare Price Index Trend" subtitle="Weighted route price relatives · baseline 100" action={<span className="rounded-md bg-slate-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">Daily</span>}>
      {!trend.data?.items?.length ? <EmptyState title="No index observations" message="Collect valid fares across at least one period to construct the index."/> : <ResponsiveContainer width="100%" height={320}><AreaChart data={trend.data.items} margin={{ left: 0, right: 16 }}><defs><linearGradient id="indexFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#2563eb" stopOpacity={.22}/><stop offset="95%" stopColor="#2563eb" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false}/><XAxis dataKey="date" tick={{ fontSize: 12 }} tickLine={false}/><YAxis domain={['auto', 'auto']} tick={{ fontSize: 12 }} tickLine={false}/><Tooltip formatter={v => [v.toFixed(2), 'APIx']}/><ReferenceLine y={100} stroke="#64748b" strokeDasharray="5 5"/><Area type="monotone" dataKey="value" stroke="#1d4ed8" strokeWidth={3} fill="url(#indexFill)" activeDot={{ r: 5 }}/></AreaChart></ResponsiveContainer>}
    </Card>
    <div className="grid gap-5 xl:grid-cols-2"><Card title="Top Contributors to Airfare Inflation" subtitle="Weekly period · only routes with a comparable prior period"><DataTable columns={cols} rows={contrib.data?.contributors} empty="No route has sufficient comparable observations to calculate a positive contribution."/></Card><Card title="Routes Pulling the Index Down" subtitle="Weekly period"><DataTable columns={cols} rows={contrib.data?.declines} empty="No route has sufficient comparable observations showing a decline."/></Card></div>
    <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]"><Card title="Advance Purchase Impact" subtitle="Observed average fare by standardized lead-time window">{lead.data?.items?.some(i => i.average_fare != null) ? <><ResponsiveContainer width="100%" height={250}><LineChart data={lead.data.items}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="label"/><YAxis tickFormatter={v => `₹${Math.round(v/1000)}k`}/><Tooltip formatter={inr}/><Line type="monotone" dataKey="average_fare" name="Average fare" stroke="#0891b2" strokeWidth={3} connectNulls={false}/></LineChart></ResponsiveContainer>{lead.data.insight && <p className="mt-3 rounded-lg bg-cyan-50 p-3 text-sm font-semibold text-cyan-900">{lead.data.insight}</p>}</> : <EmptyState title="Insufficient lead-time coverage" message="T+1, T+7, T+15, T+30 and T+45 values appear only when observations exist."/>}</Card><Card title="Collection Source Health" subtitle="Status is derived from records and recent terminal collection runs"><div className="space-y-3">{sources.data?.sources?.map(s => <div key={s.source} className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3 last:border-0"><div><p className="text-sm font-semibold text-slate-800">{s.source.replaceAll('_', ' ')}</p><p className="text-xs text-slate-500">{number(s.records)} records · {s.routes_covered} routes</p></div><StatusBadge status={s.status}/></div>)}</div></Card></div>
  </div>
}
