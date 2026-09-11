import { CircleCheck, RefreshCw } from 'lucide-react'
import { MobileMenuButton } from './Sidebar'

export default function Header({ title, onMenu, onRefresh, refreshedAt }) {
  return <header className="sticky top-0 z-20 flex min-h-[4.75rem] items-center justify-between gap-4 border-b border-slate-200/90 bg-white/95 px-4 backdrop-blur-md sm:px-6 lg:px-10">
    <div className="flex min-w-0 items-center gap-3"><MobileMenuButton onClick={onMenu}/><div className="min-w-0"><p className="hidden text-[10px] font-bold uppercase tracking-[.14em] text-slate-400 sm:block">Aviation statistics <span className="px-1.5 text-slate-300">/</span> Dashboard</p><h1 className="truncate text-lg font-semibold tracking-tight text-[#071a2f] sm:mt-0.5">{title}</h1></div></div>
    <div className="flex items-center gap-2 sm:gap-4"><div className="hidden items-center gap-2 border-r border-slate-200 pr-4 md:flex"><CircleCheck size={15} className="text-emerald-600"/><div><p className="text-[11px] font-semibold text-slate-700">System online</p><p className="text-[10px] text-slate-400">Updated {refreshedAt ? refreshedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—'}</p></div></div><button onClick={onRefresh} className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 active:translate-y-px"><RefreshCw size={15}/> <span className="hidden sm:inline">Refresh data</span></button></div>
  </header>
}
