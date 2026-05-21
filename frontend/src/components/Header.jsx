import { Tooltip } from './Tooltip'

const REGIME_STYLES = {
  BULL    : { bg: 'bg-green-600',  label: 'BULLISH'  },
  NEUTRAL : { bg: 'bg-amber-500',  label: 'NEUTRAL'  },
  BEAR    : { bg: 'bg-red-600',    label: 'BEARISH'  },
}

const SENTIMENT = {
  POSITIVE : { pill: 'bg-red-100 text-red-500',     label: 'POSITIVE' },
  NEGATIVE : { pill: 'bg-red-100 text-red-500',     label: 'NEGATIVE' },
  NEUTRAL  : { pill: 'bg-amber-100 text-amber-600', label: 'NEUTRAL'  },
}

// Override positive correctly
const SENTIMENT_MAP = {
  POSITIVE : { pill: 'bg-green-100 text-green-700', label: 'POSITIVE' },
  NEGATIVE : { pill: 'bg-red-100 text-red-500',     label: 'NEGATIVE' },
  NEUTRAL  : { pill: 'bg-amber-100 text-amber-600', label: 'NEUTRAL'  },
}

function getSentiment(summary = '') {
  if (summary.startsWith('POSITIVE')) return 'POSITIVE'
  if (summary.startsWith('NEGATIVE')) return 'NEGATIVE'
  return 'NEUTRAL'
}

function stripLabel(summary = '') {
  return summary.replace(/^(POSITIVE|NEGATIVE|NEUTRAL)\s*[—\-–]\s*/i, '').trim()
}

function MetricTile({ label, children, tooltip }) {
  return (
    <div className="flex flex-col items-center justify-center py-5 px-4 gap-1.5">
      <div className="flex items-center gap-0.5">
        <span className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">
          {label}
        </span>
        {tooltip && <Tooltip text={tooltip} />}
      </div>
      {children}
    </div>
  )
}

export function Header({ macro, sectorCounts }) {
  const regime      = macro?.regime ?? 'NEUTRAL'
  const regStyle    = REGIME_STYLES[regime] ?? REGIME_STYLES.NEUTRAL
  const score       = macro?.final_score ?? '--'
  const summary     = macro?.summary ?? ''
  const sentiment   = getSentiment(summary)
  const sentStyle   = SENTIMENT_MAP[sentiment]
  const cleanText   = stripLabel(summary)

  const scanDate = macro?.scan_date
    ? new Date(macro.scan_date + 'T00:00:00').toLocaleDateString('en-IN', {
        day: 'numeric', month: 'short', year: 'numeric'
      })
    : '--'

  return (
    <div className="space-y-3">
      {/* ── 5 metric tiles ── */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="grid grid-cols-2 sm:grid-cols-5 divide-y sm:divide-y-0 sm:divide-x divide-gray-100">

          <MetricTile label="Market Sentiment">
            <span className={`${regStyle.bg} text-white text-sm font-bold px-5 py-1.5 rounded-full tracking-wide`}>
              {regStyle.label}
            </span>
          </MetricTile>

          <MetricTile
            label="Market Score"
            tooltip="Combined score out of 100 based on Nifty trend, India VIX (fear gauge), and global macro signals. Above 65 = good conditions. Below 35 = be cautious."
          >
            <span className="text-[28px] font-bold text-gray-900 leading-none">{score}/100</span>
            <span className="text-[11px] text-gray-400 mt-0.5">Higher = better conditions</span>
          </MetricTile>

          <MetricTile label="Last Updated">
            <span className="text-[20px] font-bold text-gray-900 leading-none">{scanDate}</span>
            <span className="text-[10px] text-gray-400 mt-0.5 text-center">Updates daily after market close</span>
          </MetricTile>

          <MetricTile label="Sectors Strong">
            <span className="text-[32px] font-bold text-green-600 leading-none">{sectorCounts.strong}</span>
          </MetricTile>

          <MetricTile label="Sectors Weak">
            <span className="text-[32px] font-bold text-red-600 leading-none">{sectorCounts.weak}</span>
          </MetricTile>

        </div>
      </div>

      {/* ── Market Insight ── */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Header label */}
        <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100">
          <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">
            Market Insight
          </span>
        </div>

        {/* Insight text */}
        <div className="px-5 py-4 flex items-start gap-3 flex-wrap">
          <span className={`${sentStyle.pill} text-xs font-bold px-3 py-1 rounded-full shrink-0 whitespace-nowrap`}>
            {sentStyle.label}
          </span>
          <p className="text-sm text-gray-800 leading-relaxed flex-1 min-w-0">{cleanText}</p>
        </div>

        {/* Disclaimer */}
        <div className="mx-0 px-5 py-2.5 bg-amber-50 border-t-0" style={{ borderLeft: '3px solid #F59E0B' }}>
          <p className="text-xs text-amber-800">
            ⚠️ For research and educational purposes only. Not investment advice. Do your own research before trading.
          </p>
        </div>
      </div>
    </div>
  )
}
