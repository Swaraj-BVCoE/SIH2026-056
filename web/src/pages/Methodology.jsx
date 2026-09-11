import { useApi } from '../api'
import { Card, ErrorState, LoadingSkeleton } from '../components/UI'

export default function Methodology({ refreshKey }) {
  const data = useApi(`/api/methodology?r=${refreshKey}`)
  if (data.loading) return <LoadingSkeleton/>
  if (data.error) return <ErrorState onRetry={data.refresh}/>
  const sections = [
    ['Objective','High-frequency domestic airfare measurement designed to augment CPI research with timely, traceable observations.'],
    ['Data Sources','Direct airline portals and online travel aggregators. Each observation preserves its source and collection timestamp.'],
    ['Route Basket',`${data.data.route_count} configured representative domestic city-pairs. Coverage is displayed separately from configuration.`],
    ['Advance Purchase Windows',data.data.advance_windows.map(v=>`T+${v}`).join(', ') + '. Observations are assigned to transparent lead-time bands.'],
    ['Data Processing','Collection → normalization → validation → deduplication → outlier detection → index-ready dataset.'],
    ['Index Construction',`${data.data.name}. ${data.data.base}. ${data.data.aggregation}.`],
    ['Ethical Collection','Conservative rate limits, retries and audit logs are retained. CAPTCHA is never bypassed; blocked sources are marked unavailable and adapters can be replaced with licensed or official feeds.'],
    ['Limitations','Current coverage may be partial; automated requests may be blocked; component breakdowns may be unavailable; short history limits period comparisons; configured weights are not official PSD weights.'],
  ]
  return <div className="space-y-5"><div><h2 className="text-2xl font-extrabold">Methodology</h2><p className="mt-1 text-sm text-slate-500">Transparent definitions for analysts, researchers and reviewers.</p></div><div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm font-bold text-amber-950">{data.data.disclaimer}</div><div className="grid gap-5 lg:grid-cols-2">{sections.map(([title,body])=><Card key={title} title={title}><p className="leading-7 text-slate-600">{body}</p></Card>)}</div></div>
}
