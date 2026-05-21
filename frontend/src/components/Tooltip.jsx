export function Tooltip({ text, children }) {
  return (
    <div className="relative inline-flex items-center group">
      {children}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-60 bg-gray-900 text-white text-xs rounded-lg p-3 leading-relaxed z-50 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-150 shadow-xl">
        {text}
        <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
      </div>
    </div>
  )
}

export function InfoIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-gray-400 ml-1 cursor-help" fill="none"
      viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <circle cx="12" cy="12" r="10" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 16v-4M12 8h.01" />
    </svg>
  )
}
