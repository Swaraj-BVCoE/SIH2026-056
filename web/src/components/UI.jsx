import { AlertTriangle, Database } from 'lucide-react'

export function Card({ title, subtitle, action, children, className = '' }) {
  return <section className={`rounded-xl border border-[#dfe5ec] bg-white shadow-[0_1px_2px_rgba(15,23,42,.035)] ${className}`}>
    {(title || action) && <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 px-5 py-4.5 sm:px-6">
      <div><h2 className="text-[15px] font-semibold tracking-tight text-[#172033]">{title}</h2>{subtitle && <p className="mt-1.5 text-xs leading-5 text-slate-500">{subtitle}</p>}</div>{action}
    </div>}
    <div className="p-5 sm:p-6">{children}</div>
  </section>
}

export function KPICard({ label, value, detail, icon: Icon, tone = 'blue' }) {
  return <div data-tone={tone} className="metric-card min-w-0 rounded-xl border border-[#dfe5ec] bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,.035)]">
    <div className="flex items-center justify-between gap-3"><p className="metric-label">{label}</p>{Icon && <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-slate-50 text-[#176b77]"><Icon size={18}/></span>}</div>
    <p className="metric-value mt-3 tracking-tight text-[#071a2f]">{value}</p>
    <p className="mt-2 min-h-5 text-xs leading-5 text-slate-500">{detail}</p>
  </div>
}

export function StatusBadge({ status }) {
  const value = status || 'NO DATA'
  const cls = value === 'HEALTHY' || value === 'SUCCESS' || value === 'FRESH' ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20' : value === 'BLOCKED' || value === 'FAILED' || value === 'STALE' ? 'bg-red-50 text-red-700 ring-red-600/20' : value === 'RUNNING' ? 'bg-blue-50 text-blue-700 ring-blue-600/20' : 'bg-amber-50 text-amber-700 ring-amber-600/20'
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[.06em] ring-1 ring-inset ${cls}`}>{value}</span>
}

export function LoadingSkeleton({ cards = 4 }) {
  return <div className="animate-pulse space-y-6"><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: cards }).map((_, i) => <div key={i} className="h-32 rounded-xl border border-slate-200 bg-white"/>)}</div><div className="h-80 rounded-xl border border-slate-200 bg-white"/></div>
}

export function EmptyState({ title = 'No data available', message = 'No observations match the current selection.' }) {
  return <div className="flex min-h-48 flex-col items-center justify-center text-center"><Database className="mb-3 text-slate-300" size={34}/><p className="font-semibold text-slate-700">{title}</p><p className="mt-1 max-w-md text-sm text-slate-500">{message}</p></div>
}

export function ErrorState({ onRetry }) {
  return <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center"><AlertTriangle className="mx-auto text-red-600"/><p className="mt-2 font-bold text-red-900">Analytics API unavailable</p><p className="mt-1 text-sm text-red-700">The dashboard could not load traceable observations.</p>{onRetry && <button onClick={onRetry} className="mt-4 rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white">Try again</button>}</div>
}

export function DataTable({ columns, rows, empty = 'No observations available.' }) {
  if (!rows?.length) return <EmptyState message={empty}/>
  return <div className="overflow-x-auto rounded-lg border border-slate-200"><table className="w-full min-w-[680px] text-left text-sm"><thead className="bg-slate-50/90"><tr className="border-b border-slate-200">{columns.map(col => <th key={col.key} className="whitespace-nowrap px-4 py-3 text-[10px] font-bold uppercase tracking-[.08em] text-slate-500">{col.label}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={row.id ?? row.route ?? i} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/70">{columns.map(col => <td key={col.key} className="whitespace-nowrap px-4 py-3.5 text-[13px] text-slate-700">{col.render ? col.render(row[col.key], row) : row[col.key] ?? '—'}</td>)}</tr>)}</tbody></table></div>
}

export function Select({ value, onChange, children, label }) {
  return <label className="flex flex-col gap-1.5 text-[11px] font-semibold text-slate-600">{label}<select value={value} onChange={e => onChange(e.target.value)} className="min-w-32 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-800 shadow-sm outline-none transition focus:border-[#0f6f78] focus:ring-2 focus:ring-teal-100">{children}</select></label>
}
