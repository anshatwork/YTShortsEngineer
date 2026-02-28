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

## Roadmap

- [ ] Implement actual YouTube upload (OAuth2)
- [ ] Add multiple LLM provider support
- [ ] Background video auto-download from stock sources
- [ ] A/B testing for caption styles
- [ ] Batch processing for multiple topics
- [ ] Web UI for workflow management

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please open an issue or PR for improvements.

---

**Built with**: LangGraph • HuggingFace • ElevenLabs • Whisper • MoviePy • yt-dlp
