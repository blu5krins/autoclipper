import { useEffect, useState } from 'react'
import { FolderOpen, Play, Download, Trash2, Youtube, Wand2, Users, Type, Facebook } from 'lucide-react'
import { listLibrary, libraryFileUrl, librarySrtUrl, deleteLibraryClip, deleteLibraryFolder } from '../api.js'
import YouTubeUploadModal from './YouTubeUploadModal.jsx'
import FacebookUploadModal from './FacebookUploadModal.jsx'
import EnhanceModal from './EnhanceModal.jsx'
import ChatSplitModal from './ChatSplitModal.jsx'
import SubtitleEditor from './SubtitleEditor.jsx'

export default function Library({ onVoiceOver }) {
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [uploading, setUploading] = useState(null) // { name, clip }
  const [facebookUploading, setFacebookUploading] = useState(null) // { name, clip }
  const [enhancing, setEnhancing] = useState(null) // { name, clip, hook }
  const [chatSplitting, setChatSplitting] = useState(null) // { name, clip }
  const [subtitling, setSubtitling] = useState(null) // { name, clip }

  function refresh() {
    listLibrary()
      .then(setItems)
      .catch((e) => setError(e.message))
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleDeleteClip(name, file) {
    if (!confirm('Delete this clip? This cannot be undone.')) return
    setDeleting(true)
    try {
      await deleteLibraryClip(name, file)
      refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setDeleting(false)
    }
  }

  async function handleDeleteFolder(name) {
    if (!confirm('Delete this entire video and all its clips? This cannot be undone.')) return
    setDeleting(true)
    try {
      await deleteLibraryFolder(name)
      refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <section>
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <FolderOpen size={18} /> Saved Library
      </h2>

      {error && <div className="mb-3 text-sm text-red-300">{error}</div>}

      {items.length === 0 ? (
        <div className="text-sm text-zinc-500">
          No saved clips yet. Generate clips from a video and they'll appear here,
          organized into a folder per source video.
        </div>
      ) : (
        <div className="space-y-6">
          {items.map((vid) => (
            <div key={vid.name} className="bg-surface border border-border rounded-xl p-4">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 font-medium text-zinc-100">
                  {vid.title}
                </span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-zinc-500">{vid.clips.length} clips</span>
                  <button
                    onClick={() => handleDeleteFolder(vid.name)}
                    disabled={deleting}
                    title="Delete this video and all its clips"
                    className="text-xs px-2 py-1 rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors flex items-center gap-1 disabled:opacity-50"
                  >
                    <Trash2 size={13} /> Delete
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 mt-4">
                {vid.clips.map((c) => {
                  const url = libraryFileUrl(vid.name, c.file)
                  return (
                    <div key={c.file} className="bg-background border border-border rounded-lg overflow-hidden flex flex-col sm:flex-row">
                      <video
                        src={url}
                        controls
                        preload="metadata"
                        className="w-full sm:w-44 sm:h-72 aspect-[9/16] sm:aspect-auto object-contain bg-black shrink-0"
                      />
                      <div className="p-3 flex-1 flex flex-col min-w-0">
                        <div className="text-sm font-semibold text-zinc-100 line-clamp-2">
                          {c.title || c.file}
                        </div>

                        {c.hook && (
                          <div className="mt-2 bg-black/20 rounded-lg p-2 border border-white/5">
                            <div className="text-[10px] font-bold text-amber-400 mb-1 uppercase tracking-wider">Hook</div>
                            <p className="text-xs text-zinc-300 break-words line-clamp-3">{c.hook}</p>
                          </div>
                        )}
                        {c.description && (
                          <div className="mt-2 bg-black/20 rounded-lg p-2 border border-white/5">
                            <div className="text-[10px] font-bold text-cyan-400 mb-1 uppercase tracking-wider">Caption</div>
                            <p className="text-xs text-zinc-300 break-words whitespace-pre-wrap line-clamp-3">{c.description}</p>
                          </div>
                        )}

                        <div className="flex flex-wrap gap-2 mt-3">
                          <a
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                            className="flex-1 text-center text-xs px-3 py-1.5 rounded-lg bg-primary/20 text-primary
                                       hover:bg-primary/30 transition-colors flex items-center justify-center gap-1"
                          >
                            <Play size={13} /> Open
                          </a>
                          <a
                            href={url}
                            download={c.file}
                            className="flex-1 text-center text-xs px-3 py-1.5 rounded-lg bg-white/5 text-zinc-300
                                       hover:bg-white/10 transition-colors flex items-center justify-center gap-1"
                          >
                            <Download size={13} /> Save
                          </a>
                          <button
                            onClick={() => handleDeleteClip(vid.name, c.file)}
                            disabled={deleting}
                            title="Delete this clip"
                            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-red-500/15 text-red-400
                                       hover:bg-red-500/25 transition-colors flex items-center justify-center gap-1 disabled:opacity-50"
                          >
                            <Trash2 size={13} /> Delete
                          </button>
                          <button
                            onClick={() => setSubtitling({ name: vid.name, clip: c })}
                            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-yellow-500/15 text-yellow-400
                                       hover:bg-yellow-500/25 transition-colors flex items-center justify-center gap-1"
                          >
                            <Type size={13} /> Subtitle
                          </button>
                          <button
                            onClick={() => setEnhancing({ name: vid.name, clip: c, hook: c.hook })}
                            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-purple-500/15 text-purple-300
                                       hover:bg-purple-500/25 transition-colors flex items-center justify-center gap-1"
                          >
                            <Wand2 size={13} /> Enhance
                          </button>
                          <button
                            onClick={() => setChatSplitting({ name: vid.name, clip: c })}
                            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-cyan-500/15 text-cyan-300
                                       hover:bg-cyan-500/25 transition-colors flex items-center justify-center gap-1"
                          >
                            <Users size={13} /> Split
                          </button>
                          <button
                            onClick={() => setUploading({ name: vid.name, clip: c })}
                            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-red-600/15 text-red-400
                                       hover:bg-red-600/25 transition-colors flex items-center justify-center gap-1"
                          >
                            <Youtube size={13} /> YouTube
                          </button>
                          <button
                            onClick={() => setFacebookUploading({ name: vid.name, clip: c })}
                            className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-[#1877f2]/15 text-[#1877f2]
                                       hover:bg-[#1877f2]/25 transition-colors flex items-center justify-center gap-1"
                          >
                            <Facebook size={13} /> FB
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {uploading && (
        <YouTubeUploadModal
          source={{
            name: uploading.name,
            filename: uploading.clip.file,
            title: uploading.clip.title,
            description: uploading.clip.description,
          }}
          onClose={() => setUploading(null)}
          onDone={() => setUploading(null)}
        />
      )}

      {facebookUploading && (
        <FacebookUploadModal
          source={{
            name: facebookUploading.name,
            filename: facebookUploading.clip.file,
            title: facebookUploading.clip.title,
            description: facebookUploading.clip.description,
          }}
          onClose={() => setFacebookUploading(null)}
          onDone={() => setFacebookUploading(null)}
        />
      )}

      {enhancing && (
        <EnhanceModal
          name={enhancing.name}
          clip={enhancing.clip}
          hook={enhancing.hook}
          onClose={() => { setEnhancing(null); refresh() }}
          onDone={() => { setEnhancing(null); refresh() }}
        />
      )}

      {chatSplitting && (
        <ChatSplitModal
          name={chatSplitting.name}
          clip={chatSplitting.clip}
          onClose={() => { setChatSplitting(null); refresh() }}
          onDone={() => { setChatSplitting(null); refresh() }}
        />
      )}

      {subtitling && (
        <SubtitleEditor
          name={subtitling.name}
          clip={subtitling.clip}
          srtUrl={librarySrtUrl(subtitling.name, subtitling.clip.file)}
          onApply={() => {}}
          onClose={() => { setSubtitling(null); refresh() }}
        />
      )}
    </section>
  )
}
