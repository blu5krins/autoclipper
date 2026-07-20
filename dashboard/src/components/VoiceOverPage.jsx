import { useState } from 'react'
import { AudioLines, Play, Loader2, Scissors } from 'lucide-react'
import { applyVoiceOver, previewVoiceOver, voiceOverFileUrl } from '../api.js'

const KOKORO_VOICES = [
  'af_heart', 'af_alloy', 'af_bella', 'af_nova', 'af_sarah', 'af_sky',
  'am_michael', 'am_puck', 'am_zeno',
  'bf_alice', 'bf_emma', 'bm_daniel', 'bm_george', 'bm_leo',
]
const GEMINI_VOICES = [
  'en-US-Chirp3-HD-Aoede', 'en-US-Chirp3-HD-Autonoe', 'en-GB-Chirp3-HD-Alnilam',
  'id-ID-Standard-A', 'id-ID-Standard-B', 'id-ID-Wavenet-A',
]

export default function VoiceOverPage({ initialTarget }) {
  const [source, setSource] = useState(
    initialTarget?.jobId
      ? { type: 'job', jobId: initialTarget.jobId, filename: initialTarget.filename || '' }
      : initialTarget?.name
      ? { type: 'library', name: initialTarget.name, filename: initialTarget.filename || '' }
      : { type: 'job', jobId: '', filename: '' }
  )
  const [text, setText] = useState(initialTarget?.hook || '')
  const [engine, setEngine] = useState('auto')
  const [voice, setVoice] = useState('')
  const [mode, setMode] = useState('overlay')
  const [busy, setBusy] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const voiceList = engine === 'gemini' ? GEMINI_VOICES : engine === 'kokoro' ? KOKORO_VOICES : KOKORO_VOICES

  async function handlePreview() {
    setError('')
    if (!text.trim()) return setError('Teks voice-over kosong.')
    if (!source.jobId && !source.name) return setError('Pilih sumber klip (Job ID atau Library name).')
    if (!source.filename) return setError('Nama file klip diperlukan.')
    setBusy(true)
    try {
      const url = await previewVoiceOver({
        job_id: source.type === 'job' ? source.jobId : undefined,
        name: source.type === 'library' ? source.name : undefined,
        filename: source.filename,
        text,
        engine,
        voice: voice || undefined,
        mode,
      })
      setPreviewUrl(url)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleBurn() {
    setError('')
    if (!text.trim()) return setError('Teks voice-over kosong.')
    if (!source.jobId && !source.name) return setError('Pilih sumber klip.')
    if (!source.filename) return setError('Nama file klip diperlukan.')
    setBusy(true)
    try {
      const res = await applyVoiceOver({
        job_id: source.type === 'job' ? source.jobId : undefined,
        name: source.type === 'library' ? source.name : undefined,
        filename: source.filename,
        text,
        engine,
        voice: voice || undefined,
        mode,
      })
      setResult(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-9 h-9 bg-primary/20 rounded-lg flex items-center justify-center">
          <AudioLines size={18} className="text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white">Voice-Over</h1>
          <p className="text-zinc-400 text-sm">Tambahkan narasi audio ke klip (Kokoro lokal + Gemini untuk Indo).</p>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-xl p-5 space-y-5">
        {/* Source */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider mb-3">Sumber Klip</h2>
          <div className="flex gap-2 mb-3">
            {['job', 'library'].map((t) => (
              <button
                key={t}
                onClick={() => setSource({ type: t, jobId: '', name: '', filename: '' })}
                className={`px-3 py-1.5 rounded-lg text-sm ${
                  source.type === t ? 'bg-primary text-background' : 'bg-background text-zinc-400'
                }`}
              >
                {t === 'job' ? 'Job ID' : 'Library'}
              </button>
            ))}
          </div>
          {source.type === 'job' ? (
            <input
              value={source.jobId}
              onChange={(e) => setSource({ ...source, jobId: e.target.value })}
              placeholder="job_id (mis. abad3b2c6b1d)"
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-primary"
            />
          ) : (
            <input
              value={source.name}
              onChange={(e) => setSource({ ...source, name: e.target.value })}
              placeholder="library name (folder di Saved Library)"
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-primary"
            />
          )}
          <input
            value={source.filename}
            onChange={(e) => setSource({ ...source, filename: e.target.value })}
            placeholder="nama file klip (mis. clip1_9x16.mp4)"
            className="w-full mt-2 bg-background border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-primary"
          />
        </section>

        {/* Text */}
        <section className="border-t border-border pt-5">
          <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider mb-3">Teks</h2>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder="Teks yang akan dibacakan. Kosongkan untuk pakai hook klip, atau tempel subtitle untuk dub penuh."
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-primary resize-y"
          />
        </section>

        {/* Engine / voice / mode */}
        <section className="border-t border-border pt-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Engine</label>
            <select
              value={engine}
              onChange={(e) => { setEngine(e.target.value); setVoice('') }}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-primary"
            >
              <option value="auto">Auto (recommended)</option>
              <option value="kokoro">Kokoro (lokal)</option>
              <option value="gemini">Gemini (Indo)</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Voice</label>
            <select
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-primary"
            >
              <option value="">Default</option>
              {voiceList.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Mode</label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-primary"
            >
              <option value="overlay">Overlay (mix)</option>
              <option value="replace">Replace (dub)</option>
            </select>
          </div>
        </section>

        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={handlePreview}
            disabled={busy}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-background border border-border text-white text-sm disabled:opacity-50"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            Preview
          </button>
          <button
            onClick={handleBurn}
            disabled={busy}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary hover:bg-blue-600 text-white text-sm font-medium disabled:opacity-50"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Scissors size={15} />}
            Burn Voice-Over
          </button>
        </div>

        {previewUrl && (
          <div className="border-t border-border pt-5">
            <p className="text-xs text-zinc-400 mb-2">Preview audio:</p>
            <audio controls src={previewUrl} className="w-full" />
          </div>
        )}

        {result && (
          <div className="border-t border-border pt-5">
            <p className="text-sm text-green-300 mb-2">Berhasil! Klip dengan voice-over:</p>
            <video
              src={voiceOverFileUrl(source.type === 'job' ? source.jobId : null, source.type === 'library' ? source.name : null, result.filename)}
              controls
              className="w-full rounded-lg bg-black"
            />
            <a
              href={voiceOverFileUrl(source.type === 'job' ? source.jobId : null, source.type === 'library' ? source.name : null, result.filename)}
              download={result.filename}
              className="text-xs text-primary hover:underline mt-2 inline-block"
            >
              Download {result.filename}
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
