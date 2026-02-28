# Script Parser Guide

## Overview

The Script Parser Agent extracts multiple viral-worthy short-form scripts from long-form content (podcasts, articles, transcripts, etc.). Each extracted script is optimized for YouTube Shorts with hooks, structure, and length validation.

## Quick Start

### 1. Prepare Your Content

```python
# Your long-form content (podcast transcript, article, etc.)
source_content = """
[Paste your content here - can be several paragraphs]
"""
```

### 2. Run the Parser

```python
from agents.script_parser import ScriptParserAgent

agent = ScriptParserAgent()
result = agent.run({"source_content": source_content})

scripts = result["parsed_script_list"]
print(f"Extracted {len(scripts)} shorts!")
```

### 3. Review Extracted Scripts

```python
for script in scripts:
    print(f"Key Point: {script['key_point']}")
    print(f"Word Count: {script['word_count']}")
    print(f"Hook: {script['hook']}")
    print(f"Full Script:\n{script['script']}\n")
```

## How It Works

### Extraction Process

1. **Analyze Content**: LLM reads your long-form content
2. **Identify Segments**: Finds 3-5 viral-worthy segments
3. **Reword for Shorts**: Adapts content for 30-60s format
4. **Optimize Hooks**: Creates attention-grabbing first 3 seconds
5. **Add Structure**: Enforces `[HOOK]/[BRIDGE]/[CORE SCRIPT]` format
6. **Validate Length**: Ensures 75-150 words (~30-60s when spoken)

### Output Format

Each extracted script includes:

```python
{
    "script": "Full script with [HOOK]/[BRIDGE]/[CORE SCRIPT] markers",
    "hook": "Just the hook portion (optimized for first 3s)",
    "word_count": 120,
    "key_point": "Brief note on what this segment covers",
    "index": 0
}
```

## Best Practices

### Content Preparation

✅ **Good Content**:
- Podcast transcripts (10-30 minutes)
- Blog posts with clear points
- Interview transcripts
- Educational content with distinct topics

❌ **Avoid**:
- Very short content (<500 words)
- Highly technical jargon without context
- Content without clear narrative structure

### Length Targets

- **Minimum**: 75 words (~30 seconds)
- **Optimal**: 100-120 words (~40-50 seconds)
- **Maximum**: 150 words (~60 seconds)

Scripts outside this range will trigger warnings but won't fail.

### Hook Optimization

The parser automatically optimizes hooks using these patterns:

- **Curiosity**: "Did you know that..."
- **Fear**: "Stop doing this..."
- **Identity**: "If you're X, you need to hear this..."
- **Contradiction**: "Everything you know about X is wrong..."

## Testing

### Run the Test Script

```bash
python test_script_parser.py
```

This tests extraction with a sample podcast transcript about productivity.

### Expected Output

```
================================================================================
TESTING SCRIPT PARSER AGENT
================================================================================

Source content length: 2156 characters
Source content word count: ~350 words

--------------------------------------------------------------------------------
Running ScriptParserAgent...
--------------------------------------------------------------------------------

✓ Parser completed successfully!
Current step: scripts_parsed

Extracted 5 scripts:
================================================================================

--- SCRIPT 1 ---
Key Point: Brain's 90-minute focus cycle
Word Count: 95
Hook: Did you know your brain can only focus for 90 minutes?

Full Script:
[HOOK]
Did you know your brain can only focus for 90 minutes?
[BRIDGE]
It's called the ultradian rhythm, and it's hardwired into your biology.
[CORE SCRIPT]
Most people fight this natural cycle, chugging coffee and forcing themselves 
to work for hours. But science shows this is counterproductive. Work in 
90-minute blocks with 15-20 minute breaks, and your productivity skyrockets.
--------------------------------------------------------------------------------

[... more scripts ...]

================================================================================
VALIDATION SUMMARY
================================================================================
Script 1: ✓ VALID (words: 95, structure: True)
Script 2: ✓ VALID (words: 110, structure: True)
Script 3: ✓ VALID (words: 88, structure: True)
Script 4: ✓ VALID (words: 102, structure: True)
Script 5: ✓ VALID (words: 125, structure: True)

Total valid scripts: 5/5

🎉 All scripts passed validation!
```

