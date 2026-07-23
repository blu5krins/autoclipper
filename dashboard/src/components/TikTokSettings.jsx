import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, AlertCircle, Link2, LogOut, Upload } from 'lucide-react'
import { tiktokStatus, tiktokConnect, tiktokLogout } from '../api.js'

export default function TikTokSettings() {
  const [status, setStatus] = useState({ authenticated: false })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [cookieText, setCookieText] = useState('')
  const [showImport, setShowImport] = useState(false)
  const fileRef = useRef(null)

  async function load() {
    try {
      const s = await tiktokStatus()
      setStatus(s)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function connect() {
    const text = cookieText.trim()
    if (!text) {
      setError('Please paste your TikTok cookies or import a cookies file.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await tiktokConnect(text)
      setCookieText('')
      setShowImport(false)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function disconnect() {
    if (!confirm('Disconnect TikTok account?')) return
    setBusy(true)
    setError('')
    try {
      await tiktokLogout()
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function handleFileImport(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      setCookieText(ev.target.result || '')
      setShowImport(true)
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  return (
    <section className="border-t border-border pt-5">
      <div className="flex items-center gap-2 mb-3">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="text-zinc-400">
          <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1v-3.51a6.37 6.37 0 0 0-.79-.05A6.34 6.34 0 0 0 3.16 15.2a6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V8.73a8.19 8.19 0 0 0 4.78 1.53V6.81a4.84 4.84 0 0 1-1.03-.12z" fill="currentColor"/>
        </svg>
        <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">TikTok</h2>
      </div>

      {loading ? (
        <p className="text-xs text-zinc-500">Checking connection…</p>
      ) : (
        <div className="bg-background border border-border rounded-lg p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {status.authenticated ? (
                <CheckCircle2 size={18} className="text-green-400" />
              ) : (
                <AlertCircle size={18} className="text-zinc-500" />
              )}
              <span className="text-sm text-zinc-200">
                {status.authenticated
                  ? 'Connected to TikTok'
                  : 'Not connected — import cookies to enable posting'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {!status.authenticated && (
                <button
                  onClick={() => setShowImport(!showImport)}
                  disabled={busy}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-[#fe2c55] hover:bg-[#e02548] text-white transition-colors disabled:opacity-50"
                >
                  <Link2 size={13} /> Connect
                </button>
              )}
              {status.authenticated && (
                <button
                  onClick={disconnect}
                  disabled={busy}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-zinc-300 transition-colors disabled:opacity-50"
                >
                  <LogOut size={13} /> Disconnect
                </button>
              )}
            </div>
          </div>

          {showImport && !status.authenticated && (
            <div className="mt-3 space-y-2">
              <div className="flex gap-2">
                <textarea
                  value={cookieText}
                  onChange={(e) => setCookieText(e.target.value)}
                  placeholder={'Paste cookies here (JSON or Netscape format)\n\nHow to get cookies:\n1. Install "Cookie-Editor" extension\n2. Log into tiktok.com\n3. Click extension → Export (JSON or Netscape)\n4. Paste here or import file below'}
                  rows={6}
                  className="flex-1 rounded-lg bg-background border border-border px-3 py-2 text-xs text-zinc-200
                             font-mono focus:outline-none focus:border-primary resize-y"
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={connect}
                  disabled={busy || !cookieText.trim()}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-[#fe2c55] hover:bg-[#e02455] text-white transition-colors disabled:opacity-50"
                >
                  {busy ? 'Connecting…' : 'Save Cookies'}
                </button>
                <label className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-zinc-300 cursor-pointer transition-colors">
                  <Upload size={13} /> Import File
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".txt,.json"
                    onChange={handleFileImport}
                    className="hidden"
                  />
                </label>
              </div>
              <p className="text-[10px] text-zinc-500">
                Supported: Cookie-Editor JSON export or Netscape cookies.txt format.
                Cookies expire after ~30 days — re-import when needed.
              </p>
            </div>
          )}

          {error && <p className="text-xs text-red-300 mt-2">{error}</p>}
        </div>
      )}
    </section>
  )
}
