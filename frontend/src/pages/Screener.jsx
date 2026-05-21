import { useEffect, useState } from 'react'
import { getLatestVCPDate, getVCPCandidates } from '../lib/supabase'
import { VCPCard } from '../components/VCPCard'

function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3">
      <div className="w-8 h-8 border-[3px] border-gray-200 border-t-gray-600 rounded-full animate-spin" />
      <p className="text-sm text-gray-400">Loading VCP setups...</p>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
      <svg className="w-12 h-12 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
      <p className="font-medium text-gray-500">No VCP setups found</p>
      <p className="text-sm text-gray-400 max-w-xs">
        Run the VCP scanner from GitHub Actions to populate this page.
      </p>
    </div>
  )
}

const FILTERS = ['All', 'Late Stage', 'Broke Out', 'Vol Drying']

export default function Screener() {
  const [loading,    setLoading]    = useState(true)
  const [stocks,     setStocks]     = useState([])
  const [filter,     setFilter]     = useState('All')
  const [scanDate,   setScanDate]   = useState(null)

  useEffect(() => {
    async function load() {
      try {
        const date = await getLatestVCPDate()
        if (date) {
          setScanDate(date)
          const data = await getVCPCandidates(date)
          setStocks(data)
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const filtered = stocks.filter(s => {
    if (filter === 'All')        return true
    if (filter === 'Late Stage') return s.num_contractions >= 3
    if (filter === 'Broke Out')  return s.broke_out
    if (filter === 'Vol Drying') return s.volume_drying
    return true
  })

  const scanDateFmt = scanDate
    ? new Date(scanDate + 'T00:00:00').toLocaleDateString('en-IN', {
        day: 'numeric', month: 'short', year: 'numeric'
      })
    : '--'

  return (
    <div className="min-h-screen" style={{ background: '#F1F5F9' }}>
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-5">

        {/* Page header */}
        <div className="text-center pb-1">
          <h1 className="text-[28px] font-bold text-gray-900 tracking-tight">
            VCP Screener
          </h1>
          <p className="text-[14px] text-gray-500 mt-1.5">
            Volatility Contraction Pattern setups — based on Mark Minervini's method
          </p>
        </div>

        {/* Stats bar */}
        {!loading && stocks.length > 0 && (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="grid grid-cols-2 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-gray-100">
              {[
                { label: 'Scan Date',    value: scanDateFmt,                                    color: 'text-gray-900' },
                { label: 'VCP Setups',   value: stocks.length,                                  color: 'text-gray-900' },
                { label: 'Broke Out',    value: stocks.filter(s => s.broke_out).length,         color: 'text-green-600' },
                { label: 'Late Stage',   value: stocks.filter(s => s.num_contractions >= 3).length, color: 'text-blue-600' },
              ].map(({ label, value, color }) => (
                <div key={label} className="flex flex-col items-center py-4 px-3 gap-1">
                  <span className="text-[11px] uppercase tracking-widest text-gray-400 font-semibold">{label}</span>
                  <span className={`text-[24px] font-bold leading-none ${color}`}>{value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* What is VCP */}
        <div className="bg-amber-50 rounded-2xl border border-amber-200 px-5 py-4">
          <p className="text-[13px] text-amber-800 leading-relaxed">
            <span className="font-semibold">What is VCP?</span> A Volatility Contraction Pattern forms when a stock
            consolidates after a strong uptrend, with each price swing getting smaller and volume drying up.
            The pivot is the entry point — buy when the stock breaks above it on high volume.
            Stop loss = bottom of the last contraction.
          </p>
        </div>

        {loading && <Spinner />}

        {!loading && stocks.length === 0 && <EmptyState />}

        {!loading && stocks.length > 0 && (
          <>
            {/* Filters */}
            <div className="flex items-center gap-2 flex-wrap">
              {FILTERS.map(f => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-4 py-2 rounded-full text-[13px] font-medium transition-colors ${
                    filter === f
                      ? 'bg-gray-900 text-white'
                      : 'bg-white border border-gray-200 text-gray-600 hover:border-gray-400'
                  }`}
                >
                  {f}
                  <span className="ml-1.5 text-[12px] opacity-60">
                    {f === 'All'        ? stocks.length :
                     f === 'Late Stage' ? stocks.filter(s => s.num_contractions >= 3).length :
                     f === 'Broke Out'  ? stocks.filter(s => s.broke_out).length :
                     stocks.filter(s => s.volume_drying).length}
                  </span>
                </button>
              ))}
            </div>

            {/* VCP cards grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {filtered.map(stock => (
                <VCPCard key={stock.id} stock={stock} />
              ))}
            </div>

            {filtered.length === 0 && (
              <p className="text-center text-gray-400 py-12 text-sm">
                No setups match this filter.
              </p>
            )}
          </>
        )}

        <footer className="text-center pt-4 pb-10">
          <p className="text-[12px] text-gray-400">
            VCP Scanner runs daily after market close.
            For research purposes only. Not financial advice.
          </p>
        </footer>

      </div>
    </div>
  )
}
