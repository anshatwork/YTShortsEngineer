# YouTube Shorts Engine 🎬

An automated YouTube Shorts creator powered by LangGraph, AI, and video editing tools. Transform trending topics **or long-form content** into high-retention vertical videos with AI-generated scripts, professional voiceovers, smart background audio, and Hormozi-style captions.

## Features

✨ **AI-Powered Workflow**
- Query generation via HuggingFace LLMs
- Trending video discovery using YouTube Data API
- Automated script creation for engaging narration
- Professional voiceover with ElevenLabs
- **NEW**: Script extraction from podcasts/articles
- **NEW**: Auto-intent classification from script tone

🎵 **Smart Audio Integration**
- **NEW**: 4-tier audio fallback (cache → Pixabay → Freesound → silent)
- **NEW**: Automatic background music selection based on intent
- **NEW**: Local caching with LRU cleanup

🎥 **Advanced Video Editing**
- Split-screen vertical layout (9:16)
- Whisper-based audio-visual synchronization
- Hormozi-style dynamic captions (bold, centered, color-coded)
- Automatic video assembly with MoviePy

🔄 **Human-in-the-Loop (HITL)**
- Manual video selection from candidates
- Video review before upload
- State persistence with LangGraph checkpointing

## Architecture

```
YouTube Shorts Creator Workflow
├── Generate Queries → Fetch Assets → [HITL: Select Video]
├── Generate Script → Render Video → [HITL: Review]
└── Upload to YouTube (conditional on approval)
```

## Installation

1. **Clone the repository**
```bash
cd c:\Users\anshc\anshatwork\YTShortsEnginer
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Install FFmpeg** (required for MoviePy)
   - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)
   - Add to PATH

4. **Configure environment variables**
```bash
cp .env.example .env
```

Edit `.env` with your API keys:
```
YT_API_KEY=your_youtube_api_key
HUGGINGFACE_API_KEY=your_huggingface_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
BACKGROUND_VIDEO_PATH=./assets/background.mp4
OUTPUT_DIR=./output

# Optional: Audio API keys for background music
PIXABAY_API_KEY=your_pixabay_api_key
FREESOUND_API_KEY=your_freesound_api_key
```

## Usage

### Basic Workflow

```bash
python main.py
```

The script will:
1. Generate search queries from your topic
2. Fetch trending YouTube videos
3. **[INTERRUPT 1]** Display candidates for manual selection
4. Generate a viral script
5. Render video with voiceover and captions
6. **[INTERRUPT 2]** Request review approval
7. Upload to YouTube (if approved)

### Programmatic Usage

```python
from agents.graph import app
from agents.state import ShortsState

# Initialize state
initial_state: ShortsState = {
    "broad_topic": "Looksmaxxing jawline tips",
    "overlay_style": "split_screen",
    "background_video_path": "./assets/background.mp4",
    # ... other fields
}

config = {"configurable": {"thread_id": "unique_id"}}

# Run workflow
for event in app.stream(initial_state, config):
    print(event)

