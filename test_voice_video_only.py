"""
Simplified Test: Voice Synthesis + Video Assembly Only
Tests voiceover generation and video assembly with a pre-written script.
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
load_dotenv()

from agents.voice_synthesis import VoiceSynthesisAgent
from agents.video_assembly import VideoAssemblyAgent
from workflows.state import ShortsState

# Pre-written script (properly formatted with actual newlines, not escaped)
URANIUM_SCRIPT = """[HOOK]
Uranium in 2026 is repeating Silver's 2025 playbook.

[BRIDGE]
We saw Silver break a 13-year resistance and gain over 120% in a single year. Now, Uranium is following that exact same script.

[CORE SCRIPT]
Just like Silver faced a massive supply deficit from solar and EV demand, Uranium is hitting a critical wall in 2026. With major producers like Kazatomprom and Cameco struggling to meet targets, the shortage narrative has shifted from theory to a full-blown price squeeze.

The AI and data center catalyst is massive. Tech giants are signing direct nuclear power contracts, effectively locking up future supply. The Global X Uranium ETF has been soaring, reaching highs above 60 dollars earlier this year.

But here's the warning: Silver in 2025 had that vertical price action, gaining 120% before a flash crash. Uranium in 2026 is now in price discovery mode, but these parabolic moves often end in sharp corrections when profit-booking hits."""


def test_voice_and_video():
    """Test voice synthesis and video assembly with pre-written script."""
    print("=" * 80)
    print("VOICE SYNTHESIS + VIDEO ASSEMBLY TEST")
    print("=" * 80)
    
    # Initialize state with pre-written script
    state: ShortsState = {
        "broad_topic": "Uranium_Silver",
        "source_content": "",
        "search_queries": [],
        "video_candidates": [],
        "selected_video": None,
        "overlay_style": "background_only",
        "background_video_path": "assets\\op_bg1.mp4",
        "script": URANIUM_SCRIPT,  # Pre-written script
        "script_prompt": None,
        "hook_style": None,
        "visual_intent": None,
        "hook_style_validated": None,
        "visual_intent_validated": None,
        "voiceover_audio_path": None,
        "voiceover_url": None,
        "word_timestamps": None,
        "downloaded_video_path": None,
        "video_source": None,
        "video_query_used": None,
        "video_selection_tier": None,
        "review_status": "pending",
        "review_notes": None,
        "current_step": "initial",
        "final_video_path": None,
        "audio_mode": "voiceover",
        "video_mode": "bg_video"
    }
    
    print("\n" + "=" * 80)
    print("SCRIPT PREVIEW")
    print("=" * 80)
    print(state["script"])
    print()
    
    # ========================================================================
    # STEP 1: VOICE SYNTHESIS
    # ========================================================================
    print("=" * 80)
    print("STEP 1: VOICE SYNTHESIS")
    print("=" * 80)
    
    try:
        voice_agent = VoiceSynthesisAgent()
        voice_result = voice_agent.run(state)
        
        state.update(voice_result)
        voiceover_path = state.get("voiceover_audio_path")
        
        if voiceover_path:
            print(f"✓ Voiceover generated: {voiceover_path}")
            
            # Check if file exists
            if Path(voiceover_path).exists():
                file_size = Path(voiceover_path).stat().st_size / 1024  # KB
                print(f"  File size: {file_size:.2f} KB")
            else:
                print(f"  ⚠ Warning: File not found at path")
        else:
            print(f"✗ Voiceover generation failed")
            return False
            
    except Exception as e:
        print(f"✗ Voice synthesis failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # ========================================================================
    # STEP 2: VIDEO ASSEMBLY
    # ========================================================================
    print("\n" + "=" * 80)
    print("STEP 2: VIDEO ASSEMBLY")
    print("=" * 80)
    
    try:
        # Verify background video exists
        bg_path = Path(state["background_video_path"])
        if not bg_path.exists():
            print(f"✗ Background video not found: {state['background_video_path']}")
            print(f"  Please ensure the background video exists at this path")
            return False
        
        print(f"✓ Background video found: {state['background_video_path']}")
        print(f"  Overlay style: {state['overlay_style']}")
        print(f"  Voiceover: {state['voiceover_audio_path']}")
        
        assembly_agent = VideoAssemblyAgent()
        assembly_result = assembly_agent.run(state)
        
        state.update(assembly_result)
        final_video = state.get("final_video_path")
        
        if final_video:
            print(f"\n✓ Video assembled: {final_video}")
            
            if Path(final_video).exists():
                file_size = Path(final_video).stat().st_size / (1024 * 1024)  # MB
                print(f"  File size: {file_size:.2f} MB")
            else:
                print(f"  ⚠ Warning: File not found at path")
        else:
            print(f"✗ Video assembly failed")
            return False
            
    except Exception as e:
        print(f"✗ Video assembly failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # ========================================================================
    # SUCCESS SUMMARY
    # ========================================================================
    print("\n" + "=" * 80)
    print("🎉 TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print(f"\n✓ Voiceover: {state['voiceover_audio_path']}")
    print(f"✓ Final Video: {state['final_video_path']}")
    print(f"✓ Background: {state['background_video_path']}")
    print(f"✓ Overlay Style: {state['overlay_style']}")
    
    return True


if __name__ == "__main__":
    success = test_voice_and_video()
    sys.exit(0 if success else 1)
