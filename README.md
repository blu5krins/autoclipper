# AutoClipper

Turn long videos (YouTube URL or local upload) into viral-ready **9:16 short clips** for TikTok, Instagram Reels, and YouTube Shorts.

**Pipeline:** ingest → transcribe (**Groq Whisper**) → detect viral moments (**Gemini**) → cut clips (**FFmpeg**) → reframe to **vertical 9:16** with face/subject tracking → **burn in subtitles** from word timestamps → optional **hook overlay** and **direct upload** to YouTube.

Ships as a **FastAPI backend** with an async job queue and a **React dashboard** (Vite + Tailwind).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Deploy-Docker-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)

## Table of Contents

- [Requirements](#requirements)
- [Setup (Docker)](#setup-docker--recommended)
- [Local Development](#local-development-without-docker)
- [Backend API](#backend-api)
- [Dashboard Features](#dashboard-features)
- [Configuration](#configuration-env)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

## Requirements

- Docker + Docker Compose (recommended), or Python 3.11 + Node 18 for local dev
- [FFmpeg](https://ffmpeg.org/download.html) on `PATH` (`ffmpeg` + `ffprobe`)
- API keys (stored in `.env` server-side **and/or** entered in the dashboard Settings):
  - `GROQ_API_KEY` — https://console.groq.com/keys (**required** — Whisper transcription)
  - `GEMINI_API_KEY` — https://aistudio.google.com/apikey (required — viral moment detection + trending ideas)
  - `YOUTUBE_API_KEY` — https://console.cloud.google.com (real trending data + upload view counts)

## Setup (Docker — recommended)

### Prerequisites
- [Docker](https://www.docker.com/products/docker-desktop) + Docker Compose v2 (`docker compose` CLI).
- FFmpeg is bundled inside the backend image, so no host install needed.
- API keys (see [Requirements](#requirements)). At minimum `GROQ_API_KEY` and `GEMINI_API_KEY`.

### 1. Clone & configure

```bash
git clone https://github.com/your-username/autoclipper.git
cd autoclipper
cp .env.example .env
```

Edit `.env` and fill in at least:

```dotenv
GROQ_API_KEY=gsk_xxx        # required — Whisper transcription
GEMINI_API_KEY=xxx          # required — viral moment detection
# YOUTUBE_API_KEY=xxx       # optional — real YouTube trending
COMPOSE_PROJECT_NAME=autoclipper   # keeps container names stable
```

> The `COMPOSE_PROJECT_NAME=autoclipper` line keeps the container names
> (`autoclipper-backend`, `autoclipper-frontend`) stable across runs. Either keep
> it in `.env` or always pass `-p autoclipper` on the command line.

### 2. Build & start

```bash
docker compose -p autoclipper up --build
```

Or detached (recommended for long sessions):

```bash
docker compose -p autoclipper up -d --build
```

- `backend` — FastAPI + FFmpeg + MediaPipe (Python 3.11-slim). Transcription runs on Groq's cloud Whisper endpoint. Container `autoclipper-backend`, port **8000**. API docs at http://localhost:8000/docs.
- `frontend` — React production build served by nginx, proxying `/api` to the backend. Container `autoclipper-frontend`, port **5173** (container 80 → host 5173).

Generated clips live in `./output` (mounted into the backend container at `/app/output`). Open the dashboard at **http://localhost:5173**.

### 3. Useful commands

```bash
docker compose -p autoclipper ps                 # show container status
docker compose -p autoclipper logs -f backend    # follow backend logs
docker compose -p autoclipper down               # stop & remove containers
docker compose -p autoclipper up -d --build backend   # rebuild backend only after code changes
docker compose -p autoclipper restart frontend   # restart the dashboard
```

### Volumes & mounted files
- `./output` ↔ `/app/output` — all generated clips, logs, and the Saved Library.
- `./client_secret.json` ↔ `/app/client_secret.json` (read-only) — only needed for YouTube OAuth upload.
- `yt_config` (named volume) — stores the YouTube OAuth token.

### YouTube upload (optional)
To enable uploading clips to YouTube, place your OAuth client secret at
`./client_secret.json` (downloaded from Google Cloud Console, "Desktop" app type).
The dashboard's Settings page will then show a "Connect YouTube" button.

## Local Development (without Docker)

### Backend
```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000   # docs at http://localhost:8000/docs
```

### Frontend (dashboard)
```bash
cd dashboard
npm install
npm run dev          # dev server (HMR) on http://localhost:5173
npm run build        # production build (served by nginx in Docker)
npm run lint         # ESLint, --max-warnings 0
```

The frontend proxies `/api` calls to the backend at `http://localhost:8000` (override with `VITE_API_URL`).

## Accounts & Per-User API Keys

AutoClipper has optional user accounts. Each user registers with a username/password
and stores their own API keys (Groq, Gemini, YouTube) on the server — encrypted at rest
with Fernet. Keys are resolved automatically per request, so the dashboard no longer
sends them in the request body.

- **Storage:** SQLite (`autoclipper.db`, mounted to the `autoclipper_data` volume in Docker).
- **Encryption:** `AUTOCLIPPER_SECRET` signs JWTs and derives the Fernet key. **Set this
  to a long random value in production** — if unset, an ephemeral key is used and stored
  keys cannot survive a restart.
- **Endpoints:** `POST /api/auth/register`, `POST /api/auth/login` (returns a JWT),
  `GET /api/auth/me`, `GET /api/auth/settings`, `PUT /api/auth/settings`.
- **Protected routes:** `/api/process`, `/api/trending`, `/api/trending/youtube` require a
  `Bearer` token. Other routes (status, files, library, YouTube upload) remain open for
  local/single-user use.

> **Note:** The YouTube OAuth upload token is still shared server-wide (single
> `client_secret.json`). Per-user YouTube accounts are a planned follow-up.

## Backend API

Async FastAPI server with a bounded job queue (semaphore, `MAX_CONCURRENT_JOBS`). Per-job logs are captured via a contextvar-aware handler so concurrent jobs don't interleave. Output is written to `OUTPUT_ROOT/<job_id>/` (`OUTPUT_ROOT` defaults to `output`).

### Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/process` | Submit a video (`source` URL/path or uploaded `file`, `content_type`, clip options); returns `job_id`. |
| GET | `/api/status/{job_id}` | Poll status, live logs, and result. |
| GET | `/api/jobs` | List recent jobs. |
| GET | `/api/files/{job_id}/{filename}` | Download a generated clip / asset. |
| GET | `/api/trending` | Curated trending topics (cached). |
| GET | `/api/trending/youtube` | **Real** YouTube trending via Data API v3 (`region`, `category`, `window_days`, `enrich`). Falls back to the general list when a niche has no regional trending (`category_filtered: false`). |
| POST | `/api/subtitle` | Generate + burn edited subtitles (karaoke highlight) into a clip. |
| POST | `/api/hook` | Burn a viral hook text overlay onto a clip. |
| GET | `/api/library` | List saved clips (manifest-driven). |
| POST | `/api/library/save` | Save a generated clip into the library. |
| POST | `/api/library/register` | Register a clip's metadata. |
| GET | `/api/youtube/status` | YouTube OAuth connection status. |
| POST | `/api/youtube/auth_url` | Begin YouTube OAuth (returns auth URL). |
| POST | `/api/youtube/callback` | Complete YouTube OAuth (exchanges code for token). |
| POST | `/api/youtube/upload` | Upload a clip to YouTube (OAuth). |
| POST | `/api/cleanup` | Manually trigger output cleanup (older than `JOB_RETENTION_HOURS`). |

## Dashboard Features

- **Clip Generator** — paste a YouTube URL or upload a file, choose a **Content Type** (General, Podcast, Gaming, Tutorial, IRL/Live) that tailors the AI prompt, then watch live logs and preview/download the vertical clips.
- **Trending** — pull real trending videos by region + content type, enriched by Gemini with clip ideas. Copy a link straight into the generator.
- **Subtitle editor** — per-cue caption editing (text, colors, box, font size, word-highlight karaoke), then burn to a new clip.
- **Hook overlay** — add styled viral hook text (top / center / bottom, scalable).
- **Gaming Cam + Gameplay** — for `content_type=gaming`, paste a single YouTube URL (or upload) and draw CAM + GAME boxes on a live preview; the backend downloads at 720p and crops/stacks them into a 9:16 vertical (`cam_top` / `game_top` / `side`).
- **Library** — saved clips with metadata, download / delete.
- **Settings** — enter API keys (encrypted in `localStorage`), pick Gemini model, YouTube OAuth connect, and trigger cleanup.

### Content Types

`CONTENT_TYPES` in `autoclipper/config.py` tailors the Gemini analysis prompt per niche (e.g. Gaming focuses on highlight-worthy plays, Podcast on quotable moments). The five supported types are: `general`, `podcast`, `gaming`, `tutorial`, `irl`. Content type is passed through `analyze.py` → `pipeline.py` → `/api/process`.

## YouTube Trending Notes

- Uses `videos.list chart=mostPopular` with `regionCode` (unlike `search.list`, which does not support reliable region filtering).
- **Content Type** is applied as a hard filter on `snippet.categoryId`. When a niche has no trending videos in that region (common — YouTube trending is region-based, not category-based), the endpoint returns the general list with `category_filtered: false` and the UI shows a hint.
- Shorts (<60s) and live streams are filtered out; Podcast mode keeps only longer-form videos (>10 min).

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Required. Gemini for viral detection + trending ideas. |
| `YOUTUBE_API_KEY` | — | YouTube Data API v3 key for trending + view counts. |
| `GROQ_API_KEY` | — | Required. Groq Whisper transcription. |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model. |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3-turbo` | Whisper model (Groq cloud). |
| `YOUTUBE_REGION` | `ID` | Default region for trending. |
| `MAX_CONCURRENT_JOBS` | `2` | Concurrent processing limit (semaphore). |
| `JOB_RETENTION_HOURS` | `24` | Auto-cleanup age for job outputs. |
| `MIN_CLIP_SECONDS` / `MAX_CLIP_SECONDS` | `15` / `60` | Clip length bounds. |
| `TARGET_CLIP_COUNT` | `8` | How many clips to request. |
| `YOUTUBE_COOKIES` | — | Optional Netscape cookies to bypass YouTube bot detection. |
| `SUBTITLE_FONT` / `SUBTITLE_FONT_SIZE` | `Arial` / `80` | Burned-in caption font + size. |
| `SUBTITLE_WORDS_PER_CUE` | `1` | Words per caption line (1 = word-by-word). |
| `SUBTITLE_MARGIN_V` | `120` | Bottom margin for captions (px). |
| `OUTPUT_ROOT` | `output` | Where job outputs are written. |
| `COMPOSE_PROJECT_NAME` | `autoclipper` | Keeps Docker container names stable. |

## Project Structure

```
autoclipper/
  config.py            # env / settings (keys, models, content types, clip bounds)
  utils.py             # logging, ffmpeg/ffprobe helpers
  ingest.py            # yt-dlp download / local file
  audio.py             # audio extraction + chunking
  transcribe.py        # Groq Whisper transcription (cloud, chunked)
  analyze.py           # Gemini viral moment detection (content-type aware)
  clip.py              # FFmpeg clip cutting (CRF 18, medium preset)
  reframe.py           # vertical 9:16 reframing (face/subject tracking)
  subtitles.py         # SRT generation + burned-in caption rendering
  hooks.py             # hook text overlay rendering
  trending_youtube.py  # real YouTube trending (mostPopular + category filter)
  youtube_uploader.py  # YouTube OAuth upload
  pipeline.py          # orchestration
  app.py               # FastAPI server + job queue + all endpoints
dashboard/
  src/
    App.jsx
    api.js
    components/        # SubmitForm, TrendingPage, ClipGrid, SubtitleEditor,
                       # HookModal, TranslateModal, YouTubeSettings, SettingsPage, ...
```

## Roadmap

- [x] Vertical 9:16 reframing with face/subject tracking
- [x] Burned-in subtitles from word timestamps
- [x] FastAPI backend + async job queue
- [x] React dashboard
- [x] Real YouTube trending (region + content type) with Gemini enrichment
- [x] Hook overlay, YouTube OAuth upload
- [x] Output auto-cleanup (`JOB_RETENTION_HOURS`)
- [x] Gaming cam + gameplay split from a single video (YouTube URL or upload) → 9:16
- [ ] Uploaded-clips tracking page (views + links per platform)

## Security

- **Never commit secrets.** `.env`, `client_secret.json`, and the `output/` folder are git-ignored. Only `.env.example` (with placeholder values) is tracked.
- API keys entered in the dashboard Settings page are stored in the browser's `localStorage` and sent only to the backend over your local network — they are **not** persisted server-side.
- The YouTube OAuth token is written to the `yt_config` Docker volume, not to the repo.

## Contributing

Contributions are welcome!

1. Fork the repo and create a feature branch (`git checkout -b feat/my-feature`).
2. Install dependencies for local dev (see [Local Development](#local-development-without-docker)).
3. Follow the existing code style (Black/isort for Python, ESLint for the dashboard).
4. Keep `.env` and secrets out of your commits.
5. Open a pull request describing your change.

Please file bugs and feature requests via [GitHub Issues](https://github.com/your-username/autoclipper/issues).

## License

Released under the [MIT License](LICENSE).

