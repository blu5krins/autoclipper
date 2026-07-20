import { useEffect, useState, useMemo } from 'react'
import { X, Type, Loader2 } from 'lucide-react'
import { getSrt, parseSrt, applySubtitles, fileUrl } from '../api.js'

const FONT_OPTIONS = [
  { value: 'Verdana', label: 'Verdana' },
  { value: 'Arial', label: 'Arial' },
  { value: 'Impact', label: 'Impact' },
  { value: 'Helvetica', label: 'Helvetica' },
  { value: 'Georgia', label: 'Georgia' },
  { value: 'Courier New', label: 'Courier New' },
]

const TEXT_COLORS = [
  { color: '#FFFFFF', label: 'White' },
  { color: '#FFFF00', label: 'Yellow' },
  { color: '#00FFFF', label: 'Cyan' },
  { color: '#00FF00', label: 'Green' },
  { color: '#FF0000', label: 'Red' },
  { color: '#FF69B4', label: 'Pink' },
]

const HIGHLIGHT_COLORS = [
  { color: '#FFDD00', label: 'Gold' },
  { color: '#FF4444', label: 'Red' },
  { color: '#00FF88', label: 'Green' },
  { color: '#00BBFF', label: 'Blue' },
  { color: '#FF69B4', label: 'Pink' },
]

const DEFAULT_STYLE = {
  font: 'Arial',
  font_size: 80,
  text_color: '#FFFFFF',
  outline_color: '#000000',
  box_color: '#000000',
  box_opacity: 50,
  highlight_color: '#FFDD00',
  highlight: false,
  box: false,
  position: 'bottom',
  margin_v: 120,
}

