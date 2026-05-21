import { useState, useRef } from 'react'

export function Tooltip({ text }) {
  const [pos, setPos]   = useState(null)
  const iconRef         = useRef(null)

  function handleEnter() {
    if (iconRef.current) {
      const rect = iconRef.current.getBoundingClientRect()
      setPos({
        top : rect.top + window.scrollY - 8,
        left: rect.left + rect.width / 2,
      })
    }
  }

  function handleLeave() {
    setPos(null)
  }

  return (
    <>
      <span
        ref={iconRef}
        className="inline-flex items-center justify-center w-[15px] h-[15px] ml-1 rounded-full border border-gray-300 text-gray-400 text-[9px] font-bold cursor-help select-none flex-shrink-0"
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        onClick={() => pos ? setPos(null) : handleEnter()}
      >
        i
      </span>

      {pos && (
        <div
          className="fixed z-[9999] pointer-events-none"
          style={{
            top     : pos.top,
            left    : pos.left,
            transform: 'translate(-50%, -100%)',
          }}
        >
          <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2.5 leading-relaxed shadow-2xl w-56">
            {text}
          </div>
          <div className="flex justify-center">
            <div className="border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-gray-900 w-0 h-0" />
          </div>
        </div>
      )}
    </>
  )
}
