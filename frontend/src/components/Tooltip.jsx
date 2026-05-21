import { useState, useRef } from 'react'

export function Tooltip({ text }) {
  const [pos, setPos] = useState(null)
  const ref           = useRef(null)

  function show() {
    if (ref.current) {
      const r = ref.current.getBoundingClientRect()
      setPos({ top: r.top + window.scrollY, left: r.left + r.width / 2 })
    }
  }

  return (
    <>
      <span
        ref={ref}
        onMouseEnter={show}
        onMouseLeave={() => setPos(null)}
        onClick={() => pos ? setPos(null) : show()}
        className="inline-flex items-center justify-center w-[15px] h-[15px] ml-1 rounded-full border border-gray-300 text-gray-400 text-[9px] font-bold cursor-help select-none flex-shrink-0 align-middle"
      >
        i
      </span>

      {pos && (
        <div
          className="fixed z-[9999] pointer-events-none"
          style={{
            top      : pos.top - 8,
            left     : pos.left,
            transform: 'translate(-50%, -100%)',
          }}
        >
          <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2.5 leading-relaxed shadow-2xl"
            style={{ width: '220px' }}>
            {text}
          </div>
          <div className="flex justify-center">
            <div style={{
              width: 0, height: 0,
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderTop: '5px solid #111827',
            }} />
          </div>
        </div>
      )}
    </>
  )
}