export default function SubtitleEditor({ jobId, clip, onApply, onClose, srtUrl }) {
  const [cues, setCues] = useState([])
  const [style, setStyle] = useState(DEFAULT_STYLE)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)

  useEffect(() => {
    const url = srtUrl || (clip.srt ? getSrt(jobId, clip.srt) : null)
    if (!url) {
      setError('No subtitle track for this clip.')
      setLoaded(true)
      return
    }
    const p = typeof url === 'string' ? fetch(url).then((r) => r.text()) : url
    p.then((text) => {
      setCues(parseSrt(text))
      setLoaded(true)
    }).catch((e) => {
      setError(e.message)
      setLoaded(true)
    })
  }, [jobId, clip])

  function setStyleKey(key, value) {
    setStyle((s) => ({ ...s, [key]: value }))
  }

  // Whole-transcript editing: joined text <-> per-cue cues. OpenShorts style.
  const [fullText, setFullText] = useState('')
  useEffect(() => {
    if (loaded) setFullText(cues.map((c) => c.text).join(' '))
  }, [loaded]) // eslint-disable-line react-hooks/exhaustive-deps

  // Live "what the burn will look like" — rebuild cues from the edited text so
  // the preview updates as the user types (not just on Generate).
  const editedCues = useMemo(() => buildCuesFromText(fullText), [fullText]) // eslint-disable-line react-hooks/exhaustive-deps

  function buildCuesFromText(text) {
    const words = text.split(/\s+/).filter(Boolean)
    if (words.length === 0) return []
    if (cues.length === 0) return words.map((w) => ({ start: 0, end: 1, text: w }))
    // Redistribute words across the original cue time ranges.
    const totalWords = cues.reduce((n, c) => n + (c.text ? c.text.split(/\s+/).filter(Boolean).length : 0), 0) || 1
    const out = []
    let wi = 0
    for (const cue of cues) {
      const n = Math.max(1, Math.round(((cue.text ? cue.text.split(/\s+/).filter(Boolean).length : 1) / totalWords) * words.length))
      const slice = words.slice(wi, wi + n)
      wi += slice.length
      if (slice.length === 0) continue
      out.push({ start: cue.start, end: cue.end, text: slice.join(' ') })
    }
    // Append any leftovers to the last cue.
    if (wi < words.length && out.length > 0) {
      out[out.length - 1].text += ' ' + words.slice(wi).join(' ')
    }
    return out.length ? out : words.map((w) => ({ start: 0, end: 1, text: w }))
  }

  async function handleGenerate() {
    if (!clip.srt) return
    const editedCues = buildCuesFromText(fullText)
    setBusy(true)
    setError('')
    try {
      const res = await applySubtitles(jobId, clip.file, editedCues, style)
      onApply(clip.index, res.filename)
      onClose()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#121214] border border-white/10 rounded-2xl w-full max-w-5xl shadow-2xl relative flex flex-col md:flex-row gap-6 max-h-[90vh] overflow-hidden">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-zinc-500 hover:text-white z-10"
        >
          <X size={20} />
        </button>

        {/* Left: clip player with live subtitle overlay */}
        <div className="flex-1 flex flex-col items-center justify-center bg-black rounded-l-2xl border-r border-white/5 overflow-hidden relative aspect-[9/16] max-h-[600px]">
          <div className="relative w-full h-full">
            <video
              src={fileUrl(jobId, clip.file)}
              controls
              playsInline
              onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
              className="w-full h-full object-contain"
            />
            {/* SVG overlay — mirrors the ASS burn exactly (stroke = outline) */}
            <svg
              className="pointer-events-none absolute inset-0 w-full h-full"
              viewBox="0 0 1080 1920"
              preserveAspectRatio="xMidYMid meet"
            >
               {(() => {
                 const active = (editedCues.length ? editedCues : cues).find(
                   (c) => currentTime >= c.start && currentTime <= c.end
                 )
                if (!active) return null
                const outline = style.box ? 1 : 4
                const words = active.text.split(/\s+/).filter(Boolean)
                const span = Math.max(0.001, active.end - active.start)
                const progress = Math.min(1, Math.max(0, (currentTime - active.start) / span))
                const doneCount = style.highlight
                  ? Math.floor(progress * words.length + 0.0001)
                  : words.length
                const pos = (style.position || 'bottom').toLowerCase()
                const baseline =
                  pos === 'top' ? 'hanging' : pos === 'middle' ? 'middle' : 'alphabetic'
                const y =
                  pos === 'top'
                    ? style.margin_v
                    : pos === 'middle'
                    ? 960
                    : 1920 - style.margin_v
                const fontSize = style.font_size
                const fontWeight = 800

                return (
                  <g
                    fontFamily={style.font}
                    fontSize={fontSize}
                    fontWeight={fontWeight}
                    textAnchor="middle"
                    dominantBaseline={baseline}
                  >
                    {style.box && (
                      <text
                        x="540"
                        y={y}
                        fill={style.box_color}
                        fillOpacity={style.box_opacity / 100}
                        stroke="none"
                        style={{ paintOrder: 'stroke', stroke: style.box_color, strokeWidth: outline * 2 + fontSize * 0.25 }}
                      >
                        {active.text}
                      </text>
                    )}
                    <text
                      x="540"
                      y={y}
                      fill={style.text_color}
                      stroke={style.outline_color}
                      strokeWidth={outline * 2}
                      strokeLinejoin="round"
                      paintOrder="stroke"
                    >
                      {words.map((w, i) => (
                        <tspan key={i} fill={i < doneCount ? style.highlight_color : style.text_color} stroke="none">
                          {w}
                          {i < words.length - 1 ? ' ' : ''}
                        </tspan>
                      ))}
                    </text>
                  </g>
                )
              })()}
            </svg>
          </div>
        </div>

        {/* Right: controls */}
        <div className="w-full md:w-80 flex flex-col p-6">
          <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2 shrink-0">
            <Type className="text-primary" /> Auto Subtitles
          </h3>

          <div className="space-y-5 flex-1 overflow-y-auto pr-1">
            {/* Editable text (whole transcript) */}
            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 block">
                Text
              </label>
              <textarea
                value={fullText}
                onChange={(e) => setFullText(e.target.value)}
                rows={5}
                className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white
                           focus:outline-none focus:border-primary/50 resize-none leading-relaxed"
                placeholder="Edit subtitle text…"
              />
              {cues.length === 0 && (
                <div className="text-sm text-zinc-500 mt-1">No captions. The clip had no speech.</div>
              )}
            </div>

            {/* Font family */}
            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 block">
                Font Family
              </label>
              <select
                value={style.font}
                onChange={(e) => setStyleKey('font', e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-sm text-white
                           focus:outline-none focus:border-primary/50"
                style={{ fontFamily: style.font }}
              >
                {FONT_OPTIONS.map((f) => (
                  <option key={f.value} value={f.value} style={{ fontFamily: f.value }}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Font size */}
            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 block">
                Font Size
              </label>
              <div className="flex items-center gap-3">
                <span className="text-[10px] text-zinc-500 w-10 text-right">{style.font_size}px</span>
                <input
                  type="range"
                  min="20"
                  max="80"
                  value={style.font_size}
                  onChange={(e) => setStyleKey('font_size', Number(e.target.value))}
                  className="flex-1 accent-primary"
                />
              </div>
            </div>

            {/* Position */}
            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 block">
                Position
              </label>
              <div className="flex gap-2">
                {['top', 'middle', 'bottom'].map((p) => (
                  <button
                    key={p}
                    onClick={() => setStyleKey('position', p)}
                    className={`flex-1 text-xs px-3 py-1.5 rounded-lg capitalize transition-colors ${
                      style.position === p
                        ? 'bg-primary text-white'
                        : 'bg-white/5 text-zinc-300 hover:bg-white/10'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            {/* Text color */}
            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 block">
                Text Color
              </label>
              <div className="flex flex-wrap gap-2 items-center">
                {TEXT_COLORS.map((c) => (
                  <button
                    key={c.color}
                    onClick={() => setStyleKey('text_color', c.color)}
                    className={`w-7 h-7 rounded-full border-2 transition-all ${
                      style.text_color === c.color ? 'border-white scale-110' : 'border-white/20 hover:border-white/50'
                    }`}
                    style={{ backgroundColor: c.color }}
                    title={c.label}
                  />
                ))}
                <label className="w-7 h-7 rounded-full border-2 border-dashed border-white/20 cursor-pointer flex items-center justify-center hover:border-white/50 overflow-hidden relative">
                  <span className="text-[10px] text-zinc-400">+</span>
                  <input
                    type="color"
                    value={style.text_color}
                    onChange={(e) => setStyleKey('text_color', e.target.value)}
                    className="absolute inset-0 opacity-0 cursor-pointer"
                  />
                </label>
              </div>
            </div>

            {/* Highlight color */}
            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 block">
                Highlight Color
              </label>
              <div className="flex flex-wrap gap-2">
                {HIGHLIGHT_COLORS.map((c) => (
                  <button
                    key={c.color}
                    onClick={() => setStyleKey('highlight_color', c.color)}
                    className={`w-7 h-7 rounded-full border-2 transition-all ${
                      style.highlight_color === c.color ? 'border-white scale-110' : 'border-white/20 hover:border-white/50'
                    }`}
                    style={{ backgroundColor: c.color }}
                    title={c.label}
                  />
                ))}
              </div>
              <label className="flex items-center gap-2 mt-2 text-xs text-zinc-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={style.highlight}
                  onChange={(e) => setStyleKey('highlight', e.target.checked)}
                  className="accent-primary w-4 h-4"
                />
                Word highlight
              </label>
            </div>

            {/* Box background */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Box</label>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={style.box}
                    onChange={(e) => setStyleKey('box', e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-8 h-4 bg-zinc-700 rounded-full peer-checked:bg-primary after:content-[''] after:absolute after:top-0 after:left-0 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4"></div>
                </label>
              </div>
              {style.box && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <label className="relative w-8 h-8 rounded-lg border border-white/10 cursor-pointer overflow-hidden shrink-0">
                      <div className="w-full h-full" style={{ backgroundColor: style.box_color }} />
                      <input
                        type="color"
                        value={style.box_color}
                        onChange={(e) => setStyleKey('box_color', e.target.value)}
                        className="absolute inset-0 opacity-0 cursor-pointer"
                      />
                    </label>
                    <div className="flex-1">
                      <input
                        type="range"
                        min="10"
                        max="100"
                        value={style.box_opacity}
                        onChange={(e) => setStyleKey('box_opacity', Number(e.target.value))}
                        className="w-full accent-primary"
                      />
                      <div className="flex justify-between text-[10px] text-zinc-500">
                        <span>Transparent</span>
                        <span>{style.box_opacity}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Outline / border color */}
            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 block">
                Outline Color
              </label>
              <label className="relative w-8 h-8 rounded-lg border border-white/10 cursor-pointer overflow-hidden inline-block">
                <div className="w-full h-full" style={{ backgroundColor: style.outline_color }} />
                <input
                  type="color"
                  value={style.outline_color}
                  onChange={(e) => setStyleKey('outline_color', e.target.value)}
                  className="absolute inset-0 opacity-0 cursor-pointer"
                />
              </label>
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={busy || cues.length === 0}
            className="w-full py-3 mt-4 bg-gradient-to-r from-yellow-500 to-orange-500 hover:from-yellow-400 hover:to-orange-400 text-black font-bold rounded-xl shadow-lg transition-all active:scale-[0.98] flex items-center justify-center gap-2 shrink-0 disabled:opacity-50"
          >
            {busy ? <Loader2 size={20} className="animate-spin" /> : <Type size={20} />}
            {busy ? 'Generating…' : 'Generate Subtitles'}
          </button>
          {error && <div className="mt-2 text-sm text-red-300">{error}</div>}
        </div>
      </div>
    </div>
  )
}
