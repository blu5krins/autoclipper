import { useState, useEffect } from 'react'
import { Download, Type, FileText, Bookmark, Sparkles, Youtube } from 'lucide-react'
import { fileUrl, saveToLibrary, applyHook, hookPreview, API_URL } from '../api.js'
import SubtitleEditor from './SubtitleEditor.jsx'
import YouTubeUploadModal from './YouTubeUploadModal.jsx'

export default function ClipGrid({ jobId, clips, onApply }) {
  return (
    <section>
      <h2 className="text-lg font-semibold mb-3">
        {clips.length} clip{clips.length > 1 ? 's' : ''} generated
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {clips.map((clip) => (
          <ClipCard key={clip.index} jobId={jobId} clip={clip} onApply={onApply} />
        ))}
      </div>
    </section>
  )
}

function ClipCard({ jobId, clip, onApply }) {
  const [editing, setEditing] = useState(false)
  const [showCaption, setShowCaption] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [hooking, setHooking] = useState(false)
  const [uploading, setUploading] = useState(false)
  const url = fileUrl(jobId, clip.file)

  async function handleSave() {
    setSaving(true)
    setSavedMsg('')
    try {
      const res = await saveToLibrary({
        jobId,
        filename: clip.file,
        clipTitle: clip.title,
        description: clip.description,
        hook: clip.hook,
      })
      setSavedMsg(`Saved to ${res.folder}`)
    } catch (e) {
      setSavedMsg(e.message)
    } finally {
      setSaving(false)
      setTimeout(() => setSavedMsg(''), 4000)
    }
  }

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden flex flex-col">
      <div className="relative bg-black">
        <video
          src={url}
          controls
          preload="metadata"
          className="w-full aspect-[9/16] object-contain bg-black"
        />
        <span className="absolute top-2 left-2 bg-black/60 text-white text-[10px] font-bold px-2 py-1 rounded-md uppercase tracking-wide">
          Clip {clip.index}
        </span>
      </div>

      <div className="p-3 flex-1 flex flex-col">
        <div className="text-sm font-semibold text-zinc-100 line-clamp-2">
          {clip.title || `Clip ${clip.index}`}
        </div>
        <div className="text-xs text-zinc-500 mt-1">
          {clip.start?.toFixed(1)}s – {clip.end?.toFixed(1)}s
        </div>

        {(clip.description || clip.hook) && (
          <button
            onClick={() => setShowCaption((v) => !v)}
            className="mt-2 text-left text-xs text-zinc-400 hover:text-zinc-200 flex items-center gap-1"
          >
            <FileText size={13} /> {showCaption ? 'Hide caption' : 'View caption'}
          </button>
        )}

        {showCaption && (clip.description || clip.hook) && (
          <div className="mt-2 space-y-2">
            {clip.hook && (
              <div className="bg-black/20 rounded-lg p-2 border border-white/5">
                <div className="text-[10px] font-bold text-amber-400 mb-1 uppercase tracking-wider">Hook</div>
                <p className="text-xs text-zinc-300 break-words">{clip.hook}</p>
              </div>
            )}
            {clip.description && (
              <div className="bg-black/20 rounded-lg p-2 border border-white/5">
                <div className="text-[10px] font-bold text-cyan-400 mb-1 uppercase tracking-wider">Caption</div>
                <p className="text-xs text-zinc-300 break-words whitespace-pre-wrap">{clip.description}</p>
              </div>
            )}
          </div>
        )}

        <div className="flex gap-2 mt-3">
          <button
            onClick={() => setEditing(true)}
            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-accent/20 text-accent
                       hover:bg-accent/30 transition-colors flex items-center justify-center gap-1"
          >
            <Type size={13} /> Auto Subtitle
          </button>
          <button
            onClick={() => setHooking(true)}
            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-amber-500/15 text-amber-300
                       hover:bg-amber-500/25 transition-colors flex items-center justify-center gap-1"
          >
            <Sparkles size={13} /> Add Hook
          </button>
        </div>
        <div className="flex gap-2 mt-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-white/5 text-zinc-300
                       hover:bg-white/10 transition-colors flex items-center justify-center gap-1 disabled:opacity-50"
          >
            <Bookmark size={13} /> {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={() => setUploading(true)}
            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-red-600/15 text-red-400
                       hover:bg-red-600/25 transition-colors flex items-center justify-center gap-1"
          >
            <Youtube size={13} /> YouTube
          </button>
        </div>
        <a
          href={url}
          download={clip.file}
          className="mt-2 text-center text-xs px-3 py-1.5 rounded-lg bg-primary/20 text-primary
                     hover:bg-primary/30 transition-colors flex items-center justify-center gap-1"
        >
          <Download size={13} /> Download
        </a>
        {savedMsg && <div className="mt-2 text-xs text-green-300">{savedMsg}</div>}
      </div>

      {editing && (
        <SubtitleEditor jobId={jobId} clip={clip} onApply={onApply} onClose={() => setEditing(false)} />
      )}

      {hooking && (
        <HookModal
          clip={clip}
          jobId={jobId}
          filename={clip.file}
          onClose={() => setHooking(false)}
          onApply={async (text, position, fontScale, opts) => {
            const res = await applyHook(jobId, clip.file, text, position, fontScale, opts)
            onApply && onApply(clip.index, res.filename)
            setHooking(false)
          }}
        />
      )}

      {uploading && (
        <YouTubeUploadModal
          source={{
            jobId,
            filename: clip.file,
            title: clip.title,
            description: clip.description,
          }}
          onClose={() => setUploading(false)}
          onDone={() => setUploading(false)}
        />
      )}
    </div>
  )
}

