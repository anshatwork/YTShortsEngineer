"""
Quick test to verify script cleaning handles escaped newlines correctly
"""
import re

def clean_script_for_tts(script: str) -> str:
    """Clean script for TTS - remove markers and normalize whitespace."""
    # Remove all structure markers (including trailing whitespace/newlines)
    cleaned = re.sub(r'\[HOOK\]\s*\n?', '', script)
    cleaned = re.sub(r'\[BRIDGE\]\s*\n?', '', cleaned)
    cleaned = re.sub(r'\[CORE SCRIPT\]\s*\n?', '', cleaned)
    
    # Normalize whitespace:
    # 1. First, preserve paragraph breaks by protecting double newlines
    cleaned = re.sub(r'\n\s*\n', '<<PARAGRAPH>>', cleaned)
    
    # 2. Convert single newlines to spaces (for natural TTS flow)
    cleaned = re.sub(r'\n', ' ', cleaned)
    
    # 3. Restore paragraph breaks as double newlines
    cleaned = cleaned.replace('<<PARAGRAPH>>', '\n\n')
    
    # 4. Clean up multiple spaces
    cleaned = re.sub(r' +', ' ', cleaned)
    
    # 5. Final trim
    cleaned = cleaned.strip()
    
    return cleaned


# Test 1: String with escaped newlines (as it appears in your output)
print("=" * 80)
print("TEST 1: String with escaped newlines (\\n as text)")
print("=" * 80)

escaped_script = "[HOOK]\\nUranium in 2026 is repeating Silver's 2025 playbook.\\n[BRIDGE]\\nWe saw Silver break a 13-year resistance and gain over 120% in a single year. Now, Uranium is following that exact same script.\\n[CORE SCRIPT]\\nJust like Silver faced a massive supply deficit from solar and EV demand, Uranium is..."

print("\nINPUT (repr):")
print(repr(escaped_script))
print("\nINPUT (readable):")
print(escaped_script)

# This won't work because \n is literal text, not a newline character
cleaned_escaped = clean_script_for_tts(escaped_script)
print("\nOUTPUT (repr):")
print(repr(cleaned_escaped))
print("\nOUTPUT (readable):")
print(cleaned_escaped)

# Test 2: Proper string with actual newlines
print("\n" + "=" * 80)
print("TEST 2: String with actual newlines (correct format)")
print("=" * 80)

proper_script = """[HOOK]
Uranium in 2026 is repeating Silver's 2025 playbook.
[BRIDGE]
We saw Silver break a 13-year resistance and gain over 120% in a single year. Now, Uranium is following that exact same script.
[CORE SCRIPT]
Just like Silver faced a massive supply deficit from solar and EV demand, Uranium is hitting a critical wall in 2026."""

print("\nINPUT (repr):")
print(repr(proper_script[:150]))
print("\nINPUT (readable):")
print(proper_script)

cleaned_proper = clean_script_for_tts(proper_script)
print("\nOUTPUT (repr):")
print(repr(cleaned_proper[:150]))
print("\nOUTPUT (readable):")
print(cleaned_proper)

# Test 3: Convert escaped newlines to actual newlines
print("\n" + "=" * 80)
print("TEST 3: Converting escaped newlines to actual newlines")
print("=" * 80)

# If your script has literal \n characters, convert them first
fixed_script = escaped_script.replace('\\n', '\n')
print("\nAFTER CONVERSION (repr):")
print(repr(fixed_script[:150]))

cleaned_fixed = clean_script_for_tts(fixed_script)
print("\nOUTPUT (repr):")
print(repr(cleaned_fixed[:150]))
print("\nOUTPUT (readable):")
print(cleaned_fixed)

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("✓ Escaped newlines (\\\\n as text) won't be cleaned properly")
print("✓ Actual newlines work correctly with the cleaning function")
print("✓ If your script has escaped newlines, use .replace('\\\\n', '\\n') first")
