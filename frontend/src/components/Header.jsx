import { Tooltip, InfoIcon } from './Tooltip'

const REGIME_STYLES = {
  BULL    : { bg: 'bg-green-600',  label: 'BULLISH'  },
  NEUTRAL : { bg: 'bg-amber-500',  label: 'NEUTRAL'  },
  BEAR    : { bg: 'bg-red-600',    label: 'BEARISH'  },
}

const SENTIMENT_STYLES = {
  NEGATIVE : { pill: 'bg-red-100 text-red-600',    label: 'NEGATIVE' },
  POSITIVE : { pill: 'bg-green-100 text-green-700', label: 'POSITIVE' },
  NEUTRAL  : { pill: 'bg-amber-100 text-amber-700', label: 'NEUTRAL'  },
}

function getSentimentFromSummary(summary = '') {
  if (summary.startsWith('POSITIVE')) return 'POSITIVE'
  if (summary.startsWith('NEGATIVE')) return 'NEGATIVE'
  return 'NEUTRAL'
}

function stripSentimentLabel(summary = '') {
  return summary
    .replace(/^(POSITIVE|NEGATIVE|NEUTRAL)\s*[—-]\s*/i, '')
    .trim()
}

export function Header({ macro, sectorCounts }) {
  const regime      = macro?.regime ?? 'NEUTRAL'
  const regimeStyle = REGIME_STYLES[regime] ?? REGIME_STYLES.NEUTRAL
  const score       = macro?.final_score ?? '--'
  const scanDate    = macro?.scan_date
    ? new Date(macro.scan_date).toLocaleDateString('en-IN',
        { day: 'numeric', month: 'short', year: 'numeric' })
    : '--'
  const summary    = macro?.summary ?? ''
  const sentiment  = getSentimentFromSummary(summary)
  const sentStyle  = SENTIMENT_STYLES[sentiment]
  const cleanText  = stripSentimentLabel(summary)

  return (
    <div className="space-y-3">
      {/* ── 5 metric pills ── */}
      <div className="card p-0 overflow-hidden">
        <div className="grid grid-cols-2 sm:grid-cols-5 divide-y sm:divide-y-0 sm:divide-x divide-gray-100">

          {/* Market Sentiment */}
          <div className="flex flex-col items-center justify-center p-4 gap-2">
            <span className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">
              Market Sentiment
            </span>
            <span className={`${regimeStyle.bg} text-white text-sm font-bold px-4 py-1.5 rounded-full`}>
              {regimeStyle.label}
            </span>
          </div>

          {/* Market Score */}
          <div className="flex flex-col items-center justify-center p-4 gap-1">
            <div className="flex items-center gap-1">
              <span className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">
                Market Score
              </span>
              <Tooltip text="Combined score out of 100 based on Nifty trend, India VIX (fear gauge), and global macro signals. Above 65 = good conditions to trade. Below 35 = be cautious.">
                <InfoIcon />
              </Tooltip>
            </div>
            <span className="text-2xl font-bold text-gray-900">{score}/100</span>
            <span className="text-[11px] text-gray-400">Higher = better conditions</span>
          </div>

          {/* Last Updated */}
          <div className="flex flex-col items-center justify-center p-4 gap-1">
            <span className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">
              Last Updated
            </span>
            <span className="text-xl font-bold text-gray-900">{scanDate}</span>
            <span className="text-[11px] text-gray-400">Updates daily after market close</span>
          </div>

          {/* Sectors Strong */}
          <div className="flex flex-col items-center justify-center p-4 gap-1">
            <span className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">
              Sectors Strong
            </span>
            <span className="text-2xl font-bold text-green-600">
              {sectorCounts.strong}
            </span>
          </div>

          {/* Sectors Weak */}
          <div className="flex flex-col items-center justify-center p-4 gap-1">
            <span className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">
              Sectors Weak
            </span>
            <span className="text-2xl font-bold text-red-600">
              {sectorCounts.weak}
            </span>
          </div>

        </div>
      </div>

      {/* ── Market Insight box ── */}
      <div className="card overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-100 flex items-center gap-2">
          <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span className="text-[11px] uppercase tracking-wide text-gray-400 font-medium">
            Market Insight
          </span>
        </div>

        <div className="px-4 py-3 flex items-start gap-2 flex-wrap">
          <span className={`${sentStyle.pill} text-xs font-bold px-2.5 py-1 rounded-full shrink-0`}>
            {sentStyle.label}
          </span>
          <p className="text-sm text-gray-800 leading-relaxed">{cleanText}</p>
        </div>

        <div className="px-4 py-2 bg-amber-50 border-l-4 border-amber-500 mx-0">
          <p className="text-xs text-amber-800">
            ⚠️ For research and educational purposes only. Not investment advice.
            Do your own research before trading.
          </p>
        </div>
      </div>
    </div>
  )
}
