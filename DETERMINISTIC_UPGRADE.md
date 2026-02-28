# YouTube Shorts Engine - Quick Reference

## New Configuration Options

Add to your `.env` file:

```bash
# Video Library Configuration
VIDEO_LIBRARY_PATH=./assets/video_library

# Safe Base Videos (Optional - for Tier 2 fallback)
CALM_BASE_VIDEO=./assets/safe_base/calm_nature.mp4
FAST_BASE_VIDEO=./assets/safe_base/city_timelapse.mp4
SERIOUS_BASE_VIDEO=./assets/safe_base/professional_bg.mp4
REFLECTIVE_BASE_VIDEO=./assets/safe_base/rainy_window.mp4
TENSION_BASE_VIDEO=./assets/safe_base/dark_atmosphere.mp4

# LLM Fallback (Set to 'false' for strict determinism)
ENABLE_LLM_FALLBACK=true
```

## Visual Intent Enums

### Hook Styles
- `curiosity` - Start with weird facts or questions
- `fear` - "Stop doing this..." or "This is why you're failing..."
- `identity` - "If you are X, you need to hear this..."
- `contradiction` - "Everything you know about X is wrong."

### Visual Intents
- `calm` - Slow, reflective, peaceful delivery
- `fast` - Energetic, rapid-fire, exciting delivery
- `serious` - Professional, authoritative, educational tone
- `reflective` - Thoughtful, introspective, contemplative
- `tension` - Suspenseful, dramatic, urgent

## Tiered Video Fetching

1. **Tier 1: Local Library** (Preferred)
   - Location: `assets/video_library/{intent}/`
   - No API calls, instant selection
   - Fully deterministic

2. **Tier 2: Safe Base** (High Priority)
   - Curated background videos
   - Configured in `.env`
   - Fully deterministic

3. **Tier 3: External Search** (Medium Priority)
   - Uses `INTENT_QUERY_MAP`
   - Queries are deterministic
   - Topic text never used

4. **Tier 4: LLM Fallback** (Last Resort)
   - LLM generates intent-only queries
   - Can be disabled
   - Less deterministic

## Testing Commands

```bash
# Test determinism (3 runs)
python test_determinism.py

# Test with custom topic
python test_determinism.py "Your topic here"

# Run full workflow
python main.py
```

## Key Metrics to Monitor

- **Validation Success Rate**: Should be 100%
- **Determinism Score**: Target 90%+ (Tiers 1-3)
- **Topic Isolation**: Should be 0 instances
- **Tier Distribution**: Prefer Tiers 1-2

## Directory Structure

```
YTShortsEnginer/
├── core/
│   ├── visual_intents.py       # Enums and validation
│   └── intent_query_map.py     # Query mappings
├── agents/
│   ├── script_generation.py    # Updated with enum selection
│   └── video_selection.py      # Tiered fetching
├── assets/
│   ├── video_library/          # Local videos (Tier 1)
│   │   ├── calm/
│   │   ├── fast/
│   │   ├── serious/
│   │   ├── reflective/
│   │   └── tension/
│   └── safe_base/              # Safe base videos (Tier 2)
├── test_determinism.py         # Determinism test script
└── main.py                     # Main workflow
```

## Troubleshooting

### All tiers failing?
- Check API keys in `.env`
- Verify internet connection
- Check `INTENT_QUERY_MAP` has queries for your intent

### Low determinism score?
- Populate local video library
- Configure safe base videos
- Add more queries to `INTENT_QUERY_MAP`

### Topic text in queries?
- Disable LLM fallback: `ENABLE_LLM_FALLBACK=false`
- Check Tier 3 is working properly
- Review logs for Tier 4 usage
