# Script Parser & TTS Integration Updates

## Summary of Changes

This document outlines the updates made to fix the TTS audio generation issue and improve the test workflow.

## Issues Fixed

### 1. **Structure Markers in TTS Audio** ✅
**Problem**: The script was sending `[HOOK]`, `[BRIDGE]`, and `[CORE SCRIPT]` markers to the TTS engine, causing them to be spoken in the audio.

**Solution**: Added `_clean_script_for_tts()` method in `VoiceSynthesisAgent` that:
- Removes all structure markers before sending to TTS
- Preserves the actual content to be spoken
- Cleans up extra whitespace

**Files Modified**:
- `agents/voice_synthesis.py`

### 2. **Chatterbox TTS API Integration** ✅
**Problem**: Chatterbox TTS was using a mock implementation with TODO comments.

**Solution**: Implemented actual Chatterbox API integration:
- Added API key and URL configuration via environment variables
- Implemented proper HTTP request with voice presets
- Maintained fallback to pyttsx3 if API is not configured
- Added comprehensive error handling and logging

**Files Modified**:
- `tools/tts/chatterbox.py`

**Environment Variables Required**:
```bash
CHATTERBOX_API_KEY=your_api_key_here
CHATTERBOX_API_URL=https://api.chatterboxtts.com/v1/synthesize  # Optional, has default
```

### 3. **Test Script Optimization** ✅
**Problem**: Test was attempting to fetch videos from YouTube when a background video was already provided.

**Solution**: Updated test workflow to:
- Skip content sourcing agent entirely
- Use pre-configured background video (`assets\op_bg1.mp4`)
- Set overlay style to `background_only`
- Update validation to check workflow completion instead of video selection

**Files Modified**:
- `test_script_parser.py`

## Code Changes Detail

### agents/voice_synthesis.py
```python
def _clean_script_for_tts(self, script: str) -> str:
    """Remove structure markers from script for TTS generation."""
    cleaned = re.sub(r'\[HOOK\]\s*', '', script)
    cleaned = re.sub(r'\[BRIDGE\]\s*', '', cleaned)
    cleaned = re.sub(r'\[CORE SCRIPT\]\s*', '', cleaned)
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
    return cleaned.strip()
```

### tools/tts/chatterbox.py
```python
# Check for Chatterbox API configuration
api_key = os.getenv("CHATTERBOX_API_KEY")
api_url = os.getenv("CHATTERBOX_API_URL", "https://api.chatterboxtts.com/v1/synthesize")

if api_key:
    # Use actual Chatterbox API
    response = requests.post(api_url, headers=headers, json=payload, timeout=60)
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(response.content)
        return output_path
else:
    # Fallback to pyttsx3
    ...
```

### test_script_parser.py
```python
# Initial state configuration
state = {
    "overlay_style": "background_only",
    "background_video_path": "assets\op_bg1.mp4",
    ...
}

# Skip content sourcing
print("✓ Using pre-configured background video")
state["selected_video"] = None

# Updated validation
all_core_passed = (
    len(scripts) > 0 and 
    state.get("voiceover_audio_path") is not None and
    state.get("final_video_path") is not None
)
```

## Testing

### Test TTS Cleaning
A dedicated test script was created to verify marker removal:
```bash
python test_tts_cleaning.py
```

This test verifies:
- ✅ All markers are removed
- ✅ Content is preserved
- ✅ No empty results
- ✅ Whitespace is cleaned properly

### End-to-End Test
Run the complete workflow test:
```bash
python test_script_parser.py
```

This test validates:
1. **Script Parsing**: Extract scripts from source content
2. **Intent Classification**: Map to audio themes
3. **Audio Selection**: Fetch background music
4. **Video Selection**: Skip (using background video)
5. **Voiceover Generation**: Generate TTS with cleaned script
6. **Video Assembly**: Combine background video + voiceover + music

## Voice Presets

The Chatterbox integration supports voice presets for different content types:

### Finance Preset
```python
"finance": {
    "voice_id": "professional_male_deep",
    "stability": 0.7,  # More authoritative
    "clarity": 0.8,    # High clarity for numbers
    "rate": 150        # Slower for complex info
}
```

### Finance Energetic Preset
```python
"finance_energetic": {
    "voice_id": "professional_female_clear",
    "stability": 0.6,
    "clarity": 0.9,
    "rate": 170
}
```

## Next Steps

1. **Configure Chatterbox API**: Add `CHATTERBOX_API_KEY` to environment
2. **Test with Real API**: Run test with actual API credentials
3. **Verify Audio Quality**: Check that generated audio sounds natural
4. **Adjust Voice Presets**: Fine-tune voice settings based on content type
5. **Add More Presets**: Create presets for other content categories (tech, lifestyle, etc.)

## Notes

- The script cleaning happens **before** TTS generation, so the markers are never spoken
- The cleaned script is logged for debugging purposes
- Fallback to pyttsx3 ensures the system works even without API keys
- Background video mode is now the default for testing
