import { useState } from 'react'
import { Tooltip } from './Tooltip'

const STATUS_STYLES = {
  STRONG: {
    card  : 'bg-green-50 border-green-400',
    prc   : 'text-green-600',
    badge : 'bg-green-600 text-white',
  },
  MIXED: {
    card  : 'bg-orange-50 border-orange-400',
    prc   : 'text-orange-500',
    badge : 'bg-orange-500 text-white',
  },
  WEAK: {
    card  : 'bg-red-50 border-red-400',
    prc   : 'text-red-600',
    badge : 'bg-red-600 text-white',
  },
}

function PctVal({ value }) {
  if (value == null) return <span className="text-gray-400">—</span>
  const isPos = value >= 0
  return (
    <span className={isPos ? 'text-green-600' : 'text-red-500'}>
      {isPos ? '+' : ''}{Number(value).toFixed(2)}%
    </span>
  )
}

function SectorCard({ row }) {
  const [open, setOpen] = useState(false)
  const s = STATUS_STYLES[row.category] ?? STATUS_STYLES.MIXED

  return (
    <div
      onClick={() => setOpen(o => !o)}
      className={`relative rounded-xl border cursor-pointer transition-all duration-150 select-none ${s.card} ${open ? 'shadow-md' : 'hover:-translate-y-0.5 hover:shadow-sm'}`}
    >
      {/* Badge */}
      <span className={`absolute top-2.5 right-2.5 text-[10px] font-bold px-2 py-0.5 rounded-full ${s.badge}`}>
        {row.category}
      </span>

      {/* Default view */}
      <div className="p-3.5 pr-16">
        <p className="font-semibold text-gray-900 text-[14px] mb-1.5">{row.sector}</p>
        <p className={`text-[24px] font-semibold leading-none mb-2 ${s.prc}`}>{row.prc}</p>
        <div className="flex items-center gap-2 text-[12px] text-gray-500">
          <PctVal value={row.p3} />
          <span>3M</span>
          <PctVal value={row.p6} />
          <span>6M</span>
        </div>
      </div>

      {/* Expanded detail */}
      {open && (
        <div className="px-3.5 pb-3.5 pt-0 border-t border-black/5 mt-0">
          <div className="space-y-1.5 pt-3">
            {[
              { label: 'Momentum Score', value: `${row.prc}/100` },
              { label: '3M vs Nifty',    value: <PctVal value={row.p3} /> },
              { label: '6M vs Nifty',    value: <PctVal value={row.p6} /> },
              { label: 'Status',         value: row.category === 'WEAK' ? 'Weak — avoid this week' : row.category === 'MIXED' ? 'Mixed — one timeframe positive' : 'Strong — leading the market' },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between text-[12px]">
                <span className="text-gray-500">{label}</span>
                <span className="font-medium text-gray-800">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const TABS = ['All', 'Strong', 'Mixed', 'Weak']

export function SectorHeatmap({ sectors }) {
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
              Sectors ranked by momentum. Start at the top — those are leading the market. Tap any card for detail.
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
        <div className="px-5 pb-5">

          {/* Column header labels */}
          <div className="hidden sm:grid grid-cols-4 gap-2 mb-2 px-1">
            {[
              { label: 'Sector',         tip: 'Name of the NSE sector index.' },
              { label: 'Momentum Score', tip: 'Score 0–100. How strong this sector is vs its own past 12 months. Above 60 = strong. Below 40 = weak.' },
              { label: '3M RS',          tip: 'How much this sector has beaten or trailed Nifty 50 in the last 3 months.' },
              { label: '6M RS',          tip: 'Same as 3M but over 6 months. Both positive = sustained strength.' },
            ].map(({ label, tip }) => (
              <div key={label} className="flex items-center">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">{label}</span>
                <Tooltip text={tip} />
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-2 flex-wrap mb-4">
            {TABS.map(t => (
              <button
                key={t}
                onClick={e => { e.stopPropagation(); setTab(t) }}
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

          {/* Heatmap grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            {filtered.map(row => (
              <SectorCard key={row.sector} row={row} />
            ))}
          </div>

        </div>
      )}
    </div>
  )
}
