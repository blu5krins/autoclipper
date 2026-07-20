import { useEffect, useRef } from 'react'

export default function LogConsole({ logs }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="bg-background border border-border rounded-lg p-3 h-64 overflow-y-auto font-mono text-xs text-zinc-400">
      {logs.length === 0 ? (
        <span className="text-zinc-600">Waiting for logs…</span>
      ) : (
        logs.map((line, i) => (
          <div key={i} className="whitespace-pre-wrap leading-relaxed">
            {line}
          </div>
        ))
      )}
      <div ref={endRef} />
    </div>
  )
}
