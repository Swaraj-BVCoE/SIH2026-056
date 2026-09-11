import { useMemo, useState } from 'react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import { NAV } from './components/nav'
import AdvancePurchase from './pages/AdvancePurchase'
import AirfareIndex from './pages/AirfareIndex'
import AirlinesSources from './pages/AirlinesSources'
import Backtesting from './pages/Backtesting'
import CollectionMonitor from './pages/CollectionMonitor'
import DataExplorer from './pages/DataExplorer'
import DataQuality from './pages/DataQuality'
import Methodology from './pages/Methodology'
import Overview from './pages/Overview'
import RouteAnalytics from './pages/RouteAnalytics'
import SectorHeatmap from './pages/SectorHeatmap'

const PAGES = { overview: Overview, index: AirfareIndex, routes: RouteAnalytics, advance: AdvancePurchase, heatmap: SectorHeatmap, sources: AirlinesSources, quality: DataQuality, monitor: CollectionMonitor, data: DataExplorer, validation: Backtesting, methodology: Methodology }

export default function Dashboard() {
  const [page, setPage] = useState('overview')
  const [menuOpen, setMenuOpen] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [refreshedAt, setRefreshedAt] = useState(new Date())
  const Page = PAGES[page] || Overview
  const title = useMemo(() => NAV.find(item => item[0] === page)?.[1] || 'Overview', [page])
  const refresh = () => { setRefreshKey(Date.now()); setRefreshedAt(new Date()) }
  return <div className="min-h-screen bg-[#f4f6f8] text-slate-900"><Sidebar page={page} onNavigate={setPage} open={menuOpen} onClose={() => setMenuOpen(false)}/><div className="lg:pl-[17.5rem]"><Header title={title} onMenu={() => setMenuOpen(true)} onRefresh={refresh} refreshedAt={refreshedAt}/><main className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-9"><Page refreshKey={refreshKey}/></main><footer className="mx-auto max-w-[1600px] px-6 pb-8 text-center text-[11px] leading-5 text-slate-500"><span className="font-semibold text-slate-600">Experimental analytical prototype.</span> Not an officially published MoSPI CPI index. All statistics are derived from traceable stored observations.</footer></div></div>
}