## Troubleshooting

### No Scripts Extracted

**Problem**: Parser returns empty list

**Solutions**:
1. Check `source_content` is not empty
2. Verify HuggingFace API key is set: `HUGGINGFACE_API_KEY`
3. Ensure content is at least 500 words
4. Check LLM response in logs for errors

### Invalid Word Counts

**Problem**: Scripts are too short or too long

**Solutions**:
1. Adjust `target_count` in parser (default: 5 scripts)
2. Provide longer source content for more extraction options
3. LLM may need better prompting - check `_build_extraction_prompt()`

### Missing Structure

**Problem**: Scripts missing `[HOOK]`, `[BRIDGE]`, or `[CORE SCRIPT]` markers

**Solutions**:
1. Check LLM is following prompt instructions
2. Verify prompt template in `_build_extraction_prompt()`
3. May need to adjust temperature in HuggingFace LLM config

### JSON Parsing Errors

**Problem**: `Failed to parse JSON response`

**Solutions**:
1. LLM may be returning extra text - check response format
2. Adjust prompt to emphasize "Return ONLY the JSON array"
3. Check for malformed JSON in LLM response logs

## Advanced Usage

### Custom Extraction Count

```python
# Modify in script_parser.py
response = llm.generate(
    prompt_template=prompt,
    input_variables={
        "source_content": source,
        "target_count": 10  # Extract more scripts
    }
)
```

### Custom Length Validation

```python
# In _parse_scripts method
if word_count < 50 or word_count > 200:  # Custom range
    self.logger.warning(f"Script {idx} outside custom range")
```

### Batch Processing Multiple Sources

```python
sources = [
    "Podcast transcript 1...",
    "Podcast transcript 2...",
    "Article content..."
]

all_scripts = []
for source in sources:
    result = parser.run({"source_content": source})
    all_scripts.extend(result["parsed_script_list"])

print(f"Total scripts extracted: {len(all_scripts)}")
```

## Integration with Workflow

### Current State (Manual)

```python
# 1. Extract scripts
parser = ScriptParserAgent()
result = parser.run({"source_content": content})
scripts = result["parsed_script_list"]

# 2. Process each script manually
for script in scripts:
    state = {
        "script": script["script"],
        "broad_topic": script["key_point"],
        # ... run through existing workflow
    }
```

### Future State (Automated - Phase 6)

```python
# Graph will automatically loop through scripts
state = {
    "source_content": "Your podcast transcript...",
}

# Workflow will:
# 1. Parse scripts
# 2. For each script:
#    - Classify intent
#    - Select video
#    - Select audio
#    - Render video
for event in app.stream(state, config):
    print(event)
```

## Tips for Best Results

1. **Quality Content**: Start with well-structured, engaging source material
2. **Clear Topics**: Content with distinct points extracts better than rambling text
3. **Optimal Length**: 1000-3000 word source content yields 3-7 good scripts
4. **Review Hooks**: Manually review and tweak hooks for maximum impact
5. **Test Variations**: Try different source content to see what works best

## Next Steps

After extracting scripts:
1. Review each script for quality
2. Manually adjust hooks if needed
3. Feed into existing workflow for video generation
4. Test with real audience to see what performs best

---

**Related Documentation**:
- [Main README](file:///c:/Users/anshc/anshatwork/YTShortsEnginer/README.md)
- [Walkthrough](file:///C:/Users/anshc/.gemini/antigravity/brain/71d5029c-2e00-4af7-bae3-21b924bddf33/walkthrough.md)
- [Implementation Plan](file:///C:/Users/anshc/.gemini/antigravity/brain/71d5029c-2e00-4af7-bae3-21b924bddf33/implementation_plan.md)