# Update state at interrupts
app.update_state(config, {"selected_video": video})
```

## Project Structure

```
YTShortsEnginer/
├── agents/
│   ├── state.py          # TypedDict state schemas
│   ├── node.py           # LangGraph node implementations
│   └── graph.py          # Workflow graph definition
├── tools/
│   ├── youtube_api.py    # YouTube Data API integration
│   └── editor_engine.py  # Video editing functions
├── output/               # Generated videos (auto-created)
├── assets/               # Background videos (create manually)
├── main.py               # Main execution script
├── requirements.txt      # Python dependencies
└── .env.example          # Environment variable template
```

## Key Components

### State Management (`agents/state.py`)
- `ShortsState`: Complete workflow state with TypedDict
- `VideoAsset`: YouTube video metadata
- `WordTimestamp`: Whisper timestamp output

### Nodes (`agents/node.py`)
- `generate_queries_node`: AI query generation
- `generate_script_node`: Script creation with HuggingFace
- `render_video_node`: Complete video rendering pipeline
- `review_node`: HITL review checkpoint
- `upload_to_yt_node`: YouTube upload (placeholder)

### Editor Engine (`tools/editor_engine.py`)
- `download_video()`: yt-dlp video downloader
- `generate_voiceover()`: ElevenLabs text-to-speech
- `extract_word_timestamps()`: Whisper transcription
- `create_caption_clips()`: Hormozi-style captions
- `assemble_split_screen_video()`: Final video assembly

## Configuration

### API Keys

**YouTube Data API**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → Enable YouTube Data API v3
3. Create credentials → API Key

**HuggingFace**
1. Sign up at [huggingface.co](https://huggingface.co/)
2. Go to Settings → Access Tokens
3. Create new token with read access

**ElevenLabs**
1. Sign up at [elevenlabs.io](https://elevenlabs.io/)
2. Go to Profile → API Key
3. Find your preferred voice ID in Voice Library

### Background Video

Place your background video (Minecraft, GTA parkour, etc.) in `./assets/background.mp4` or update `BACKGROUND_VIDEO_PATH` in `.env`.

## Troubleshooting

### FFmpeg Errors
- Ensure FFmpeg is installed and in PATH
- Test: `ffmpeg -version`

### Whisper Model Download
- First run downloads the Whisper model (~140MB for 'base')
- Requires stable internet connection

### ElevenLabs Rate Limits
- Free tier: 10,000 characters/month
- Monitor usage in ElevenLabs dashboard

### MoviePy Errors
- If ImageMagick warnings appear, install [ImageMagick](https://imagemagick.org/)
- Set `IMAGEMAGICK_BINARY` environment variable if needed

## Persistence and Authentication (Supabase)

The Long-to-Shorts API and frontend support persistent, multi-user job storage via [Supabase](https://supabase.com).

### 1 — Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and create a free project.
2. In **Authentication → Providers**, enable **Google** and/or **GitHub**.
   - Add `http://localhost:3000/auth/callback` (and your production URL) to **Redirect URLs** under Authentication → URL Configuration.
3. In **SQL Editor**, run the migration:
   ```
   supabase/migrations/001_jobs.sql
   ```
   This creates the `clip_jobs`, `edit_jobs`, and `uploads` tables with RLS policies.

### 2 — Configure the FastAPI backend

Copy `.env.example` to `.env` and fill in the Supabase section:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key   # never expose publicly
SUPABASE_JWT_SECRET=your-jwt-secret               # Project Settings → API → JWT Secret

JOB_STORE=supabase        # switch from in-memory to Supabase
AUTH_DISABLED=false        # require JWT on all job endpoints
FRONTEND_URL=http://localhost:3000   # tighten CORS
```

`AUTH_DISABLED=true` (the default in the example) skips JWT verification so you can run the pipeline locally without signing in.

### 3 — Configure the Next.js frontend

Copy `frontend/.env.local.example` to `frontend/.env.local`:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### 4 — Run both servers

```bash
# FastAPI (backend)
python agents/long_to_shorts/api/server.py

# Next.js (frontend)
cd frontend && npm run dev
```

Open `http://localhost:3000`. You will be redirected to `/login` to sign in with Google or GitHub. After sign-in, all job submissions are persisted under your user account and survive API restarts.

### Testing checklist

- [ ] Sign in with Google / GitHub → redirected to workspace
- [ ] Submit a job → row appears in Supabase `clip_jobs` table with your `user_id`
- [ ] Restart the FastAPI server → `GET /jobs` still returns your job history
- [ ] Open the job detail page → pipeline progress tracked via `current_node`
- [ ] Log in with a second account → cannot see the first account's jobs (404)
- [ ] Pipeline completes → `clips` JSONB populated; frontend renders clip grid
- [ ] TTS edit job completes → `edit_jobs` row updated, output URL accessible
- [ ] Sign out → redirected to `/login`; workspace not accessible without auth

---

## Roadmap

- [ ] Implement actual YouTube upload (OAuth2)
- [ ] Add multiple LLM provider support
- [ ] Background video auto-download from stock sources
- [ ] A/B testing for caption styles
- [ ] Batch processing for multiple topics
- [ ] Supabase Storage for clip/upload files (phase 2)
- [ ] Job cancellation + retention cleanup cron
- [ ] Per-user rate limits on job submission

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please open an issue or PR for improvements.

---

**Built with**: LangGraph • HuggingFace • ElevenLabs • Whisper • MoviePy • yt-dlp
