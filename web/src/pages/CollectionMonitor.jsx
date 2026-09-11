import { Activity, CheckCircle, Clock, Database, XCircle } from 'lucide-react'
import { useApi, istDateTime, number } from '../api'
import { Card, DataTable, ErrorState, KPICard, LoadingSkeleton, StatusBadge } from '../components/UI'

export default function CollectionMonitor({ refreshKey }) {
  const summary = useApi(`/api/runs/summary?r=${refreshKey}`, { interval: 45000 })
  const runs = useApi(`/api/runs/recent?limit=50&r=${refreshKey}`, { interval: 45000 })
  if (summary.loading || runs.loading) return <LoadingSkeleton cards={6}/>
  if (summary.error || runs.error) return <ErrorState onRetry={() => { summary.refresh(); runs.refresh() }}/>
  const d = summary.data
  const cols = [{key:'started_at',label:'Time',render:istDateTime},{key:'portal',label:'Portal',render:v=>v.replaceAll('_',' ')},{key:'route',label:'Route'},{key:'travel_date',label:'Travel date'},{key:'status',label:'Status',render:v=><StatusBadge status={v}/>},{key:'records',label:'Records',render:number},{key:'duration_s',label:'Duration',render:v=>v==null?'Running':`${v}s`}]
  return <div className="space-y-5"><div><h2 className="text-2xl font-extrabold">Collection Monitor</h2><p className="mt-1 text-sm text-slate-500">Audit trail for scheduled and manual scraper runs · auto-refreshes every 45 seconds.</p></div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6"><KPICard label="Jobs Today" value={number(d.jobs_today)} icon={Activity}/><KPICard label="Successful" value={number(d.successful)} icon={CheckCircle} tone="green"/><KPICard label="Failed / Blocked" value={number(d.failed)} icon={XCircle} tone="red"/><KPICard label="Running" value={number(d.running)} icon={Clock} tone="amber"/><KPICard label="Records Collected" value={number(d.records_collected)} icon={Database}/><KPICard label="Average Duration" value={d.average_run_duration == null ? 'Insufficient data' : `${d.average_run_duration}s`} icon={Clock} tone="indigo"/></div><Card title="Latest Scraping Runs" subtitle="Failed and blocked collections remain visible for auditability"><DataTable columns={cols} rows={runs.data}/></Card></div>
}
