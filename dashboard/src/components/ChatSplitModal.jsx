import { useState, useRef, useEffect } from 'react'
import { X, Users, Sparkles, Wand2 } from 'lucide-react'
import { chatSplitDetect, chatSplitRender, libraryFileUrl } from '../api.js'

function DragRect({ label, color, box, onChange, containerRef }) {
  const dragging = useRef(null)
  const start = useRef({ x: 0, y: 0, box: null })

  function toPct(clientX, clientY) {
    const el = containerRef.current
    const r = el.getBoundingClientRect()
    return {
      x: Math.min(1, Math.max(0, (clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (clientY - r.top) / r.height)),
    }
  }

  function onDown(e, mode) {
    e.stopPropagation()
    e.preventDefault()
    dragging.current = mode
    const p = toPct(e.clientX, e.clientY)
    start.current = { x: p.x, y: p.y, box: { ...box } }
  }

  function onMove(e) {
    if (!dragging.current) return
    const p = toPct(e.clientX, e.clientY)
    const b = { ...start.current.box }
    if (dragging.current === 'move') {
      const dx = p.x - start.current.x
      const dy = p.y - start.current.y
      b.x = Math.min(1 - b.w, Math.max(0, b.x + dx))
      b.y = Math.min(1 - b.h, Math.max(0, b.y + dy))
    } else if (dragging.current === 'se') {
      b.w = Math.min(1 - b.x, Math.max(0.05, p.x - b.x))
      b.h = Math.min(1 - b.y, Math.max(0.05, p.y - b.y))
    }
    onChange(b)
  }

  function onUp() { dragging.current = null }

  useEffect(() => {
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [box])

  const style = {
    left: `${box.x * 100}%`,
    top: `${box.y * 100}%`,
    width: `${box.w * 100}%`,
    height: `${box.h * 100}%`,
    borderColor: color,
    background: `${color}22`,
  }

  return (
    <div
      className="absolute cursor-move rounded-lg border-2"
      style={style}
      onMouseDown={(e) => onDown(e, 'move')}
    >
      <span
        className="absolute -top-6 left-0 text-[10px] font-bold px-1.5 py-0.5 rounded"
        style={{ background: color, color: '#000' }}
      >
        {label}
      </span>
      <div
        className="absolute -bottom-1 -right-1 w-3 h-3 rounded-full border border-white"
        style={{ background: color }}
        onMouseDown={(e) => onDown(e, 'se')}
      />
    </div>
  )
}

export default function ChatSplitModal({ name, clip, onClose, onDone }) {
  const containerRef = useRef(null)
  const [person1, setPerson1] = useState({ x: 0.0, y: 0.0, w: 0.5, h: 0.5 })
  const [person2, setPerson2] = useState({ x: 0.5, y: 0.0, w: 0.5, h: 0.5 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const videoUrl = libraryFileUrl(name, clip.file)

  async function handleAutoDetect() {
    setBusy(true)
    setError('')
    try {
      const res = await chatSplitDetect(name, clip.file, 5)
      if (res.person1) setPerson1(res.person1)
      if (res.person2) setPerson2(res.person2)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleRender() {
    setBusy(true)
    setError('')
    try {
      const res = await chatSplitRender(name, clip.file, person1, person2)
      setResult(res)
      if (onDone) onDone(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#121214] border border-white/10 rounded-2xl w-full max-w-3xl p-6 relative max-h-[90vh] overflow-y-auto">
        <button onClick={onClose} className="absolute top-4 right-4 text-zinc-500 hover:text-white z-10">
          <X size={20} />
        </button>
        <h3 className="text-lg font-bold text-white mb-1 flex items-center gap-2">
          <Users size={18} className="text-purple-400" /> Chat Split — Dua Orang
        </h3>
        <p className="text-xs text-zinc-500 mb-4">
          Atur kotak untuk masing-masing orang. Hasil: orang 1 di atas, orang 2 di bawah (9:16).
        </p>

        {/* Preview canvas */}
        <div
          ref={containerRef}
          className="relative w-full aspect-video bg-black rounded-lg overflow-hidden border border-white/10 select-none"
        >
          <video
            src={videoUrl}
            className="w-full h-full object-contain bg-black pointer-events-none"
            autoPlay
            muted
            loop
            playsInline
          />
          <DragRect label="Orang 1" color="#a855f7" box={person1} onChange={setPerson1} containerRef={containerRef} />
          <DragRect label="Orang 2" color="#06b6d4" box={person2} onChange={setPerson2} containerRef={containerRef} />
        </div>

        {/* Auto Detect + Render */}
        <div className="flex gap-3 mt-5">
          <button
            onClick={handleAutoDetect}
            disabled={busy}
            className="flex-1 py-2.5 rounded-lg bg-white/10 text-white text-sm font-semibold
                       hover:bg-white/20 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <Sparkles size={15} /> Auto Detect
          </button>
          <button
            onClick={handleRender}
            disabled={busy}
            className="flex-1 py-2.5 rounded-lg bg-gradient-to-r from-purple-500 to-cyan-500 text-black font-bold
                       hover:from-purple-400 hover:to-cyan-400 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <Wand2 size={15} /> {busy ? 'Processing…' : 'Buat Split Screen'}
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 px-3 py-2 text-sm mt-4">
            {error}
          </div>
        )}

        {result && (
          <div className="rounded-lg border border-green-500/40 bg-green-500/10 px-3 py-3 mt-4">
            <p className="text-sm text-green-300 mb-2">Berhasil! Split screen:</p>
            <video
              src={libraryFileUrl(name, result.filename)}
              controls
              className="w-full rounded-lg bg-black mb-2"
            />
            <div className="flex gap-3">
              <a
                href={libraryFileUrl(name, result.filename)}
                download={result.filename}
                className="text-xs text-primary hover:underline"
              >
                Download
              </a>
              <button
                onClick={onClose}
                className="ml-auto px-3 py-1.5 rounded-lg bg-primary/20 text-primary text-xs hover:bg-primary/30"
              >
                Selesai
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
