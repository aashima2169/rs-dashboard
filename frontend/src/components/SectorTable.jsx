import { useState } from 'react'
import { Tooltip } from './Tooltip'

const STATUS_STYLES = {
  STRONG : { border: 'border-l-[3px] border-green-500', badge: 'bg-green-50 text-green-700 border border-green-200' },
  MIXED  : { border: 'border-l-[3px] border-amber-400', badge: 'bg-amber-50 text-amber-700 border border-amber-200' },
  WEAK   : { border: 'border-l-[3px] border-red-500',   badge: 'bg-red-50 text-red-600 border border-red-200'       },
}

function PctCell({ value }) {
  if (value == null) return <span className="text-gray-300">—</span>
  const isPos = value >= 0
  return (
    <span className={`font-medium ${isPos ? 'text-green-600' : 'text-red-500'}`}>
      {isPos ? '+' : ''}{Number(value).toFixed(2)}%
    </span>
  )
}

// Mobile card
function SectorCard({ row }) {
  const s = STATUS_STYLES[row.category] ?? STATUS_STYLES.MIXED
  return (
    <div className={`bg-white rounded-xl shadow-sm border border-gray-100 ${s.border} overflow-hidden`}>
      <div className="px-4 py-3.5 flex items-center justify-between">
        <span className="font-semibold text-gray-900 text-[15px]">{row.sector}</span>
        <span className={`text-[11px] font-bold px-2.5 py-1 rounded-full ${s.badge}`}>
          {row.category}
        </span>
      </div>
      <div className="px-4 pb-3.5 flex items-center gap-6 text-sm border-t border-gray-50">
        <div className="pt-2">
          <p className="text-[11px] text-gray-400 uppercase tracking-wide">Momentum</p>
          <p className="font-semibold text-gray-800 mt-0.5">{row.prc}</p>
        </div>
        <div className="pt-2">
          <p className="text-[11px] text-gray-400 uppercase tracking-wide">3M RS</p>
          <p className="mt-0.5"><PctCell value={row.p3} /></p>
        </div>
        <div className="pt-2">
          <p className="text-[11px] text-gray-400 uppercase tracking-wide">6M RS</p>
          <p className="mt-0.5"><PctCell value={row.p6} /></p>
        </div>
      </div>
    </div>
  )
}

// Desktop table row
function SectorRow({ row }) {
  const s = STATUS_STYLES[row.category] ?? STATUS_STYLES.MIXED
  return (
    <tr className={`border-b border-gray-50 hover:bg-gray-50/80 transition-colors ${s.border}`}>
      <td className="py-4 pl-5 pr-3 font-semibold text-gray-900 text-[14px]">{row.sector}</td>
      <td className="py-4 px-3 text-gray-700 text-[14px]">{row.prc}</td>
      <td className="py-4 px-3 text-[14px]"><PctCell value={row.p3} /></td>
      <td className="py-4 px-3 text-[14px]"><PctCell value={row.p6} /></td>
      <td className="py-4 pl-3 pr-5">
        <span className={`text-[11px] font-bold px-3 py-1 rounded-full ${s.badge}`}>
          {row.category}
        </span>
      </td>
    </tr>
  )
}

const TABS = ['All', 'Strong', 'Mixed', 'Weak']

export function SectorTable({ sectors }) {
  const [tab,       setTab]       = useState('All')
  const [collapsed, setCollapsed] = useState(false)

  const counts = {
    All    : sectors.length,
    Strong : sectors.filter(s => s.category === 'STRONG').length,
    Mixed  : sectors.filter(s => s.category === 'MIXED').length,
    Weak   : sectors.filter(s => s.category === 'WEAK').length,
  }

  const filtered = tab === 'All'
    ? sectors
    : sectors.filter(s => s.category === tab.toUpperCase())

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Section header */}
      <button
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50/60 transition-colors"
        onClick={() => setCollapsed(c => !c)}
      >
        <div className="flex items-center gap-3">
          <svg className="w-5 h-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <div className="text-left">
            <h2 className="font-bold text-gray-900 text-[16px]">Sector Strength</h2>
            <p className="text-[12px] text-gray-500 mt-0.5">
              Sectors ranked by momentum. Start at the top — those are leading the market.
            </p>
          </div>
        </div>
        <svg
          className={`w-5 h-5 text-gray-400 transition-transform duration-200 ${collapsed ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
        </svg>
      </button>

      {!collapsed && (
        <>
          {/* Tabs */}
          <div className="px-5 pb-4 flex items-center gap-2 flex-wrap">
            {TABS.map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-[13px] font-medium transition-colors ${
                  tab === t
                    ? 'bg-gray-900 text-white'
                    : 'bg-white border border-gray-200 text-gray-600 hover:border-gray-400'
                }`}
              >
                {t}
                <span className={`text-[12px] ${tab === t ? 'text-gray-400' : 'text-gray-400'}`}>
                  {counts[t]}
                </span>
              </button>
            ))}
          </div>

          {/* Mobile cards */}
          <div className="sm:hidden px-4 pb-4 space-y-2">
            {filtered.map(row => <SectorCard key={row.sector} row={row} />)}
          </div>

          {/* Desktop table */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  {[
                    { label: 'SECTOR',         tip: 'Name of the NSE sector index. Each sector groups similar companies — e.g. Pharma = pharmaceutical companies, Metal = mining and steel.' },
                    { label: 'MOMENTUM SCORE', tip: 'Score from 0–100. How strong this sector is right now vs its own past 12 months. Above 60 = strong. 40–60 = average. Below 40 = weak.' },
                    { label: '3M RS',          tip: 'How much this sector has beaten or trailed Nifty 50 in the last 3 months. Positive = doing better than the market.' },
                    { label: '6M RS',          tip: 'Same as 3M but over 6 months. When both 3M and 6M are positive, the sector has lasting strength — not just a short-term spike.' },
                    { label: 'STATUS',         tip: 'STRONG = beating the market on both 3M and 6M. MIXED = beating one, lagging the other. WEAK = lagging both.' },
                  ].map(({ label, tip }) => (
                    <th key={label} className="py-3 px-3 first:pl-5 last:pr-5 text-left">
                      <div className="flex items-center">
                        <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                          {label}
                        </span>
                        <Tooltip text={tip} />
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(row => <SectorRow key={row.sector} row={row} />)}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
