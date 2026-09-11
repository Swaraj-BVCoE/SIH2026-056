import { ExternalLink, Landmark, Menu, X } from 'lucide-react'
import { NAV } from './nav'

export default function Sidebar({ page, onNavigate, open, onClose }) {
  const groups = [
    ['Monitoring', NAV.slice(0, 6)],
    ['Data governance', NAV.slice(6, 9)],
    ['Assurance', NAV.slice(9)],
  ]
  return <><div onClick={onClose} className={`fixed inset-0 z-30 bg-slate-950/55 backdrop-blur-[1px] lg:hidden ${open ? 'block' : 'hidden'}`}/><aside className={`fixed inset-y-0 left-0 z-40 flex w-[17.5rem] flex-col bg-[#071a2f] text-white shadow-2xl shadow-slate-950/10 transition-transform duration-200 lg:translate-x-0 lg:shadow-none ${open ? 'translate-x-0' : '-translate-x-full'}`}>
    <div className="h-1 bg-[linear-gradient(90deg,#d97706_0_33%,#e2e8f0_33%_66%,#15803d_66%)]"/>
    <div className="flex min-h-24 items-center justify-between border-b border-white/10 px-5 py-5"><div className="flex min-w-0 items-center gap-3"><span className="grid size-11 shrink-0 place-items-center rounded-xl border border-white/15 bg-white/8 text-cyan-100"><Landmark size={22}/></span><div className="min-w-0"><p className="truncate text-[15px] font-semibold tracking-tight">Airfare Price Monitor</p><p className="mt-1 text-[11px] leading-4 text-slate-400">CPI augmentation analytics</p></div></div><button onClick={onClose} className="rounded-lg p-2 text-slate-300 hover:bg-white/10 lg:hidden" aria-label="Close navigation"><X size={20}/></button></div>
    <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Primary navigation">{groups.map(([group, items]) => <div key={group} className="mb-5 last:mb-0"><p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[.16em] text-slate-500">{group}</p>{items.map(([id, label, Icon]) => <button key={id} onClick={() => { onNavigate(id); onClose() }} aria-current={page === id ? 'page' : undefined} className={`mb-1 flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-[13px] transition ${page === id ? 'border-cyan-400/20 bg-cyan-400/12 font-semibold text-white' : 'border-transparent text-slate-300 hover:bg-white/6 hover:text-white'}`}><Icon size={17} className={page === id ? 'text-cyan-300' : 'text-slate-500'}/><span>{label}</span></button>)}</div>)}</nav>
    <div className="border-t border-white/10 p-4"><p className="mb-3 px-1 text-[10px] uppercase tracking-[.14em] text-slate-500">Decision support system</p><a href="/docs" target="_blank" rel="noreferrer" className="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3.5 py-3 text-xs font-semibold text-slate-200 transition hover:border-white/20 hover:bg-white/10">Analytics API <ExternalLink size={14} className="text-slate-400"/></a></div>
  </aside></>
}

export function MobileMenuButton({ onClick }) { return <button onClick={onClick} className="rounded-lg border border-slate-200 bg-white p-2 text-slate-700 shadow-sm transition hover:bg-slate-50 lg:hidden" aria-label="Open navigation"><Menu size={19}/></button> }
