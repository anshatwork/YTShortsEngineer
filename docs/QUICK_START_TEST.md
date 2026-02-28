# Quick Start Guide: Running the Updated Test

## Prerequisites

1. **Background Video**: Ensure `assets\op_bg1.mp4` exists ✅
2. **Python Dependencies**: Install required packages
3. **Optional**: Chatterbox API key for production-quality TTS

## Running the Test

### Option 1: With Chatterbox API (Recommended)
```bash
# Set environment variable
$env:CHATTERBOX_API_KEY = "your_api_key_here"

# Run test
python test_script_parser.py
```

### Option 2: With pyttsx3 Fallback
```bash
# Just run the test (no API key needed)
python test_script_parser.py
```

### Option 3: With ElevenLabs (Alternative)
```bash
# Set ElevenLabs API key
$env:ELEVENLABS_API_KEY = "your_elevenlabs_key"

# Run test
python test_script_parser.py
```

## What the Test Does

### Phase 1: Script Parsing
- Extracts short-form scripts from long-form content
- Validates structure markers: `[HOOK]`, `[BRIDGE]`, `[CORE SCRIPT]`
- Checks word count (75-150 words for 30-60s videos)

### Phase 2: Intent Classification & Audio Selection
- Maps content to visual intent (e.g., FINANCIAL)
- Selects appropriate audio theme
- Fetches background music (if API configured)

### Phase 3: Complete Workflow Execution
1. **Script Ready**: Uses parsed script
2. **Video Selection**: ⚠️ SKIPPED - Using background video
3. **Voiceover Generation**: 
   - Cleans script (removes markers)
   - Generates TTS audio
   - Saves to `output/voiceover_*.mp3`
4. **Video Assembly**:
   - Combines background video + voiceover + music
   - Saves to `output/final_*.mp4`

## Expected Output

```
================================================================================
END-TO-END INTEGRATION TEST
================================================================================

================================================================================
PHASE 1: SCRIPT PARSING
================================================================================

Source content: 1234 characters
Topic: Uranium price

✓ Successfully parsed 1 script(s)

--- EXTRACTED SCRIPT ---
Key Point: Uranium ETFs repeating Silver playbook
Word Count: 145
Hook: Did you know Uranium ETFs in 2026...

================================================================================
PHASE 2: INTENT CLASSIFICATION & AUDIO SELECTION
================================================================================

Expected Visual Intent: financial
Mapped Audio Theme: corporate

--- TESTING AUDIO FETCHER ---
✓ Audio fetched successfully: audio_cache/corporate_theme.mp3

================================================================================
PHASE 3: EXECUTING COMPLETE WORKFLOW
================================================================================

--- STEP 5: VIDEO SELECTION ---
✓ Using pre-configured background video: assets\op_bg1.mp4
  Skipping content sourcing (background video already provided)

--- STEP 6: VOICEOVER GENERATION ---
✓ Voiceover generated: output/voiceover_Uranium pr.mp3

--- STEP 7: VIDEO ASSEMBLY ---
Video mode: background_only
Audio mode: voiceover
✓ Video assembled: output/final_uranium_price_20260203.mp4
  File size: 12.34 MB

================================================================================
🎉 END-TO-END WORKFLOW TEST PASSED!
================================================================================

✓ Scripts parsed: 1
✓ Voiceover generated: output/voiceover_Uranium pr.mp3
✓ Video assembled: output/final_uranium_price_20260203.mp4
✓ Background video used: assets\op_bg1.mp4
```

## Troubleshooting

### Issue: "No module named 'pyttsx3'"
```bash
pip install pyttsx3
```

### Issue: "FFmpeg not found"
```bash
# Install FFmpeg
choco install ffmpeg  # Windows with Chocolatey
# OR download from https://ffmpeg.org/
```

### Issue: "Chatterbox API failed"
- Check API key is correct
- Verify API endpoint is accessible
- System will automatically fall back to pyttsx3

### Issue: "Background video not found"
- Ensure `assets\op_bg1.mp4` exists
- Check file path in test configuration
- Use absolute path if needed

## Key Improvements

### ✅ No More Structure Markers in Audio
The voiceover will now sound like:
> "Did you know Uranium ETFs in 2026 are following the exact same playbook as Silver in 2025? Let me break down the three key parallels..."

Instead of:
> "Hook. Did you know Uranium ETFs... Bridge. Let me break down... Core Script. First, the structural deficit..."

### ✅ Actual Chatterbox API Integration
- Production-quality TTS voices
- Voice presets for different content types
- Configurable stability, clarity, and speed
- Graceful fallback to pyttsx3

### ✅ Optimized Test Workflow
- No unnecessary API calls
- Uses provided background video
- Faster test execution
- Clear validation output

## Next Steps

1. **Run the test**: `python test_script_parser.py`
2. **Check output**: Review generated files in `output/` directory
3. **Listen to audio**: Verify structure markers are removed
4. **Watch video**: Ensure background video + voiceover sync properly
5. **Iterate**: Adjust voice presets or content as needed
