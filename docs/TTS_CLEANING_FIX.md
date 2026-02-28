# TTS Script Cleaning Fix - Summary

## Problem
The voice synthesis agent was not properly cleaning scripts for TTS, resulting in:
1. Structure markers like `[HOOK]`, `[BRIDGE]`, `[CORE SCRIPT]` being spoken
2. Escaped newlines (`\n` as literal text) being spoken as "backslash n"
3. Awkward pauses due to improper newline handling

## Root Causes

### Issue 1: Escaped Newlines
LLM-generated scripts sometimes contain literal `\n` characters (escaped newlines) instead of actual newline characters. For example:
```
"[HOOK]\nUranium in 2026..."
```
Instead of:
```
[HOOK]
Uranium in 2026...
```

### Issue 2: Incomplete Marker Removal
The regex patterns weren't capturing trailing newlines after markers, leaving orphaned newlines at the start of sentences.

### Issue 3: Newlines Not Converted to Spaces
Single newlines were being preserved, causing the TTS to pause awkwardly mid-sentence.

## Solution

Updated `agents/voice_synthesis.py` with a comprehensive cleaning function:

### Step 1: Handle Escaped Newlines
```python
if '\\n' in script:
    script = script.replace('\\n', '\n')
```

### Step 2: Remove Structure Markers
```python
cleaned = re.sub(r'\[HOOK\]\s*\n?', '', script)
cleaned = re.sub(r'\[BRIDGE\]\s*\n?', '', cleaned)
cleaned = re.sub(r'\[CORE SCRIPT\]\s*\n?', '', cleaned)
```

### Step 3: Normalize Whitespace
```python
# Preserve paragraph breaks
cleaned = re.sub(r'\n\s*\n', '<<PARAGRAPH>>', cleaned)

# Convert single newlines to spaces
cleaned = re.sub(r'\n', ' ', cleaned)

# Restore paragraph breaks
cleaned = cleaned.replace('<<PARAGRAPH>>', '\n\n')

# Clean up multiple spaces
cleaned = re.sub(r' +', ' ', cleaned)
```

## Testing

### Test File: `test_voice_video_only.py`
A simplified test that:
- Skips script generation
- Uses a pre-written, properly formatted script
- Tests only voice synthesis and video assembly
- Uses `overlay_style: "background_only"` mode

### Usage
```bash
python test_voice_video_only.py
```

This will:
1. Generate voiceover from the clean script
2. Assemble video with background video + voiceover + captions
3. Output final video to `output/` directory

## Expected Output

### Before Fix
```
"bracket HOOK backslash n Uranium in 2026 backslash n bracket BRIDGE..."
```

### After Fix
```
"Uranium in 2026 is repeating Silver's 2025 playbook. We saw Silver break a 13-year resistance..."
```

## Files Modified

1. **`agents/voice_synthesis.py`**
   - Enhanced `_clean_script_for_tts()` method
   - Added escaped newline handling
   - Improved whitespace normalization
   - Added debug logging

2. **`test_voice_video_only.py`** (new)
   - Simplified test for voice + video only
   - Pre-written script about Uranium/Silver markets
   - Tests background_only overlay style

3. **`test_newline_issue.py`** (new)
   - Diagnostic tool to identify escaped vs actual newlines
   - Demonstrates the cleaning process

## Verification

Run the test and check:
- ✅ No structure markers in audio
- ✅ No "backslash n" being spoken
- ✅ Natural flow between sentences
- ✅ Proper pauses only at paragraph breaks
- ✅ Clean, professional-sounding voiceover