function HookModal({ clip, jobId, filename, onClose, onApply }) {
  const [text, setText] = useState(clip.hook || '')
  const [position, setPosition] = useState('top')
  const [size, setSize] = useState('M')
  const [entrance, setEntrance] = useState('fade')
  const [holdSeconds, setHoldSeconds] = useState(5)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [previewUrl, setPreviewUrl] = useState(null)

  const videoSrc = jobId && filename ? `${API_URL}/api/files/${jobId}/${filename}` : ''

  async function updatePreview() {
    if (!text.trim() || !jobId || !filename) {
      setPreviewUrl(null)
      return
    }
    try {
      const url = await hookPreview(jobId, filename, text, position, 1.0, { size })
      setPreviewUrl(url)
    } catch {
      setPreviewUrl(null)
    }
  }

  useEffect(() => {
    let active = true
    if (active) updatePreview()
    return () => { active = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, position, size])

  async function submit() {
    if (!text.trim()) {
      setError('Hook text is required')
      return
    }
    setBusy(true)
    setError('')
    try {
      await onApply(text, position, 1.0, { size, entrance, holdSeconds })
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  const posClass =
    position === 'center' ? 'items-center justify-center'
    : position === 'bottom' ? 'items-center justify-end pb-[20%]'
    : 'items-center justify-start pt-[20%]'

  const sizeStyle =
    size === 'S' ? { fontSize: '14px', maxWidth: '80%' }
    : size === 'L' ? { fontSize: '24px', maxWidth: '95%' }
    : { fontSize: '18px', maxWidth: '90%' }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#121214] border border-white/10 rounded-2xl w-full max-w-4xl p-6 relative flex flex-col md:flex-row gap-6 max-h-[90vh]">
        <button onClick={onClose} className="absolute top-4 right-4 text-zinc-500 hover:text-white z-10">✕</button>

        {/* Left: Preview */}
        <div className="flex-1 flex flex-col items-center justify-center bg-black rounded-lg border border-white/5 overflow-hidden relative aspect-[9/16] max-h-[600px]">
          {videoSrc ? (
            <>
              <video src={videoSrc} className="w-full h-full object-contain opacity-50" muted playsInline />
              <div className={`absolute w-full px-8 text-center pointer-events-none flex flex-col h-full ${posClass}`}>
                <div
                  className="text-black font-bold px-3 py-2 rounded-xl shadow-2xl text-center whitespace-pre-wrap"
                  style={{
                    ...sizeStyle,
                    backgroundColor: 'rgba(255, 255, 255, 0.82)',
                    fontFamily: 'Noto Serif, serif',
                    boxShadow: '0 4px 15px rgba(0,0,0,0.5)',
                    paddingTop: '10px', paddingBottom: '10px',
                    paddingLeft: '12px', paddingRight: '12px',
                  }}
                >
                  {text || 'Enter your text…'}
                </div>
              </div>
            </>
          ) : previewUrl ? (
            <img src={previewUrl} alt="hook preview" className="max-h-full object-contain" />
          ) : null}
        </div>

        {/* Right: Controls */}
        <div className="w-full md:w-80 flex flex-col">
          <h3 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
            <Sparkles size={16} className="text-amber-300" /> Viral Hook
          </h3>

          <div className="space-y-6 flex-1 overflow-y-auto pr-2">
            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3 block">Text</label>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                className="w-full bg-black/40 border border-white/10 rounded-lg p-3 text-white placeholder-zinc-600
                           focus:outline-none focus:border-amber-400/50 resize-none font-serif"
                placeholder="Enter text that will stop the scroll…"
              />
            </div>

            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3 block">Position</label>
              <div className="grid grid-cols-3 gap-2">
                {['top', 'center', 'bottom'].map((p) => (
                  <button
                    key={p}
                    onClick={() => setPosition(p)}
                    className={`py-2 px-1 rounded-lg text-xs font-bold capitalize transition-all border ${
                      position === p ? 'bg-white text-black border-white' : 'bg-white/5 text-zinc-400 border-white/5 hover:bg-white/10'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3 block">Size</label>
              <div className="grid grid-cols-3 gap-2">
                {['S', 'M', 'L'].map((sz) => (
                  <button
                    key={sz}
                    onClick={() => setSize(sz)}
                    className={`py-2 px-1 rounded-lg text-xs font-bold transition-all border ${
                      size === sz ? 'bg-white text-black border-white' : 'bg-white/5 text-zinc-400 border-white/5 hover:bg-white/10'
                    }`}
                  >
                    {sz === 'S' ? 'Small' : sz === 'M' ? 'Medium' : 'Large'}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3 block">Entrance</label>
              <div className="grid grid-cols-2 gap-2">
                {[['fade', 'Fade'], ['none', 'None']].map(([val, label]) => (
                  <button
                    key={val}
                    onClick={() => setEntrance(val)}
                    className={`py-2 px-1 rounded-lg text-xs font-bold transition-all border ${
                      entrance === val ? 'bg-white text-black border-white' : 'bg-white/5 text-zinc-400 border-white/5 hover:bg-white/10'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2 block">
                Duration: {holdSeconds}s
              </label>
              <input
                type="range"
                min="2"
                max="15"
                value={holdSeconds}
                onChange={(e) => setHoldSeconds(parseInt(e.target.value, 10))}
                className="w-full accent-amber-400"
              />
              <div className="flex justify-between text-[10px] text-zinc-500">
                <span>2s</span>
                <span>15s</span>
              </div>
            </div>
          </div>

          <button
            onClick={submit}
            disabled={busy || !text.trim()}
            className="w-full py-4 mt-4 bg-gradient-to-r from-amber-500 to-orange-500 text-black font-bold rounded-lg
                       hover:from-amber-400 hover:to-orange-400 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {busy ? 'Rendering…' : 'Add Hook'}
          </button>
        </div>
      </div>
    </div>
  )
}
