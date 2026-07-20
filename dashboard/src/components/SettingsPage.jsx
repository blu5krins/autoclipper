import { useState } from 'react'
import { KeyRound, Cpu, ToggleLeft, Save, Check, Trash2 } from 'lucide-react'
import SettingsPanel from './SettingsPanel.jsx'
import YouTubeSettings from './YouTubeSettings.jsx'
import { runCleanup, saveSettings } from '../api.js'

export default function SettingsPage({ settings, setSettings }) {
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveErr, setSaveErr] = useState('')
  const [cleaning, setCleaning] = useState(false)
  const [cleanMsg, setCleanMsg] = useState('')

  async function handleSave() {
    setSaving(true)
    setSaveErr('')
    try {
      const updated = await saveSettings({
        groqKey: settings.groqKey || '',
        geminiKey: settings.geminiKey || '',
        youtubeApiKey: settings.youtubeApiKey || '',
        geminiModel: settings.geminiModel || '',
        whisperModel: settings.whisperModel || '',
        youtubeCookies: settings.youtubeCookies || '',
      })
      setSettings((prev) => ({
        ...prev,
        groqKey: updated.groqKey || '',
        geminiKey: updated.geminiKey || '',
        youtubeApiKey: updated.youtubeApiKey || '',
        geminiModel: updated.geminiModel || '',
        whisperModel: updated.whisperModel || '',
        youtubeCookies: updated.youtubeCookies || '',
      }))
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setSaveErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-9 h-9 bg-primary/20 rounded-lg flex items-center justify-center">
          <KeyRound size={18} className="text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-zinc-400 text-sm">Configure API keys and processing options.</p>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-xl p-5 space-y-6">
        <section>
          <div className="flex items-center gap-2 mb-3">
            <KeyRound size={16} className="text-zinc-400" />
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">API Keys</h2>
          </div>
          <SettingsPanel settings={settings} setSettings={setSettings} alwaysOpen />
        </section>

        <section className="border-t border-border pt-5">
          <div className="flex items-center gap-2 mb-3">
            <Cpu size={16} className="text-zinc-400" />
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">Models</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <InfoRow label="Whisper Model" value={settings.whisperModel || 'whisper-large-v3-turbo (default)'} />
            <InfoRow label="Gemini Model" value={settings.geminiModel || 'gemini-3.5-flash (default)'} />
          </div>
        </section>

        <section className="border-t border-border pt-5">
          <div className="flex items-center gap-2 mb-3">
            <KeyRound size={16} className="text-zinc-400" />
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">YouTube</h2>
          </div>
          <label className="block text-sm text-zinc-300 mb-1">
            Cookies (Netscape format)
          </label>
          <textarea
            value={settings.youtubeCookies || ''}
            onChange={(e) => setSettings((s) => ({ ...s, youtubeCookies: e.target.value }))}
            placeholder={"Paste cookies.txt content (Netscape format) to enable HD downloads (≥720p).\nRequired because YouTube limits anonymous downloads to 360p."}
            rows={5}
            className="w-full rounded-lg bg-background border border-border px-3 py-2 text-xs text-zinc-200
                       font-mono focus:outline-none focus:border-primary resize-y"
          />
          <p className="text-xs text-zinc-500 mt-2">
            Stored encrypted on the server, tied to your account. Sent to the AI providers only when you run a job.
          </p>
        </section>

        <YouTubeSettings />

        <section className="border-t border-border pt-5">
          <div className="flex items-center gap-2 mb-3">
            <Trash2 size={16} className="text-zinc-400" />
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">Storage</h2>
          </div>
          <p className="text-xs text-zinc-500 mb-3">
            Finished job folders are auto-deleted after 24h (Saved Library is kept forever).
            Run a manual cleanup now to free disk space immediately.
          </p>
          <button
            onClick={async () => {
              if (cleaning) return
              setCleaning(true)
              setCleanMsg('')
              try {
                const r = await runCleanup(null)
                setCleanMsg(`Removed ${r.removed} old job folder(s).`)
              } catch (e) {
                setCleanMsg(e.message)
              } finally {
                setCleaning(false)
                setTimeout(() => setCleanMsg(''), 4000)
              }
            }}
            disabled={cleaning}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-red-500/80 hover:bg-red-500
                       disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            <Trash2 size={15} />
            {cleaning ? 'Cleaning…' : 'Clean Up Now'}
          </button>
          {cleanMsg && <p className="text-xs text-zinc-400 mt-2">{cleanMsg}</p>}
        </section>

        <section className="border-t border-border pt-5">
          <div className="flex items-center gap-2 mb-3">
            <ToggleLeft size={16} className="text-zinc-400" />
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">Processing Options</h2>
          </div>
          <div className="space-y-3">
            <ToggleRow
              label="Vertical 9:16 reframe"
              checked={settings.vertical}
              onChange={(v) => setSettings((s) => ({ ...s, vertical: v }))}
            />
            <ToggleRow
              label="YOLO person fallback"
              checked={settings.useYolo}
              onChange={(v) => setSettings((s) => ({ ...s, useYolo: v }))}
            />
            <ToggleRow
              label="Burn subtitle tracks"
              checked={settings.subtitles}
              onChange={(v) => setSettings((s) => ({ ...s, subtitles: v }))}
            />
            <ToggleRow
              label="Force HD download (≥720p)"
              checked={settings.forceHd}
              onChange={(v) => setSettings((s) => ({ ...s, forceHd: v }))}
            />
          </div>
          <p className="text-xs text-zinc-500 mt-3">
            Your API keys are saved to your account on the server (encrypted at rest) and
            used automatically for every job — no need to re-enter them.
          </p>
        </section>

        <div className="flex justify-end pt-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary hover:bg-blue-600 text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {saved ? <Check size={16} /> : <Save size={16} />}
            {saving ? 'Saving…' : saved ? 'Saved' : 'Save'}
          </button>
          {saveErr && <p className="text-xs text-red-400 mt-2">{saveErr}</p>}
        </div>
      </div>
    </div>
  )
}

function ToggleRow({ label, checked, onChange }) {
  return (
    <label className="flex items-center justify-between bg-background border border-border rounded-lg px-3 py-2.5 cursor-pointer">
      <span className="text-sm text-zinc-200">{label}</span>
      <span className="relative inline-flex items-center cursor-pointer">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="sr-only peer" />
        <div className="w-9 h-5 bg-zinc-700 rounded-full peer-checked:bg-primary after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4"></div>
      </span>
    </label>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="bg-background border border-border rounded-lg px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="text-sm text-zinc-200 truncate">{value}</div>
    </div>
  )
}
