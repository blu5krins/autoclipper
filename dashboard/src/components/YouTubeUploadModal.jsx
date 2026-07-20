import { useState } from 'react'
import { Youtube, Calendar, Send } from 'lucide-react'
import { youtubeUpload, youtubeStatus } from '../api.js'

export default function YouTubeUploadModal({ source, onClose, onDone }) {
  // source: { jobId?, name?, filename, title, description }
  const [title, setTitle] = useState(source.title || '')
  const [description, setDescription] = useState(source.description || '')
  const [schedule, setSchedule] = useState(false)
  const [publishAt, setPublishAt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  async function submit() {
    setBusy(true)
    setError('')
    try {
      const auth = await youtubeStatus()
      if (!auth.authenticated) {
        setError('YouTube not connected. Connect it in Settings first.')
        setBusy(false)
        return
      }
      const payload = {
        job_id: source.jobId || null,
        name: source.name || null,
        filename: source.filename,
        title,
        description,
        publish_at: schedule && publishAt ? new Date(publishAt).toISOString() : null,
      }
      const res = await youtubeUpload(payload)
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
          <Youtube size={18} className="text-red-500" /> Upload to YouTube Shorts
        </h3>

        {result ? (
          <div className="text-center py-4">
            <p className="text-green-300 text-sm mb-2">
              {result.scheduled ? 'Scheduled!' : 'Uploaded!'}
            </p>
            {result.url && (
              <a href={result.url} target="_blank" rel="noreferrer" className="text-primary text-sm underline">
                {result.url}
              </a>
            )}
            {result.scheduled && result.publish_at && (
              <p className="text-xs text-zinc-400 mt-2">Goes public at {result.publish_at}</p>
            )}
          </div>
        ) : (
          <>
            <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1 block">Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-red-400/50 mb-3"
            />

            <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1 block">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-red-400/50 resize-none mb-3"
            />

            <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer mb-2">
              <input
                type="checkbox"
                checked={schedule}
                onChange={(e) => setSchedule(e.target.checked)}
                className="accent-red-500 w-4 h-4"
              />
              <Calendar size={14} /> Schedule for later
            </label>

            {schedule && (
              <input
                type="datetime-local"
                value={publishAt}
                onChange={(e) => setPublishAt(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-red-400/50 mb-3"
              />
            )}

            {error && <p className="text-sm text-red-300 mb-2">{error}</p>}

            <button
              onClick={submit}
              disabled={busy}
              className="w-full py-2.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {busy ? 'Uploading…' : <><Send size={15} /> Upload</>}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
