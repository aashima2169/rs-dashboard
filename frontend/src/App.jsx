import { useEffect, useState } from 'react'
import { getLatestScanDate, getSectorScores, getMacroSummary, getMacroFindings } from './lib/supabase'
import { Header }       from './components/Header'
import { SectorTable }  from './components/SectorTable'
import { MacroSignals } from './components/MacroSignals'

function LoadingSpinner() {
  return (
    <div className="flex flex-col items-center justify-center min-h-64 gap-3">
      <div className="w-8 h-8 border-4 border-gray-200 border-t-gray-700 rounded-full animate-spin" />
      <p className="text-sm text-gray-400">Loading latest data...</p>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-64 gap-2">
      <p className="text-red-500 font-medium">Failed to load data</p>
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
        if (!scanDate) throw new Error('No data found')

        const [sectorData, macroData, findingsData] = await Promise.all([
          getSectorScores(scanDate),
          getMacroSummary(scanDate),
          getMacroFindings(scanDate),
        ])

        setSectors(sectorData)
        setMacro(macroData)
        setFindings(findingsData)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const sectorCounts = {
    strong: sectors.filter(s => s.category === 'STRONG').length,
    mixed : sectors.filter(s => s.category === 'MIXED').length,
    weak  : sectors.filter(s => s.category === 'WEAK').length,
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">

        {/* ── Page title ── */}
        <div className="text-center pb-2">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">
            Sector Strength Tracker
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            The market moves in sectors. Start there.
          </p>
        </div>

        {loading && <LoadingSpinner />}
        {error   && <ErrorState message={error} />}

        {!loading && !error && (
          <>
            <Header macro={macro} sectorCounts={sectorCounts} />
            <SectorTable sectors={sectors} />
            <MacroSignals findings={findings} />
          </>
        )}

        {/* ── Footer ── */}
        <footer className="text-center pt-4 pb-8">
          <p className="text-xs text-gray-400">
            Sector Strength Tracker refreshes every trading day after market close.
            For research purposes only. Not financial advice.
          </p>
          <p className="text-xs text-gray-300 mt-1">
            Built with care for swing traders.
          </p>
        </footer>

      </div>
    </div>
  )
}
