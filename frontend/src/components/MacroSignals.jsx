import { useState } from 'react'
import { Tooltip } from './Tooltip'

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

const COLS = {
  POSITIVE: {
    key      : 'POSITIVE',
    label    : 'POSITIVE',
    pillCls  : 'bg-green-600 text-white',
    cardBorder: 'border-l-[3px] border-amber-400',
    dotCls   : 'bg-white',
    empty    : 'No positive signals today',
    tooltip  : 'These factors are helping the Indian stock market right now.',
  },
  NEUTRAL: {
    key      : 'NEUTRAL',
    label    : 'WATCH',
    pillCls  : 'bg-amber-500 text-white',
    cardBorder: 'border-l-[3px] border-amber-400',
    dotCls   : 'bg-white',
    empty    : 'Nothing on the watch list today',
    tooltip  : 'These factors are not strongly good or bad right now. Keep watching — they could turn either way.',
  },
  BEARISH: {
    key      : 'BEARISH',
    label    : 'NEGATIVE',
    pillCls  : 'bg-red-600 text-white',
    cardBorder: 'border-l-[3px] border-red-500',
    dotCls   : 'bg-white',
    empty    : 'No negative signals today',
    tooltip  : 'These factors are hurting the Indian stock market right now. Be cautious.',
  },
}

function toColKey(sentiment = '') {
  const s = sentiment.toUpperCase()
  if (s === 'BULLISH')  return 'POSITIVE'
  if (s === 'BEARISH')  return 'BEARISH'
  return 'NEUTRAL'
}

function FindingCard({ finding, cfg }) {
  const label = LABEL_MAP[finding.topic] ?? finding.topic.replace(/_/g, ' ')
  return (
    <div className={`bg-white rounded-xl border border-gray-100 shadow-sm ${cfg.cardBorder} overflow-hidden`}>
      <div className="px-4 py-3.5">
        <p className="font-semibold text-gray-900 text-[14px] mb-1">{label}</p>
        <p className="text-[13px] text-gray-600 leading-relaxed">{finding.finding}</p>
      </div>
    </div>
  )
}

function Column({ cfgKey, findings }) {
  const cfg   = COLS[cfgKey]
  const count = findings.length
  return (
    <div className="flex flex-col gap-3">
      {/* Column header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`${cfg.pillCls} text-[12px] font-bold px-3.5 py-1.5 rounded-full flex items-center gap-1.5`}>
            <span className="w-1.5 h-1.5 bg-white/70 rounded-full" />
            {cfg.label}
            <Tooltip text={cfg.tooltip} />
          </span>
        </div>
        <span className="text-[12px] text-gray-400 font-medium">
          {count} {count === 1 ? 'factor' : 'factors'}
        </span>
      </div>

      {/* Cards */}
      {count === 0 ? (
        <p className="text-[13px] text-gray-400 text-center py-6">{cfg.empty}</p>
      ) : (
        <div className="space-y-2.5">
          {findings.map((f, i) => (
            <FindingCard key={i} finding={f} cfg={cfg} />
          ))}
        </div>
      )}
    </div>
  )
}

export function MacroSignals({ findings }) {
  const [collapsed, setCollapsed] = useState(false)

  const grouped = { POSITIVE: [], NEUTRAL: [], BEARISH: [] }
  findings.forEach(f => grouped[toColKey(f.sentiment)].push(f))

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Section header */}
      <button
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50/60 transition-colors"
        onClick={() => setCollapsed(c => !c)}
      >
        <div className="flex items-center gap-3">
          <svg className="w-5 h-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="10" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
          </svg>
          <div className="text-left">
            <h2 className="font-bold text-gray-900 text-[16px]">Global Macro Signals</h2>
            <p className="text-[12px] text-gray-500 mt-0.5">
              News and events affecting Indian stocks. Use this to understand WHY the market is moving.
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
        <div className="px-5 pb-5 grid grid-cols-1 sm:grid-cols-3 gap-5">
          <Column cfgKey="POSITIVE" findings={grouped.POSITIVE} />
          <Column cfgKey="NEUTRAL"  findings={grouped.NEUTRAL}  />
          <Column cfgKey="BEARISH"  findings={grouped.BEARISH}  />
        </div>
      )}
    </div>
  )
}
