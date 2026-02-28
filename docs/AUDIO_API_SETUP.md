# Audio API Setup Guide

## Overview

The YouTube Shorts Engine uses a smart 4-tier fallback system to select background audio based on your script's visual intent. This guide explains how to set up and use the audio integration.

## 4-Tier Fallback System

```
Tier 1: Local Cache (Instant) 
   ↓ (if not found)
Tier 2: Pixabay API (Free, 500 req/hour)
   ↓ (if fails)
Tier 3: Freesound API (Free, unlimited)
   ↓ (if fails)
Tier 4: Silent (Proceed without audio)
```

## Quick Setup

### 1. Get Free API Keys

#### Pixabay (Recommended - Tier 2)

1. Visit [https://pixabay.com/api/docs/](https://pixabay.com/api/docs/)
2. Sign up for a free account
3. Navigate to API documentation
4. Copy your API key

**Limits**: 500 requests/hour (free tier)

#### Freesound (Backup - Tier 3)

1. Visit [https://freesound.org/apiv2/apply/](https://freesound.org/apiv2/apply/)
2. Create an account
3. Apply for API credentials
4. Copy your API key

**Limits**: Unlimited (requires attribution in video description)

### 2. Configure Environment

Add to your `.env` file:

```bash
# Audio API Keys
PIXABAY_API_KEY=your_pixabay_api_key_here
FREESOUND_API_KEY=your_freesound_api_key_here

# Optional: Cache size limit (default: 500MB)
AUDIO_CACHE_MAX_SIZE_MB=500
```

### 3. Test the Setup

```python
from tools.audio_api import AudioFetcher
from core.audio_themes import AudioTheme

fetcher = AudioFetcher()
audio = fetcher.fetch_audio_for_theme(AudioTheme.PEACEFUL)

if audio:
    print(f"✓ Audio downloaded: {audio}")
else:
    print("✗ No audio found (check API keys)")
```

## Audio Themes

The system maps visual intents to audio themes:

| Visual Intent | Audio Theme | Description |
|--------------|-------------|-------------|
| `TENSION` | `EERIE` | Dark, suspenseful, tension-building |
| `CALM` | `PEACEFUL` | Calm, relaxing, soothing |
| `FAST` | `ENERGETIC` | Upbeat, fast-paced, exciting |
| `SERIOUS` | `PROFESSIONAL` | Corporate, serious, authoritative |
| `REFLECTIVE` | `CONTEMPLATIVE` | Thoughtful, reflective, introspective |
| `ASPIRATIONAL` | `INSPIRING` | Motivational, uplifting, aspirational |
| `NEUTRAL` | `NEUTRAL` | Generic, versatile background |

## Usage

### Automatic Selection (Recommended)

The workflow automatically selects audio based on script intent:

```python
# In your workflow, audio is selected automatically
state = {
    "visual_intent": "calm",  # Set by ScriptGenerationAgent
    # ... other fields
}

# select_audio_node runs automatically
# Audio is downloaded and cached
```

### Manual Selection

```python
from tools.audio_api import AudioFetcher
from core.audio_theme_map import get_audio_theme_for_intent
from core.visual_intents import VisualIntent

# Get intent
intent = VisualIntent.CALM

# Map to theme
theme = get_audio_theme_for_intent(intent)

# Fetch audio
fetcher = AudioFetcher()
audio_path = fetcher.fetch_audio_for_theme(theme)

print(f"Audio: {audio_path}")
```

## Cache Management

### Cache Location

Audio files are cached in:
```
assets/audio_cache/
├── eerie/
├── mysterious/
├── peaceful/
├── energetic/
├── professional/
├── contemplative/
├── inspiring/
└── neutral/
```

### Automatic Cleanup

The cache automatically cleans up when it exceeds the size limit:

```python
# Runs automatically when cache > AUDIO_CACHE_MAX_SIZE_MB
fetcher.cleanup_cache()
```

### Manual Cleanup

```python
from tools.audio_api import AudioFetcher

fetcher = AudioFetcher()
fetcher.cleanup_cache()  # Remove oldest files
```

### View Cache Status

```python
from pathlib import Path

cache_dir = Path("assets/audio_cache")
total_size = sum(f.stat().st_size for f in cache_dir.rglob("*.mp3"))
print(f"Cache size: {total_size / (1024 * 1024):.1f} MB")
```

## Troubleshooting

### No Audio Downloaded

**Symptoms**: `audio_file_path` is `None`

**Solutions**:
1. Check API keys are set correctly in `.env`
2. Verify internet connection
3. Check API rate limits:
   - Pixabay: 500 requests/hour
   - Freesound: Check your account status
4. Review logs for specific error messages

### API Rate Limit Exceeded

**Symptoms**: `Pixabay fetch failed: 429 Too Many Requests`

**Solutions**:
1. Wait for rate limit to reset (1 hour for Pixabay)
2. Use cached audio (Tier 1 doesn't hit API)
3. Set up Freesound API as backup (Tier 3)
4. Consider upgrading Pixabay plan for higher limits

### Cache Not Working

**Symptoms**: Audio downloads every time

**Solutions**:
1. Check `assets/audio_cache/` directory exists and is writable
2. Verify files are being saved (check directory after first download)
3. Ensure theme names match (case-sensitive)

### Downloaded Audio Quality Issues

**Symptoms**: Audio sounds low quality or distorted

**Solutions**:
1. Pixabay provides preview quality - consider upgrading for full quality
2. Freesound offers higher quality - check `preview-hq-mp3` URL
3. Manually download high-quality audio and place in cache directory

## Advanced Configuration

### Custom Search Queries

Edit `core/audio_theme_map.py` to customize search queries:

```python
def get_search_queries_for_theme(theme: AudioTheme) -> list[str]:
    queries = {
        AudioTheme.PEACEFUL: [
            "calm peaceful nature",  # Default
            "meditation ambient",    # Add custom
            "spa relaxation music"   # Add custom
        ],
        # ... other themes
    }
    return queries.get(theme, ["background music"])
```

### Custom Cache Location

```python
# In tools/audio_api.py
class AudioFetcher:
    def __init__(self):
        # Custom cache directory
        self.cache_dir = Path("custom/path/to/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
```

### Disable Audio Fetching

To skip audio entirely:

```python
# Don't set API keys in .env
# System will proceed without background audio
```

Or modify the node to skip:

```python
# In agents/node.py
def select_audio_node(state: ShortsState) -> Dict[str, Any]:
    # Skip audio selection
    return {
        "audio_theme": None,
        "audio_file_path": None,
        "current_step": "audio_skipped"
    }
```

## Attribution Requirements

### Freesound

If using Freesound API, you **must** attribute the audio in your video description:

```
Background music from Freesound.org:
- [Track Name] by [Artist Name]
  https://freesound.org/people/[username]/sounds/[sound_id]/
```

### Pixabay

No attribution required, but appreciated:

```
Background music from Pixabay.com
```

## Best Practices

1. **Set Both API Keys**: Pixabay for primary, Freesound for backup
2. **Monitor Cache Size**: Keep under 500MB for optimal performance
3. **Test Before Production**: Download a few samples to verify quality
4. **Review Selections**: Manually check audio matches video tone
5. **Respect Rate Limits**: Don't spam API calls during testing

## Performance Tips

- **First Run**: Slower (downloads audio)
- **Subsequent Runs**: Fast (uses cache)
- **Cache Hit Rate**: Aim for >80% to minimize API calls
- **Cleanup Frequency**: Runs automatically, no manual intervention needed

---

**Related Documentation**:
- [Main README](file:///c:/Users/anshc/anshatwork/YTShortsEnginer/README.md)
- [Walkthrough](file:///C:/Users/anshc/.gemini/antigravity/brain/71d5029c-2e00-4af7-bae3-21b924bddf33/walkthrough.md)
- [Script Parser Guide](file:///c:/Users/anshc/anshatwork/YTShortsEnginer/docs/SCRIPT_PARSER_GUIDE.md)
