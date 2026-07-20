import { useEffect, useRef, useState } from 'react'
import { LayoutDashboard, FolderOpen, Scissors, Settings as SettingsIcon, Flame } from 'lucide-react'
import { submitJob, getStatus } from './api.js'
import SubmitForm from './components/SubmitForm.jsx'
import LogConsole from './components/LogConsole.jsx'
import ClipGrid from './components/ClipGrid.jsx'
import Library from './components/Library.jsx'
import SettingsPage from './components/SettingsPage.jsx'
import TrendingPage from './components/TrendingPage.jsx'

const DEFAULT_SETTINGS = {
  groqKey: '',
  geminiKey: '',
  youtubeApiKey: '',
  whisperModel: '',
  geminiModel: '',
  vertical: true,
  useYolo: true,
  subtitles: true,
  forceHd: false,
  youtubeCookies: '',
  clipCount: 8,
  minClip: 15,
  maxClip: 60,
}

function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem('ac_settings') || '{}') }
  } catch {
    return DEFAULT_SETTINGS
  }
}

export default function App() {
  const [tab, setTab] = useState('generator')
  const [settings, setSettings] = useState(loadSettings)
  const [job, setJob] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pollRef = useRef(null)

  useEffect(() => {
    localStorage.setItem('ac_settings', JSON.stringify(settings))
  }, [settings])

  useEffect(() => () => clearInterval(pollRef.current), [])

  async function startPolling(jobId) {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await getStatus(jobId)
        setJob(s)
        if (s.status === 'completed' || s.status === 'failed') {
          clearInterval(pollRef.current)
          setBusy(false)
        }
      } catch (e) {
        clearInterval(pollRef.current)
        setBusy(false)
        setError(e.message)
      }
    }, 1500)
  }

  async function handleSubmit(payload, onProgress, onUploadEnd) {
    setError('')
    setBusy(true)
    setJob(null)
    const opts = {
      vertical: settings.vertical,
      use_yolo: settings.useYolo,
      subtitles: settings.subtitles,
      force_hd: settings.forceHd,
    }
    if (settings.youtubeCookies && settings.youtubeCookies.trim()) {
      opts.youtube_cookies = settings.youtubeCookies
    }
    if (settings.groqKey) opts.groq_key = settings.groqKey
    if (settings.geminiKey) opts.gemini_key = settings.geminiKey
    if (settings.whisperModel) opts.whisper_model = settings.whisperModel
    if (settings.geminiModel) opts.gemini_model = settings.geminiModel
    // Clip generation params come from the Clip Generator form (payload),
    // falling back to saved settings if the form didn't send them.
    if (payload.clipCount) opts.clip_count = payload.clipCount
    if (payload.minClip) opts.min_clip = payload.minClip
    if (payload.maxClip) opts.max_clip = payload.maxClip
    if (payload.contentType) opts.content_type = payload.contentType

    const file = payload.file || null
    const body = file ? opts : { ...opts, source: payload.source }
    try {
      const res = await submitJob(body, file, onProgress)
      if (onUploadEnd) onUploadEnd()
      setJob({ job_id: res.job_id, status: res.status, logs: [], result: null, error: null })
      startPolling(res.job_id)
    } catch (e) {
      if (onUploadEnd) onUploadEnd()
      setBusy(false)
      setError(e.message)
    }
  }

  const clips = (job?.result?.clips) || []
  const failed = job?.status === 'failed'

  function applyEditedClip(index, newFile) {
    setJob((j) => {
      if (!j?.result?.clips) return j
      return {
        ...j,
        result: {
          ...j.result,
          clips: j.result.clips.map((c) =>
            c.index === index ? { ...c, file: newFile, subtitled_file: newFile } : c
          ),
        },
      }
    })
  }

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar */}
      <aside className="w-20 lg:w-64 bg-surface border-r border-white/5 flex flex-col h-full shrink-0 transition-all duration-300">
        <div className="p-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-primary/20 rounded-lg flex items-center justify-center shrink-0">
            <Scissors size={18} className="text-primary" />
          </div>
          <span className="font-bold text-lg text-white hidden lg:block tracking-tight">
            AutoClipper
          </span>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-2">
          <SidebarButton
            active={tab === 'generator'}
            onClick={() => setTab('generator')}
            icon={LayoutDashboard}
          >
            Clip Generator
          </SidebarButton>
          <SidebarButton
            active={tab === 'library'}
            onClick={() => setTab('library')}
            icon={FolderOpen}
          >
            Saved Library
          </SidebarButton>
          <SidebarButton
            active={tab === 'trending'}
            onClick={() => setTab('trending')}
            icon={Flame}
          >
            Trending Ideas
          </SidebarButton>
        </nav>

        <div className="px-4 pb-4">
          <SidebarButton
            active={tab === 'settings'}
            onClick={() => setTab('settings')}
            icon={SettingsIcon}
          >
            Settings
          </SidebarButton>
        </div>

        <div className="p-4 border-t border-white/5">
          <p className="text-[10px] text-zinc-500 hidden lg:block leading-relaxed">
            Groq Whisper + Gemini powered vertical shorts.
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-4 py-8">
          {tab === 'generator' ? (
            <>
              <section className="bg-surface border border-border rounded-xl p-5 mb-6">
                <SubmitForm onSubmit={handleSubmit} busy={busy} settings={settings} />
              </section>

              {error && (
                <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 px-4 py-3 text-sm">
                  {error}
                </div>
              )}

              {job && (
                <section className="mb-6">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-sm text-zinc-400">Job</span>
                    <code className="text-xs text-zinc-300">{job.job_id}</code>
                    <StatusBadge status={job.status} />
                  </div>
                  {failed && job.error && (
                    <div className="mb-3 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 px-4 py-3 text-sm whitespace-pre-wrap">
                      {job.error}
                    </div>
                  )}
                  <LogConsole logs={job.logs || []} />
                </section>
              )}

              {clips.length > 0 && (
                <ClipGrid jobId={job.job_id} clips={clips} onApply={applyEditedClip} />
              )}
            </>
           ) : tab === 'library' ? (
            <Library />
          ) : tab === 'trending' ? (
            <TrendingPage settings={settings} />
          ) : (
            <SettingsPage settings={settings} setSettings={setSettings} />
          )}
        </div>
      </main>
    </div>
  )
}

function SidebarButton({ active, onClick, icon: Icon, children }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl transition-colors ${
        active
          ? 'bg-primary/10 text-primary'
          : 'text-zinc-400 hover:text-white hover:bg-white/5'
      }`}
    >
      <Icon size={20} />
      <span className="font-medium hidden lg:block">{children}</span>
    </button>
  )
}

function StatusBadge({ status }) {
  const styles = {
    queued: 'bg-zinc-500/20 text-zinc-300',
    processing: 'bg-primary/20 text-primary',
    completed: 'bg-green-500/20 text-green-300',
    failed: 'bg-red-500/20 text-red-300',
  }
  return (
    <span className={`text-xs px-2 py-1 rounded-full font-medium ${styles[status] || styles.queued}`}>
      {status}
    </span>
  )
}
