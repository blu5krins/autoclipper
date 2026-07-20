import { useState, useRef, useEffect } from 'react'
import { X, LayoutGrid, Video, MoveVertical } from 'lucide-react'

// Simple draggable rectangle overlay on top of a preview frame.
function DragRect({ label, color, box, onChange, containerRef, aspectHint }) {
  const dragging = useRef(null) // 'move' | 'se' | null
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

  function onUp() {
    dragging.current = null
  }

  useEffect(() => {
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

export default function GamingLayoutModal({ videoUrl, onClose, onPrepare }) {
  const containerRef = useRef(null)
  const [camBox, setCamBox] = useState({ x: 0.1, y: 0.05, w: 0.35, h: 0.35 })
  const [gameBox, setGameBox] = useState({ x: 0.05, y: 0.45, w: 0.9, h: 0.5 })
  const [layout, setLayout] = useState('cam_top')
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState(null)
  const [stageMsg, setStageMsg] = useState('')

  const layouts = [
    { id: 'cam_top', label: 'Cam Top / Game Bottom' },
    { id: 'game_top', label: 'Game Top / Cam Bottom' },
    { id: 'side', label: 'Side by Side' },
  ]

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#121214] border border-white/10 rounded-2xl w-full max-w-3xl p-6 relative max-h-[90vh] overflow-y-auto">
        <button onClick={onClose} className="absolute top-4 right-4 text-zinc-500 hover:text-white z-10">
          <X size={20} />
        </button>
        <h3 className="text-lg font-bold text-white mb-1 flex items-center gap-2">
          <LayoutGrid size={18} className="text-amber-300" /> Gaming Layout — Select Cam & Gameplay
        </h3>
        <p className="text-xs text-zinc-500 mb-4">
          Drag the boxes over the webcam (amber) and the gameplay (blue). The result is a 9:16 vertical video.
        </p>

        {/* Preview canvas */}
        <div
          ref={containerRef}
          className="relative w-full aspect-video bg-black rounded-lg overflow-hidden border border-white/10 select-none"
        >
          {videoUrl ? (
            isYouTubeUrl(videoUrl) ? (
              <iframe
                src={`${toEmbedUrl(videoUrl)}?autoplay=1&mute=1&rel=0`}
                className="w-full h-full pointer-events-none"
                allow="autoplay; encrypted-media; fullscreen"
                allowFullScreen
                title="YouTube preview"
              />
            ) : (
              <video
                src={videoUrl}
                className="w-full h-full object-contain bg-black pointer-events-none"
                autoPlay
                muted
                loop
                playsInline
              />
            )
          ) : (
            <div className="w-full h-full flex items-center justify-center text-zinc-600 text-sm">
              No preview available
            </div>
          )}
          <DragRect label="CAM" color="#f59e0b" box={camBox} onChange={setCamBox} containerRef={containerRef} />
          <DragRect label="GAME" color="#3b82f6" box={gameBox} onChange={setGameBox} containerRef={containerRef} />
        </div>

        {/* Layout selector */}
        <div className="mt-4">
          <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            <MoveVertical size={12} /> Layout
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {layouts.map((l) => (
              <button
                key={l.id}
                onClick={() => setLayout(l.id)}
                className={`py-2 px-2 rounded-lg text-xs font-bold transition-all border ${
                  layout === l.id ? 'bg-white text-black border-white' : 'bg-white/5 text-zinc-400 border-white/5 hover:bg-white/10'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={() => onPrepare({ camBox, gameBox, layout, setBusy, setStage, setStageMsg })}
          disabled={busy}
          className="w-full mt-5 py-3 rounded-lg bg-gradient-to-r from-amber-500 to-orange-500 text-black font-bold
                     hover:from-amber-400 hover:to-orange-400 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {busy ? (
            <>
              <span className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
              {stage && stage !== 'queued' ? `${stage}…` : 'Preparing…'}
            </>
          ) : (
            <>
              <Video size={16} /> Prepare Gaming Video
            </>
          )}
        </button>
        {busy && stageMsg && (
          <p className="mt-2 text-center text-[11px] text-amber-200/80">{stageMsg}</p>
        )}
      </div>
    </div>
  )
}

function isYouTubeUrl(url) {
  return /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\//i.test(url || '')
}

function toEmbedUrl(url) {
  // Convert watch / youtu.be / shorts URLs to an embeddable iframe URL.
  let id = null
  const u = url || ''
  const watch = u.match(/[?&]v=([^&]+)/)
  const short = u.match(/youtu\.be\/([^?&/]+)/)
  const shorts = u.match(/shorts\/([^?&/]+)/)
  if (watch) id = watch[1]
  else if (short) id = short[1]
  else if (shorts) id = shorts[1]
  if (!id) return u
  return `https://www.youtube.com/embed/${id}`
}
