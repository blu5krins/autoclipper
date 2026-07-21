import { useRef, useState } from 'react'
import { Link2, Upload, FileVideo, X, Sparkles, Scissors, LayoutGrid } from 'lucide-react'
import GamingLayoutModal from './GamingLayoutModal.jsx'
import { uploadFile, prepareGaming, getStatus, API_URL } from '../api.js'

export default function SubmitForm({ onSubmit, busy, settings }) {
  const [mode, setMode] = useState('url') // 'url' | 'upload'
  const [urlText, setUrlText] = useState('')
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadError, setUploadError] = useState('')
  const [dragActive, setDragActive] = useState(false)
  const [clipCount, setClipCount] = useState(settings?.clipCount ?? 8)
  const [minClip, setMinClip] = useState(settings?.minClip ?? 15)
  const [maxClip, setMaxClip] = useState(settings?.maxClip ?? 60)
  const [contentType, setContentType] = useState('general')
  const [showGaming, setShowGaming] = useState(false)
  const [gamingReady, setGamingReady] = useState(null) // { source, layout }
  const [splitScreen, setSplitScreen] = useState(false)
  const fileInput = useRef(null)

  const CONTENT_TYPES = [
    { id: 'general', label: 'General / Other' },
    { id: 'podcast', label: 'Podcast' },
    { id: 'gaming', label: 'Gaming' },
    { id: 'tutorial', label: 'Tutorial / How-To' },
    { id: 'irl', label: 'IRL / Live Stream' },
  ]

  const resolvedSource = mode === 'upload' ? (file ? file.name : '') : urlText.trim()
  const canSubmit =
    !busy && !uploading && (gamingReady ? true : !!resolvedSource)

  function handleFiles(files) {
    const f = files && files[0]
    if (!f) return
    setUploadError('')
    setFile(f)
  }

  function onDrop(e) {
    e.preventDefault()
    setDragActive(false)
    handleFiles(e.dataTransfer.files)
  }

  async function onPrepareGaming({ camBox, gameBox, layout, setBusy, setStage, setStageMsg }) {
    const useUrl = mode === 'url' && urlText.trim()
    if (!file && !useUrl) {
      setUploadError('Upload a gaming recording or paste a YouTube URL first.')
      return
    }
    try {
      setBusy(true)
      let source
      if (file) {
        const up = await uploadFile(file, (p) => setUploadProgress(p))
        source = { file: up.filename }
      } else {
        source = { source: urlText.trim() }
      }
      const res = await prepareGaming({
        ...source,
        camBox,
        gameBox,
        layout,
      })
      const jobId = res.job_id
      if (!jobId) {
        // Synchronous fallback (older backend)
        setGamingReady({ source: res.source, layout })
        setShowGaming(false)
        return
      }
      // Poll job status until done/error
      const deadline = Date.now() + 1000 * 60 * 30 // 30 min max
      let lastMsg = ''
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 3000))
        const st = await getStatus(jobId)
        if (setStage) setStage(st.status)
        const msg = (st.logs || []).slice(-1)[0] || ''
        if (setStageMsg) setStageMsg(msg || 'Working…')
        if (st.status === 'done') {
          setGamingReady({ source: st.result.source, layout, previewUrl: st.result.preview_url })
          setShowGaming(false)
          return
        }
        if (st.status === 'error') {
          throw new Error(st.error || 'Gaming prepare failed')
        }
      }
      throw new Error('Gaming prepare timed out — video may be too long/high-res')
    } catch (e) {
      setUploadError(e.message || 'Gaming prepare failed')
    } finally {
      setBusy(false)
    }
  }

  function submit() {
    if (!canSubmit) return
    const clipOpts = {
      clipCount: clipCount || undefined,
      minClip: minClip || undefined,
      maxClip: maxClip || undefined,
      splitScreen: splitScreen || undefined,
    }
    // Gaming: use the prepared 9:16 source instead of the raw file.
    if (contentType === 'gaming' && gamingReady) {
      onSubmit({ source: gamingReady.source, ...clipOpts, contentType })
      return
    }
    if (mode === 'upload') {
      setUploading(true)
      setUploadProgress(0)
      // Single-step: stream the file straight into /api/process with a progress bar.
      onSubmit({ file, ...clipOpts, contentType }, (p) => setUploadProgress(p), () => setUploading(false))
    } else {
      onSubmit({ source: urlText.trim(), ...clipOpts, contentType })
    }
  }

  return (
    <div className="bg-surface border border-border rounded-2xl p-6">
      {/* Tabs */}
      <div className="flex gap-4 mb-5 border-b border-border pb-3">
        <TabButton active={mode === 'url'} onClick={() => setMode('url')} icon={Link2}>
          URL / Path
        </TabButton>
        <TabButton active={mode === 'upload'} onClick={() => setMode('upload')} icon={Upload}>
          Upload File
        </TabButton>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        {mode === 'url' ? (
          <input
            type="text"
            value={urlText}
            onChange={(e) => setUrlText(e.target.value)}
            placeholder="YouTube URL or local video path (e.g. /videos/lecture.mp4)"
            className="w-full bg-background border border-border rounded-lg px-4 py-3 text-sm
                       placeholder-zinc-500 focus:outline-none focus:border-primary"
          />
        ) : (
          <div
            onClick={() => !file && !uploading && fileInput.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragActive(true)
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
            className={`flex flex-col items-center justify-center gap-3 border-2 border-dashed
                        rounded-xl px-4 py-10 cursor-pointer transition-colors
                        ${file ? 'border-primary/50 bg-primary/5' : dragActive ? 'border-primary bg-primary/10' : 'border-zinc-700 hover:border-zinc-500 bg-white/5'}`}
          >
            <input
              ref={fileInput}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
            {file ? (
              <div className="flex items-center gap-3 text-white">
                <FileVideo className="text-primary" size={20} />
                <span className="font-medium max-w-[280px] truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setFile(null)
                  }}
                  className="p-1 hover:bg-white/10 rounded-full disabled:opacity-40"
                  disabled={uploading}
                >
                  <X size={16} />
                </button>
              </div>
            ) : uploading ? (
              <div className="w-full max-w-sm">
                <p className="text-sm text-zinc-300 mb-2">Uploading… {uploadProgress}%</p>
                <div className="h-2 w-full bg-white/10 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-150"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            ) : (
              <>
                <Upload className="text-zinc-500" size={26} />
                <p className="text-sm text-zinc-400">Click to upload or drag and drop</p>
                <p className="text-xs text-zinc-600">MP4, MKV, MOV, WebM …</p>
              </>
            )}
          </div>
        )}

        {uploadError && <p className="mt-3 text-xs text-red-300">{uploadError}</p>}

        <div className="mt-5 border-t border-border pt-4">
          <div className="flex items-center gap-2 mb-3">
            <Scissors size={15} className="text-zinc-400" />
            <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">Clip Generation</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <SliderRow label="Clips" value={clipCount} min={1} max={30} step={1} unit="" onChange={setClipCount} />
            <RangeSlider
              label="Clip duration (sec)"
              min={5}
              max={300}
              step={1}
              low={minClip}
              high={maxClip}
              onChange={(lo, hi) => {
                setMinClip(lo)
                setMaxClip(hi)
              }}
            />
          </div>
        </div>

        <div className="mt-5 border-t border-border pt-4">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={15} className="text-zinc-400" />
            <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">Content Type</span>
          </div>
          <p className="text-xs text-zinc-500 mb-3">Helps AI pick the right viral moments for your niche.</p>
          <div className="flex flex-wrap gap-2">
            {CONTENT_TYPES.map((ct) => (
              <button
                key={ct.id}
                type="button"
                onClick={() => setContentType(ct.id)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  contentType === ct.id
                    ? 'bg-primary/20 border-primary text-primary'
                    : 'border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500'
                }`}
              >
                {ct.label}
              </button>
            ))}
          </div>

          {contentType === 'gaming' && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
              {gamingReady ? (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-amber-200">
                    ✓ Gaming video ready ({gamingReady.layout})
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowGaming(true)}
                    className="text-xs text-amber-300 hover:text-amber-100 underline"
                  >
                    Edit layout
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowGaming(true)}
                  disabled={!file && mode !== 'url'}
                  className="w-full flex items-center justify-center gap-2 text-xs font-bold text-amber-200
                             disabled:opacity-40 hover:text-amber-100 transition-colors"
                >
                  <LayoutGrid size={14} />{' '}
                  {file || (mode === 'url' && urlText.trim())
                    ? 'Setup Cam & Gameplay'
                    : 'Upload or paste a URL first'}
                </button>
              )}
            </div>
          )}

          {contentType === 'podcast' && (
            <div className="mt-3 flex items-center gap-2">
              <input
                id="splitScreen"
                type="checkbox"
                checked={splitScreen}
                onChange={(e) => setSplitScreen(e.target.checked)}
                className="accent-cyan-400"
              />
              <label htmlFor="splitScreen" className="text-xs text-zinc-300 cursor-pointer select-none">
                Split Screen <span className="text-zinc-500">(2 orang, atas/bawah)</span>
              </label>
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full mt-5 flex items-center justify-center gap-2 rounded-lg bg-primary
                     hover:bg-blue-600 disabled:opacity-50 text-white font-medium text-sm py-3
                     transition-colors"
        >
          {busy ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              {uploading ? `Uploading… ${uploadProgress}%` : 'Processing…'}
            </>
          ) : (
            <>
              <Sparkles size={16} />
              Generate Clips
            </>
          )}
        </button>
      </form>

      {showGaming && (
        <GamingLayoutModal
          videoUrl={file ? URL.createObjectURL(file) : mode === 'url' ? urlText.trim() : ''}
          onClose={() => setShowGaming(false)}
          onPrepare={onPrepareGaming}
        />
      )}
    </div>
  )
}

function TabButton({ active, onClick, icon: Icon, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 pb-2 px-1 transition-all ${
        active
          ? 'text-primary border-b-2 border-primary -mb-[13px]'
          : 'text-zinc-400 hover:text-white'
      }`}
    >
      <Icon size={16} />
      {children}
    </button>
  )
}

function SliderRow({ label, value, min, max, step, unit, onChange }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className="text-xs font-semibold text-zinc-200">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value ?? min}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        className="w-full accent-primary"
      />
    </div>
  )
}

function RangeSlider({ label, min, max, step, low, high, onChange }) {
  const lo = Math.min(low, high)
  const hi = Math.max(low, high)
  const pct = (v) => ((v - min) / (max - min)) * 100
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className="text-xs font-semibold text-zinc-200">
          {lo}s – {hi}s
        </span>
      </div>
      <div className="relative h-5">
        {/* Track */}
        <div className="absolute top-1/2 left-0 right-0 -translate-y-1/2 h-1.5 rounded-full bg-white/10" />
        {/* Selected range */}
        <div
          className="absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full bg-primary"
          style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={lo}
          onChange={(e) => onChange(Math.min(parseInt(e.target.value, 10), hi), hi)}
          className="range-thumb absolute inset-0 w-full appearance-none bg-transparent pointer-events-none"
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={hi}
          onChange={(e) => onChange(lo, Math.max(parseInt(e.target.value, 10), lo))}
          className="range-thumb absolute inset-0 w-full appearance-none bg-transparent pointer-events-none"
        />
      </div>
    </div>
  )
}
