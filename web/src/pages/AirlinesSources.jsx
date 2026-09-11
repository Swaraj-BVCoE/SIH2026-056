import { useApi, inr, istDateTime, number } from '../api'
import { Card, DataTable, ErrorState, LoadingSkeleton, StatusBadge } from '../components/UI'

export default function AirlinesSources({ refreshKey }) {
  const data = useApi(`/api/sources/status?r=${refreshKey}`)
  const coverage = useApi(`/api/coverage?r=${refreshKey}`)
  if (data.loading || coverage.loading) return <LoadingSkeleton/>
  if (data.error || coverage.error) return <ErrorState onRetry={() => { data.refresh(); coverage.refresh() }}/>
  const airlineCols = [{ key: 'airline', label: 'Airline' }, { key: 'records', label: 'Records', render: number }, { key: 'routes_covered', label: 'Routes' }, { key: 'average_fare', label: 'Average fare', render: inr }, { key: 'lowest_fare', label: 'Lowest fare', render: inr }, { key: 'latest_observation', label: 'Latest', render: istDateTime }]
  const sourceCols = [{ key: 'source', label: 'Collection source', render: v => v.replaceAll('_', ' ') }, { key: 'status', label: 'Status', render: v => <StatusBadge status={v}/> }, { key: 'success_rate', label: 'Success rate', render: v => v == null ? 'No terminal runs' : `${v}%` }, { key: 'last_successful_collection', label: 'Last success', render: istDateTime }, { key: 'records', label: 'Records', render: number }, { key: 'routes_covered', label: 'Routes' }]
  const sources = data.data.sources.map(s => s.source)
  return <div className="space-y-5"><div><h2 className="text-2xl font-extrabold">Airlines & Sources</h2><p className="mt-1 text-sm text-slate-500">Carrier analytics are separated from collection-portal health.</p></div><Card title="Airlines" subtitle="Metrics calculated from valid stored observations"><DataTable columns={airlineCols} rows={data.data.airlines}/></Card><Card title="Collection Sources" subtitle="Blocked sources remain transparent; no access controls are bypassed"><DataTable columns={sourceCols} rows={data.data.sources}/></Card>
    <Card title="Source Coverage Matrix" subtitle="Availability by configured route and collection source"><div className="overflow-x-auto"><table className="min-w-[1050px] w-full text-sm"><thead><tr><th className="sticky left-0 bg-white p-3 text-left">Route</th>{sources.map(s => <th key={s} className="p-3 text-center text-xs">{s.replace('_direct','')}</th>)}</tr></thead><tbody>{coverage.data.matrix.map(row => <tr key={row.route} className="border-t border-slate-100"><th className="sticky left-0 bg-white p-3 text-left font-semibold">{row.route}</th>{sources.map(s => <td key={s} className="p-3 text-center"><span className={row.sources[s] ? 'text-emerald-600' : 'text-slate-300'}>{row.sources[s] ? '●' : '—'}</span></td>)}</tr>)}</tbody></table></div></Card>
  </div>
}
