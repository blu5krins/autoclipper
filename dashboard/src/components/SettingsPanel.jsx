import { useState } from 'react'

const WHISPER_MODELS = [
  { value: 'whisper-large-v3-turbo', label: 'whisper-large-v3-turbo (recommended)' },
  { value: 'whisper-large-v3', label: 'whisper-large-v3' },
  { value: 'distil-whisper-large-v3-en', label: 'distil-whisper-large-v3-en (English)' },
]

const GEMINI_MODELS = [
  { value: 'gemini-3.5-flash', label: 'gemini-3.5-flash (recommended)' },
  { value: 'gemini-3-flash', label: 'gemini-3-flash' },
  { value: 'gemini-2.5-flash', label: 'gemini-2.5-flash' },
  { value: 'gemini-2.5-pro', label: 'gemini-2.5-pro' },
  { value: 'gemini-2.0-flash', label: 'gemini-2.0-flash' },
]

export default function SettingsPanel({ settings, setSettings, alwaysOpen = false }) {
  const [open, setOpen] = useState(alwaysOpen)

  function update(key, value) {
    setSettings((s) => ({ ...s, [key]: value }))
  }

  return (
    <div className={alwaysOpen ? '' : 'mt-4'}>
      {!alwaysOpen && (
        <button
          onClick={() => setOpen((o) => !o)}
          className="text-xs text-zinc-400 hover:text-zinc-200"
        >
          {open ? '▾ Hide options' : '▸ API keys & options'}
        </button>
      )}

      {(open || alwaysOpen) && (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field
            label="Groq API Key"
            value={settings.groqKey}
            onChange={(v) => update('groqKey', v)}
            placeholder="gsk_…"
            secret
          />
          <Field
            label="Gemini API Key"
            value={settings.geminiKey}
            onChange={(v) => update('geminiKey', v)}
            placeholder="AIza…"
            secret
          />
          <Field
            label="YouTube Data API Key"
            value={settings.youtubeApiKey}
            onChange={(v) => update('youtubeApiKey', v)}
            placeholder="AIza… (for Trending videos)"
            secret
          />
          <SelectField
            label="Whisper Model"
            value={settings.whisperModel || WHISPER_MODELS[0].value}
            options={WHISPER_MODELS}
            onChange={(v) => update('whisperModel', v)}
          />
          <SelectField
            label="Gemini Model"
            value={settings.geminiModel || GEMINI_MODELS[0].value}
            options={GEMINI_MODELS}
            onChange={(v) => update('geminiModel', v)}
          />
        </div>
      )}
    </div>
  )
}

function Field({ label, value, onChange, placeholder, secret }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-zinc-400">
      {label}
      <input
        type={secret ? 'password' : 'text'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="bg-background border border-border rounded-lg px-3 py-2 text-sm text-zinc-100
                   placeholder-zinc-600 focus:outline-none focus:border-primary"
      />
    </label>
  )
}

function SelectField({ label, value, options, onChange }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-zinc-400">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-background border border-border rounded-lg px-3 py-2 text-sm text-zinc-100
                   focus:outline-none focus:border-primary"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}
