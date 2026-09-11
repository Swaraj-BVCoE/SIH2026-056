import { useRef, useState } from 'react'
import { FileUp } from 'lucide-react'
import { API_BASE_URL, inr, useApi } from '../api'
import { Card, DataTable, ErrorState, KPICard, LoadingSkeleton } from '../components/UI'

export default function Backtesting({ refreshKey }) {
  const data = useApi(`/api/backtesting?r=${refreshKey}`)
  const input = useRef(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  if (data.loading) return <LoadingSkeleton/>
  if (data.error) return <ErrorState onRetry={data.refresh}/>
  const upload = async event => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true); setUploadError('')
    const body = new FormData(); body.append('file', file)
    try {
      const response = await fetch(`${API_BASE_URL}/api/backtesting/import`, { method: 'POST', body })
      if (!response.ok) throw new Error((await response.json()).detail || 'Import failed')
      await data.refresh()
    } catch (error) { setUploadError(error.message) } finally { setUploading(false); event.target.value = '' }
  }
  const d = data.data
  const cols = [{key:'date',label:'Date'},{key:'route',label:'Route'},{key:'collected_average',label:'Collected average',render:inr},{key:'reference_fare',label:'Reference fare',render:inr},{key:'difference',label:'Difference',render:inr},{key:'percentage_error',label:'Absolute % error',render:v=>v==null?'No match':`${v}%`}]
  return <div className="space-y-5"><div className="flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-extrabold">Validation & Backtesting</h2><p className="mt-1 text-sm text-slate-500">Compare collected averages with an authoritative historical or public reference file.</p></div><><input ref={input} type="file" accept=".csv,text/csv" onChange={upload} className="hidden"/><button disabled={uploading} onClick={()=>input.current?.click()} className="flex items-center gap-2 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50"><FileUp size={17}/>{uploading?'Importing…':'Import Reference CSV'}</button></></div>
    {uploadError && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">{uploadError}</div>}
    {d.status === 'NO_REFERENCE_DATASET' ? <Card><div className="flex min-h-64 flex-col items-center justify-center text-center"><span className="rounded-full bg-blue-50 p-4 text-blue-700"><FileUp size={30}/></span><h3 className="mt-4 text-lg font-bold">{d.message}</h3><p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">Upload a UTF-8 CSV with {d.required_columns.join(', ')}. No DGCA or official reference observations are fabricated.</p></div></Card> : <><div className="grid gap-4 md:grid-cols-3"><KPICard label="MAE" value={inr(d.mae)} detail="Mean absolute error"/><KPICard label="MAPE" value={d.mape==null?'—':`${d.mape}%`} detail="Mean absolute percentage error"/><KPICard label="Coverage" value={d.coverage==null?'—':`${d.coverage}%`} detail={d.message}/></div><Card title="Reference Comparison"><DataTable columns={cols} rows={d.items}/></Card></>}
  </div>
}
