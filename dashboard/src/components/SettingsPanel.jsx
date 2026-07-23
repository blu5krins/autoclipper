import { useState } from 'react'
import { AlertTriangle, CheckCircle2, Eye, EyeOff } from 'lucide-react'

const WHISPER_MODELS = [
  { value: 'whisper-large-v3-turbo', label: 'whisper-large-v3-turbo (recommended)' },
  { value: 'whisper-large-v3', label: 'whisper-large-v3' },
  { value: 'distil-whisper-large-v3-en', label: 'distil-whisper-large-v3-en (English)' },
]

const GEMINI_MODELS = [
  { value: 'gemini-3.5-flash', label: 'gemini-3.5-flash (recommended)' },
  { value: 'gemini-3-flash', label: 'gemini-3-flash' },
  { value: 'gemini-2.5-pro', label: 'gemini-2.5-pro' },
]

function maskKey(key) {
  if (!key) return ''
  if (key.length <= 8) return '••••••••'
  return key.slice(0, 4) + '••••' + key.slice(-4)
}

export default function SettingsPanel({ settings, setSettings, alwaysOpen = false }) {
  const [open, setOpen] = useState(alwaysOpen)
  const [showKeys, setShowKeys] = useState({})

  function update(key, value) {
    setSettings((s) => ({ ...s, [key]: value }))
  }

  function toggleShow(key) {
    setShowKeys((s) => ({ ...s, [key]: !s[key] }))
  }

  const apiKeys = [
    { key: 'groqKey', label: 'Groq API Key', placeholder: 'gsk_…', required: true, docs: 'https://console.groq.com/keys' },
    { key: 'geminiKey', label: 'Gemini API Key', placeholder: 'AIza…', required: true, docs: 'https://aistudio.google.com/apikey' },
    { key: 'youtubeApiKey', label: 'YouTube Data API Key', placeholder: 'AIza… (for Trending)', required: false, docs: 'https://console.cloud.google.com' },
  ]

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
        <div className="mt-3 space-y-3">
          {apiKeys.map(({ key, label, placeholder, required, docs }) => {
            const value = settings[key] || ''
            const isSet = value.length > 0
            const isRevealed = showKeys[key]

            return (
              <div key={key} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-zinc-400 flex items-center gap-1.5">
                    {label}
                    {required && <span className="text-red-400">*</span>}
                  </label>
                  {isSet ? (
                    <span className="flex items-center gap-1 text-[10px] text-green-400">
                      <CheckCircle2 size={10} />
                      Configured
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[10px] text-amber-400">
                      <AlertTriangle size={10} />
                      {required ? 'Required' : 'Optional'}
                    </span>
                  )}
                </div>

                <div className="relative">
                  <input
                    type={isRevealed ? 'text' : 'password'}
                    value={value}
                    onChange={(e) => update(key, e.target.value)}
                    placeholder={placeholder}
                    className="w-full bg-background border border-border rounded-lg px-3 py-2 pr-16 text-sm text-zinc-100
                               placeholder-zinc-600 focus:outline-none focus:border-primary"
                  />
                  {isSet && (
                    <button
                      type="button"
                      onClick={() => toggleShow(key)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-white/10 rounded text-zinc-500 hover:text-zinc-300"
                    >
                      {isRevealed ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  )}
                </div>

                {isSet ? (
                  <p className="text-[10px] text-zinc-600 font-mono">
                    {isRevealed ? value : maskKey(value)}
                  </p>
                ) : (
                  <a href={docs} target="_blank" rel="noreferrer" className="text-[10px] text-primary/70 hover:text-primary underline">
                    Get API key →
                  </a>
                )}
              </div>
            )
          })}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
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
        </div>
      )}
    </div>
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
