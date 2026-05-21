import { useState } from 'react'
import { Tooltip, InfoIcon } from './Tooltip'

const STATUS_STYLES = {
  STRONG : { row: 'border-l-4 border-green-500', badge: 'bg-green-100 text-green-700' },
  MIXED  : { row: 'border-l-4 border-amber-400', badge: 'bg-amber-100 text-amber-700' },
  WEAK   : { row: 'border-l-4 border-red-400',   badge: 'bg-red-100 text-red-600'    },
}

function PctCell({ value }) {
  if (value == null) return <span className="text-gray-400">—</span>
  const color = value >= 0 ? 'text-green-600' : 'text-red-600'
  return <span className={`font-medium ${color}`}>{value >= 0 ? '+' : ''}{value.toFixed(1)}%</span>
}

// ── Mobile card ───────────────────────────────────────────────────────────────
function SectorCard({ row }) {
  const s = STATUS_STYLES[row.category] ?? STATUS_STYLES.MIXED
  return (
    <div className={`bg-white rounded-xl ${s.row} p-4 shadow-sm border border-gray-100`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-semibold text-gray-900 text-base">{row.sector}</span>
        <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${s.badge}`}>
          {row.category}
        </span>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div>
          <span className="text-gray-400 text-xs">Momentum</span>
          <p className="font-semibold text-gray-800">{row.prc}</p>
        </div>
        <div>
          <span className="text-gray-400 text-xs">3M RS</span>
          <p><PctCell value={row.p3} /></p>
        </div>
        <div>
          <span className="text-gray-400 text-xs">6M RS</span>
          <p><PctCell value={row.p6} /></p>
        </div>
      </div>
    </div>
  )
}

// ── Desktop table row ─────────────────────────────────────────────────────────
function SectorRow({ row }) {
  const s = STATUS_STYLES[row.category] ?? STATUS_STYLES.MIXED
  return (
    <tr className={`border-b border-gray-50 hover:bg-gray-50 transition-colors ${s.row}`}>
      <td className="py-3.5 pl-4 pr-3 font-semibold text-gray-900">{row.sector}</td>
      <td className="py-3.5 px-3 text-gray-700">{row.prc}</td>
      <td className="py-3.5 px-3"><PctCell value={row.p3} /></td>
      <td className="py-3.5 px-3"><PctCell value={row.p6} /></td>
      <td className="py-3.5 pl-3 pr-4">
        <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${s.badge}`}>
          {row.category}
        </span>
      </td>
    </tr>
  )
}

const TABS = ['All', 'Strong', 'Mixed', 'Weak']

export function SectorTable({ sectors }) {
  const [activeTab, setActiveTab] = useState('All')
  const [collapsed, setCollapsed] = useState(false)

  const counts = {
    All    : sectors.length,
    Strong : sectors.filter(s => s.category === 'STRONG').length,
    Mixed  : sectors.filter(s => s.category === 'MIXED').length,
    Weak   : sectors.filter(s => s.category === 'WEAK').length,
  }

  const filtered = activeTab === 'All'
    ? sectors
    : sectors.filter(s => s.category === activeTab.toUpperCase())

  return (
    <div className="card overflow-hidden">
      {/* Section header */}
      <button
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
        onClick={() => setCollapsed(c => !c)}
      >
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-gray-700 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <div className="text-left">
            <h2 className="font-bold text-gray-900 text-base">Sector Strength</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Sectors ranked by momentum. Start at the top — those are leading the market.
            </p>
          </div>
        </div>
        <svg className={`w-5 h-5 text-gray-400 transition-transform ${collapsed ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
        </svg>
      </button>

      {!collapsed && (
        <>
          {/* Tabs */}
          <div className="px-4 pb-3 flex items-center gap-2 flex-wrap">
            {TABS.map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  activeTab === tab
                    ? 'bg-gray-900 text-white'
                    : 'bg-white border border-gray-200 text-gray-600 hover:border-gray-400'
                }`}
              >
                {tab}
                <span className={`text-xs ${activeTab === tab ? 'text-gray-300' : 'text-gray-400'}`}>
                  {counts[tab]}
                </span>
              </button>
            ))}
          </div>

          {/* Mobile: cards */}
          <div className="sm:hidden px-4 pb-4 space-y-2">
            {filtered.map(row => (
              <SectorCard key={row.sector} row={row} />
            ))}
          </div>

          {/* Desktop: table */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="py-2.5 pl-4 pr-3 text-left">
                    <div className="flex items-center gap-1">
                      <span className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">Sector</span>
                      <Tooltip text="Name of the NSE sector index. Each sector groups similar companies — e.g. Pharma = pharmaceutical companies, Metal = mining and steel.">
                        <InfoIcon />
                      </Tooltip>
                    </div>
                  </th>
                  <th className="py-2.5 px-3 text-left">
                    <div className="flex items-center gap-1">
                      <span className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">Momentum Score</span>
                      <Tooltip text="Score from 0–100. How strong this sector is right now vs its own past 12 months. Above 60 = strong. 40–60 = average. Below 40 = weak.">
                        <InfoIcon />
                      </Tooltip>
                    </div>
                  </th>
                  <th className="py-2.5 px-3 text-left">
                    <div className="flex items-center gap-1">
                      <span className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">3M RS</span>
                      <Tooltip text="How much this sector has beaten or trailed Nifty 50 in the last 3 months. Positive = doing better than the market. Negative = doing worse.">
                        <InfoIcon />
                      </Tooltip>
                    </div>
                  </th>
                  <th className="py-2.5 px-3 text-left">
                    <div className="flex items-center gap-1">
                      <span className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">6M RS</span>
                      <Tooltip text="Same as 3M but over 6 months. When both 3M and 6M are positive, the sector has lasting strength — not just a short-term spike.">
                        <InfoIcon />
                      </Tooltip>
                    </div>
                  </th>
                  <th className="py-2.5 pl-3 pr-4 text-left">
                    <div className="flex items-center gap-1">
                      <span className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">Status</span>
                      <Tooltip text="STRONG = beating the market on both 3M and 6M. MIXED = beating one, lagging the other. WEAK = lagging both — avoid this week.">
                        <InfoIcon />
                      </Tooltip>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(row => (
                  <SectorRow key={row.sector} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
