import { useState } from 'react'
import { Tooltip, InfoIcon } from './Tooltip'

const LABEL_MAP = {
  fii_dii_flows    : 'FII / DII Flows',
  rbi_policy       : 'RBI Policy',
  rupee_dollar     : 'Rupee vs Dollar',
  crude_oil        : 'Crude Oil',
  global_risk      : 'Global Risk',
  tariffs_trade    : 'Tariffs & Trade',
  geopolitical_war : 'Geopolitical Risk',
  customs_duty_bans: 'Customs & Duties',
  healthcare_virus : 'Health Risk',
  domestic_policy  : 'India Policy',
  us_bond_yields   : 'US Bond Yields',
  gold_silver      : 'Gold & Silver',
}

const COLUMN_CONFIG = {
  POSITIVE: {
    label     : 'POSITIVE',
    pill      : 'bg-green-600 text-white',
    cardBorder: 'border-l-4 border-green-500',
    empty     : 'No positive signals today',
    tooltip   : 'These factors are helping the Indian stock market right now.',
  },
  NEUTRAL: {
    label     : 'WATCH',
    pill      : 'bg-amber-500 text-white',
    cardBorder: 'border-l-4 border-amber-400',
    empty     : 'Nothing on the watch list today',
    tooltip   : 'These factors are not strongly good or bad. Keep watching — they could turn either way.',
  },
  BEARISH: {
    label     : 'NEGATIVE',
    pill      : 'bg-red-600 text-white',
    cardBorder: 'border-l-4 border-red-500',
    empty     : 'No negative signals today',
    tooltip   : 'These factors are hurting the Indian stock market right now. Be cautious.',
  },
}

// Map sentiment values from DB to column keys
function toColumnKey(sentiment = '') {
  const s = sentiment.toUpperCase()
  if (s === 'BULLISH')  return 'POSITIVE'
  if (s === 'BEARISH')  return 'BEARISH'
  return 'NEUTRAL'
}

function FindingCard({ finding, borderClass }) {
  const label = LABEL_MAP[finding.topic] ?? finding.topic.replace(/_/g, ' ')
  return (
    <div className={`bg-white rounded-xl ${borderClass} p-4 shadow-sm border border-gray-100`}>
      <p className="font-semibold text-gray-900 text-sm mb-1">{label}</p>
      <p className="text-sm text-gray-600 leading-relaxed">{finding.finding}</p>
    </div>
  )
}

function Column({ columnKey, findings }) {
  const cfg    = COLUMN_CONFIG[columnKey]
  const count  = findings.length

  return (
    <div className="flex flex-col gap-3">
      {/* Column header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`${cfg.pill} text-xs font-bold px-3 py-1 rounded-full flex items-center gap-1`}>
            <span className="w-1.5 h-1.5 bg-white rounded-full opacity-80" />
            {cfg.label}
            <Tooltip text={cfg.tooltip}>
              <svg className="w-3 h-3 opacity-70 cursor-help ml-0.5" fill="none"
                viewBox="0 0 24 24" stroke="currentColor">
                <circle cx="12" cy="12" r="10" strokeWidth={2} />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 16v-4M12 8h.01" />
              </svg>
            </Tooltip>
          </span>
        </div>
        <span className="text-xs text-gray-400">{count} {count === 1 ? 'factor' : 'factors'}</span>
      </div>

      {/* Cards or empty state */}
      {count === 0 ? (
        <p className="text-sm text-gray-400 text-center py-4">{cfg.empty}</p>
      ) : (
        <div className="space-y-3">
          {findings.map((f, i) => (
            <FindingCard key={i} finding={f} borderClass={cfg.cardBorder} />
          ))}
        </div>
      )}
    </div>
  )
}

export function MacroSignals({ findings }) {
  const [collapsed, setCollapsed] = useState(false)

  const grouped = { POSITIVE: [], NEUTRAL: [], BEARISH: [] }
  findings.forEach(f => {
    const key = toColumnKey(f.sentiment)
    grouped[key].push(f)
  })

  return (
    <div className="card overflow-hidden">
      {/* Section header */}
      <button
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
        onClick={() => setCollapsed(c => !c)}
      >
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-gray-700 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <circle cx="12" cy="12" r="10" strokeWidth={2} />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
          </svg>
          <div className="text-left">
            <h2 className="font-bold text-gray-900 text-base">Global Macro Signals</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              News and events affecting Indian stocks. Use this to understand WHY the market is moving.
            </p>
          </div>
        </div>
        <svg className={`w-5 h-5 text-gray-400 transition-transform ${collapsed ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
        </svg>
      </button>

      {!collapsed && (
        <div className="p-4 grid grid-cols-1 sm:grid-cols-3 gap-6">
          <Column columnKey="POSITIVE" findings={grouped.POSITIVE} />
          <Column columnKey="NEUTRAL"  findings={grouped.NEUTRAL}  />
          <Column columnKey="BEARISH"  findings={grouped.BEARISH}  />
        </div>
      )}
    </div>
  )
}
