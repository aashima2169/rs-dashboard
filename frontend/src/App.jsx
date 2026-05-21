import { useEffect, useState } from 'react'
import { getLatestScanDate, getSectorScores, getMacroSummary, getMacroFindings } from './lib/supabase'
import { Header }       from './components/Header'
import { SectorTable }  from './components/SectorTable'
import { MacroSignals } from './components/MacroSignals'

function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3">
      <div className="w-8 h-8 border-[3px] border-gray-200 border-t-gray-600 rounded-full animate-spin" />
      <p className="text-sm text-gray-400">Loading latest data...</p>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-2">
      <p className="text-red-500 font-semibold">Failed to load data</p>
      <p className="text-sm text-gray-400">{message}</p>
    </div>
  )
}

export default function App() {
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [sectors,  setSectors]  = useState([])
  const [macro,    setMacro]    = useState(null)
  const [findings, setFindings] = useState([])

  useEffect(() => {
    async function load() {
      try {
        const scanDate = await getLatestScanDate()
        if (!scanDate) throw new Error('No data found in database')
        const [s, m, f] = await Promise.all([
          getSectorScores(scanDate),
          getMacroSummary(scanDate),
          getMacroFindings(scanDate),
        ])
        setSectors(s)
        setMacro(m)
        setFindings(f)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const counts = {
    strong: sectors.filter(s => s.category === 'STRONG').length,
    mixed : sectors.filter(s => s.category === 'MIXED').length,
    weak  : sectors.filter(s => s.category === 'WEAK').length,
  }

  return (
    <div className="min-h-screen" style={{ background: '#F1F5F9' }}>
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-4">

        {/* Page title */}
        <div className="text-center pb-2">
          <h1 className="text-[28px] sm:text-[32px] font-bold text-gray-900 tracking-tight">
            Sector Strength Tracker
          </h1>
          <p className="text-[14px] text-gray-500 mt-1.5">
            The market moves in sectors. Start there.
          </p>
        </div>

        {loading && <Spinner />}
        {error   && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <Header macro={macro} sectorCounts={counts} />
            <SectorTable sectors={sectors} />
            <MacroSignals findings={findings} />
          </>
        )}

        {/* Footer */}
        <footer className="text-center pt-6 pb-10">
          <p className="text-[12px] text-gray-400">
            Sector Strength Tracker refreshes every trading day after market close.
            For research purposes only. Not financial advice.
          </p>
          <p className="text-[11px] text-gray-300 mt-1">
            Built with care for swing traders.
          </p>
        </footer>

      </div>
    </div>
  )
}
