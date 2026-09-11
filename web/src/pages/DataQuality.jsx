import { AlertTriangle, CheckCircle, Database, Filter, ShieldCheck, Trash2 } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi, number } from '../api'
import { Card, DataTable, EmptyState, ErrorState, KPICard, LoadingSkeleton } from '../components/UI'

export default function DataQuality({ refreshKey }) {
  const q = useApi(`/api/data-quality?r=${refreshKey}`)
  if (q.loading) return <LoadingSkeleton cards={6}/>
  if (q.error) return <ErrorState onRetry={q.refresh}/>
  const d = q.data
  return <div className="space-y-5"><div><h2 className="text-2xl font-extrabold">Data Quality</h2><p className="mt-1 text-sm text-slate-500">Traceable cleaning, validation, coverage and usability indicators.</p></div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6"><KPICard label="Raw Records" value={number(d.raw_records)} icon={Database}/><KPICard label="Valid Records" value={number(d.valid_records)} icon={CheckCircle} tone="green"/><KPICard label="Duplicates Removed" value={d.duplicates_removed == null ? 'Not audited' : number(d.duplicates_removed)} detail={d.duplicates_note} icon={Trash2} tone="amber"/><KPICard label="Outliers" value={number(d.outliers_detected)} icon={AlertTriangle} tone="red"/><KPICard label="Missing Breakdowns" value={number(d.missing_fare_breakdowns)} detail="No components are fabricated" icon={Filter} tone="amber"/><KPICard label="Usable for Index" value={number(d.usable_index_observations)} icon={ShieldCheck} tone="green"/></div>
    <Card title="Processing Pipeline"><div className="grid gap-3 md:grid-cols-6">{['Raw data','Normalization','Validation','Deduplication','Outlier detection','Index dataset'].map((step, i) => <div key={step} className="relative rounded-lg border border-slate-200 bg-slate-50 p-4 text-center text-sm font-bold text-slate-700">{step}{i < 5 && <span className="absolute -right-3 top-1/2 z-10 hidden -translate-y-1/2 text-blue-600 md:block">→</span>}</div>)}</div></Card>
    <div className="grid gap-5 xl:grid-cols-2"><Card title="Missing Fare Breakdowns by Source" subtitle="Component gaps do not invalidate a reliable total fare">{d.missing_by_source.length ? <ResponsiveContainer width="100%" height={280}><BarChart data={d.missing_by_source}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="source"/><YAxis/><Tooltip/><Bar dataKey="missing" fill="#d97706" radius={[6,6,0,0]}/></BarChart></ResponsiveContainer> : <EmptyState/>}</Card><Card title="Advance Window Coverage"><DataTable columns={[{key:'label',label:'Window'},{key:'observations',label:'Observations',render:number},{key:'average_fare',label:'Average Fare',render:v=>v==null?'No data':new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(v)}]} rows={d.advance_window_coverage}/></Card></div>
    <Card title="Outliers by Route"><DataTable columns={[{key:'route',label:'Route'},{key:'outliers',label:'Outliers',render:number}]} rows={d.outliers_by_route} empty="No observations are currently flagged as outliers."/></Card>
  </div>
}
