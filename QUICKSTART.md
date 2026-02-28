# Quick Start Guide - YouTube Shorts Engine

## 🚀 Installation & Setup

### 1. Install Dependencies

```powershell
# Install Python packages
pip install -r requirements.txt
```

### 2. Install FFmpeg

**Windows:**
1. Download FFmpeg from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to System PATH
4. Verify: `ffmpeg -version`

### 3. Configure API Keys

```powershell
# Copy template
cp .env.example .env

# Edit .env with your API keys
notepad .env
```

Required keys:
- **YouTube Data API**: [Get from Google Cloud Console](https://console.cloud.google.com/)
- **HuggingFace API**: [Get from huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
- **ElevenLabs API**: [Get from elevenlabs.io](https://elevenlabs.io/)

### 4. Add Background Video (Optional)

Place a background video at:
```
./assets/background.mp4
```

Or leave empty to use solid color fallback.

---

## ▶️ Running the Workflow

```powershell
python main.py
```

**Expected Flow:**

1. **Query Generation** → System generates trending search queries
2. **Fetch Videos** → Displays video candidates
3. **[PAUSE]** Select a video (auto-selects #1 in demo)
4. **Script Generation** → AI creates narration script (30-60 sec)
5. **Video Rendering** → Downloads video, generates voiceover, creates captions, assembles final video
6. **[PAUSE]** Review video at `./output/[video_id]_final.mp4`
7. **Approve/Reject** → Type `y` or `n`
8. **Upload** → Placeholder logs (ready for YouTube API integration)

---

## 📂 Output Files

After running, check `./output/` directory:

```
output/
├── [video_id].mp4              # Downloaded trendy video
├── [video_id]_voiceover.mp3    # Generated voiceover
└── [video_id]_final.mp4        # Final rendered Short
```

---

## 🔧 Troubleshooting

### "ELEVENLABS_API_KEY not found"
→ Check `.env` file exists and has valid API key

### "FFmpeg not found"
→ Ensure FFmpeg installed and in PATH: `ffmpeg -version`

### "Failed to download video"
→ Check internet connection and YouTube URL accessibility

### Model download on first run
→ Whisper downloads ~140MB model on first run (normal)

### MoviePy warnings
→ ImageMagick warnings are non-critical, video will still render

---

## 🎯 Next Steps

1. **Test with your own topic:**
   - Edit `broad_topic` in `main.py`
   - Run `python main.py`

2. **Customize captions:**
   - Modify `create_caption_clips()` in `tools/editor_engine.py`
   - Adjust font, colors, animations

3. **Implement YouTube upload:**
   - Add OAuth2 credentials
   - Update `upload_to_yt_node()` in `agents/node.py`

4. **Add more background videos:**
   - Place videos in `./assets/`
   - Update state with different paths per execution

---

## 📊 Summary of Files

| File | Purpose | Status |
|------|---------|--------|
| `agents/state.py` | TypedDict state schemas | ✅ Complete |
| `agents/node.py` | All workflow nodes | ✅ Complete |
| `agents/graph.py` | LangGraph workflow | ✅ Complete |
| `tools/editor_engine.py` | Video editing functions | ✅ Complete |
| `tools/youtube_api.py` | YouTube Data API | ✅ Complete |
| `main.py` | Execution script | ✅ Complete |
| `requirements.txt` | Dependencies | ✅ Complete |
| `.env.example` | Config template | ✅ Complete |
| `README.md` | Documentation | ✅ Complete |

---

**Questions?** Check the [README.md](file:///c:/Users/anshc/anshatwork/YTShortsEnginer/README.md) or [walkthrough.md](file:///C:/Users/anshc/.gemini/antigravity/brain/9e39ece9-87bd-4bc2-8d45-529be72fed13/walkthrough.md) for detailed information.
