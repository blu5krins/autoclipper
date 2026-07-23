import { useState, useEffect } from 'react'
import { Facebook, Send } from 'lucide-react'
import { facebookUpload, facebookStatus, facebookPages } from '../api.js'
import UploadTimeSuggestion from './UploadTimeSuggestion.jsx'

export default function FacebookUploadModal({ source, onClose, onDone }) {
  // source: { jobId?, name?, filename, title, description }
  const [title, setTitle] = useState(source.title || '')
  const [description, setDescription] = useState(source.description || '')
  const [selectedPage, setSelectedPage] = useState('')
  const [asReel, setAsReel] = useState(true)
  const [pages, setPages] = useState([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    async function loadPages() {
      try {
        const auth = await facebookStatus()
        if (!auth.authenticated) {
          setError('Facebook not connected. Connect it in Settings first.')
          setLoading(false)
          return
        }
        const { pages: p } = await facebookPages()
        setPages(p)
        if (p.length === 1) {
          setSelectedPage(p[0].id)
        }
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    loadPages()
  }, [])

  async function submit() {
    if (!selectedPage) {
      setError('Please select a Page to upload to')
      return
    }
    setBusy(true)
    setError('')
    try {
      const payload = {
        job_id: source.jobId || null,
        name: source.name || null,
        filename: source.filename,
        page_id: selectedPage,
        title,
        description,
        as_reel: asReel,
      }
      const res = await facebookUpload(payload)
      setResult(res)
      if (onDone) setTimeout(onDone, 1500)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#121214] border border-white/10 rounded-2xl w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-zinc-500 hover:text-white">
          ✕
        </button>
        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <Facebook size={18} className="text-[#1877f2]" />
          Upload to Facebook
        </h3>

        {result ? (
          <div className="text-center py-4">
            <p className="text-green-300 text-sm mb-2">
              {result.ok ? 'Published successfully!' : 'Upload failed'}
            </p>
            {result.url && (
              <a href={result.url} target="_blank" rel="noreferrer" className="text-[#1877f2] text-sm underline">
                View on Facebook
              </a>
            )}
          </div>
        ) : loading ? (
          <p className="text-xs text-zinc-500 text-center py-4">Loading pages…</p>
        ) : (
          <>
            {pages.length === 0 && !error ? (
              <p className="text-xs text-zinc-400 text-center py-4">
                No Pages found. Make sure you're an admin of at least one Facebook Page.
              </p>
            ) : (
              <>
                <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1 block">Page</label>
                <select
                  value={selectedPage}
                  onChange={(e) => setSelectedPage(e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-[#1877f2]/50 mb-3"
                >
                  <option value="">Select a Page…</option>
                  {pages.map((page) => (
                    <option key={page.id} value={page.id}>
                      {page.name}
                    </option>
                  ))}
                </select>

                <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1 block">Title</label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Video title"
                  className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-[#1877f2]/50 mb-3"
                />

                <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1 block">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  placeholder="Add a description with hashtags…"
                  className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-[#1877f2]/50 resize-none mb-3"
                />

                <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer mb-4">
                  <input
                    type="checkbox"
                    checked={asReel}
                    onChange={(e) => setAsReel(e.target.checked)}
                    className="accent-[#1877f2] w-4 h-4"
                  />
                  Publish as Reel (vertical short video)
                </label>

                {error && <p className="text-sm text-red-300 mb-2">{error}</p>}

                <UploadTimeSuggestion platform="youtube" />

                <button
                  onClick={submit}
                  disabled={busy || !selectedPage}
                  className="w-full py-2.5 rounded-lg bg-[#1877f2] hover:bg-[#166fe5] text-white font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {busy ? 'Publishing…' : <><Send size={15} /> Publish to Facebook</>}
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
