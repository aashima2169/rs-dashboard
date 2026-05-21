import { useState } from 'react'

const MOMENTUM_STYLES = {
  Strong  : 'bg-green-100 text-green-700',
  Neutral : 'bg-amber-100 text-amber-700',
  Weak    : 'bg-red-100 text-red-600',
  Unknown : 'bg-gray-100 text-gray-500',
}

const STAGE_COLOR = (stage = '') => {
  if (stage.includes('Late'))  return 'text-green-600'
  if (stage.includes('Mid'))   return 'text-amber-600'
  return 'text-gray-500'
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-[12px] text-gray-400">{label}</span>
      <span className="text-[12px] font-medium text-gray-800">{value}</span>
    </div>
  )
}

export function VCPCard({ stock }) {
  const [open, setOpen] = useState(false)

  const momStyle = MOMENTUM_STYLES[stock.sector_momentum] ?? MOMENTUM_STYLES.Unknown
  const rr       = stock.risk_reward ?? 0
  const rrColor  = rr >= 2.5 ? 'text-green-600' : rr >= 1.5 ? 'text-amber-600' : 'text-red-500'
  const brokeOut = stock.broke_out

  return (
    <div className={`bg-white rounded-2xl border shadow-sm overflow-hidden transition-all ${
      brokeOut ? 'border-green-300' : 'border-gray-200'
    }`}>

      {/* Header */}
      <div className="px-5 py-4 flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <h3 className="font-bold text-gray-900 text-[18px]">{stock.symbol}</h3>
            {brokeOut && (
              <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-green-600 text-white">
                BROKE OUT
              </span>
            )}
            <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${momStyle}`}>
              {stock.sector} · {stock.sector_momentum}
            </span>
          </div>
          <p className={`text-[12px] font-medium ${STAGE_COLOR(stock.vcp_stage)}`}>
            {stock.vcp_stage}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-[11px] text-gray-400 uppercase tracking-wide">Score</p>
          <p className="text-[24px] font-bold text-gray-900 leading-none">{stock.score}</p>
          <p className="text-[10px] text-gray-400">/100</p>
        </div>
      </div>

      {/* Key levels */}
      <div className="grid grid-cols-3 border-t border-gray-100">
        {[
          { label: 'Current',    value: `₹${stock.current_price}`,   color: 'text-gray-900' },
          { label: 'Pivot',      value: `₹${stock.pivot}`,           color: 'text-blue-600' },
          { label: 'Stop Loss',  value: `₹${stock.stop_loss}`,       color: 'text-red-500'  },
        ].map(({ label, value, color }) => (
          <div key={label} className="flex flex-col items-center py-3 border-r border-gray-100 last:border-0">
            <span className="text-[10px] uppercase tracking-wide text-gray-400 mb-0.5">{label}</span>
            <span className={`text-[14px] font-semibold ${color}`}>{value}</span>
          </div>
        ))}
      </div>

      {/* Targets row */}
      <div className="grid grid-cols-3 border-t border-gray-100 bg-gray-50">
        {[
          { label: 'T1 +15%', value: `₹${stock.target_1}` },
          { label: 'T2 +25%', value: `₹${stock.target_2}` },
          { label: 'T3 +40%', value: `₹${stock.target_3}` },
        ].map(({ label, value }) => (
          <div key={label} className="flex flex-col items-center py-2.5 border-r border-gray-100 last:border-0">
            <span className="text-[10px] text-gray-400 mb-0.5">{label}</span>
            <span className="text-[13px] font-semibold text-green-600">{value}</span>
          </div>
        ))}
      </div>

      {/* Summary pills */}
      <div className="px-5 py-3 flex items-center gap-2 flex-wrap border-t border-gray-100">
        <span className="text-[11px] px-2.5 py-1 rounded-full bg-gray-100 text-gray-600">
          {stock.num_contractions} contractions
        </span>
        <span className={`text-[11px] px-2.5 py-1 rounded-full ${
          stock.volume_drying ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'
        }`}>
          {stock.volume_drying ? '✓ Volume drying' : 'Volume normal'}
        </span>
        <span className={`text-[11px] px-2.5 py-1 rounded-full bg-gray-100 ${rrColor}`}>
          R:R {rr}:1
        </span>
        <span className="text-[11px] px-2.5 py-1 rounded-full bg-gray-100 text-gray-600">
          {stock.pct_from_pivot > 0
            ? `${stock.pct_from_pivot}% below pivot`
            : `${Math.abs(stock.pct_from_pivot)}% above pivot`}
        </span>
      </div>

      {/* Expand button */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full px-5 py-2.5 text-[12px] text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors border-t border-gray-100 flex items-center justify-center gap-1"
      >
        {open ? 'Hide detail' : 'Show full detail'}
        <svg className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="px-5 pb-4 border-t border-gray-100">
          <div className="pt-3 space-y-0">
            <Row label="Base started"    value={stock.base_start_date} />
            <Row label="First in scanner" value={stock.first_seen} />
            {stock.broke_out && (
              <>
                <Row label="Breakout date" value={stock.breakout_date} />
                {stock.days_to_t1 && (
                  <Row label="Days to T1" value={`${stock.days_to_t1} days`} />
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
