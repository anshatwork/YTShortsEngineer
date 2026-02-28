"""
Test script for deterministic workflow validation.
Verifies that the upgraded system produces deterministic, intent-first results.
"""

import os
import sys
from dotenv import load_dotenv
from workflows.state import ShortsState
from agents.script_generation import ScriptGenerationAgent
from agents.video_selection import VideoSelectionAgent
from core.logger import setup_logger

# Load environment variables
load_dotenv()

# Setup logging
logger = setup_logger(__name__)


def test_determinism_workflow(topic: str, num_runs: int = 3):
    """
    Test the deterministic workflow by running the same topic multiple times.
    Validates:
    - Hook styles are from valid enum
    - Visual intents are from valid enum
    - Video queries are deterministic (from INTENT_QUERY_MAP)
    - Topic text doesn't appear in video search
    """
    print("=" * 70)
    print(f"DETERMINISM TEST: {topic}")
    print(f"Running {num_runs} iterations...")
    print("=" * 70)
    
    results = []
    
    for i in range(num_runs):
        print(f"\n{'='*70}")
        print(f"RUN {i+1}/{num_runs}")
        print('='*70)
        
        # Initialize state
        state: ShortsState = {
            "broad_topic": topic,
            "search_queries": [],
            "video_candidates": [],
            "selected_video": None,
            "audio_mode": "voiceover",
            "video_mode": "fetched_video",
            "background_video_path": None,
            "script": None,
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
            "current_step": "initialized",
            "final_video_path": None
        }
        
        try:
            # Step 1: Script Generation
            print("\n[STEP 1] Generating script with hook and intent...")
            script_agent = ScriptGenerationAgent()
            script_result = script_agent.run(state)
            state.update(script_result)
            
            print(f"✓ Hook Style: {state['hook_style']} (validated: {state['hook_style_validated']})")
            print(f"✓ Visual Intent: {state['visual_intent']} (validated: {state['visual_intent_validated']})")
            print(f"✓ Script Preview: {state['script'][:150]}...")
            
            # Step 2: Video Selection
            print("\n[STEP 2] Selecting video via tiered fetching...")
            video_agent = VideoSelectionAgent()
            video_result = video_agent.run(state)
            state.update(video_result)
            
            print(f"✓ Video Source: {state['video_source']}")
            print(f"✓ Selection Tier: {state['video_selection_tier']}")
            print(f"✓ Query Used: {state['video_query_used'] or 'N/A'}")
            print(f"✓ Selected Video: {state['selected_video']['title']}")
            
            # Collect results
            results.append({
                "run": i + 1,
                "hook_style": state["hook_style"],
                "hook_validated": state["hook_style_validated"],
                "visual_intent": state["visual_intent"],
                "intent_validated": state["visual_intent_validated"],
                "video_source": state["video_source"],
                "video_tier": state["video_selection_tier"],
                "video_query": state["video_query_used"],
                "script_length": len(state["script"])
            })
            
        except Exception as e:
            print(f"\n✗ RUN {i+1} FAILED: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append({
                "run": i + 1,
                "error": str(e)
            })
    
    # Analysis
    print("\n" + "=" * 70)
    print("DETERMINISM ANALYSIS")
    print("=" * 70)
    
    successful_runs = [r for r in results if "error" not in r]
    failed_runs = [r for r in results if "error" in r]
    
    print(f"\nSuccessful Runs: {len(successful_runs)}/{num_runs}")
    print(f"Failed Runs: {len(failed_runs)}/{num_runs}")
    
    if successful_runs:
        print("\n--- Validation Success Rate ---")
        hook_validated = sum(1 for r in successful_runs if r["hook_validated"]) / len(successful_runs) * 100
        intent_validated = sum(1 for r in successful_runs if r["intent_validated"]) / len(successful_runs) * 100
        print(f"Hook Style Validation: {hook_validated:.1f}%")
        print(f"Visual Intent Validation: {intent_validated:.1f}%")
        
        print("\n--- Video Source Distribution ---")
        sources = {}
        for r in successful_runs:
            source = r["video_source"]
            sources[source] = sources.get(source, 0) + 1
        
        for source, count in sources.items():
            percentage = count / len(successful_runs) * 100
            print(f"{source}: {count}/{len(successful_runs)} ({percentage:.1f}%)")
        
        print("\n--- Tier Distribution ---")
        tiers = {}
        for r in successful_runs:
            tier = r["video_tier"]
            tiers[tier] = tiers.get(tier, 0) + 1
        
        for tier, count in sorted(tiers.items()):
            percentage = count / len(successful_runs) * 100
            print(f"Tier {tier}: {count}/{len(successful_runs)} ({percentage:.1f}%)")
        
        print("\n--- Topic Isolation Check ---")
        topic_in_query = 0
        for r in successful_runs:
            query = r.get("video_query")
            if query and topic.lower() in query.lower():
                topic_in_query += 1
                print(f"⚠ WARNING: Topic found in query: '{query}'")
        
        if topic_in_query == 0:
            print("✓ PASS: Topic text not found in any video queries")
        else:
            print(f"✗ FAIL: Topic text found in {topic_in_query} queries")
        
        print("\n--- Determinism Score ---")
        # Check if queries are from deterministic set (Tiers 1-3)
        deterministic_runs = sum(1 for r in successful_runs if r["video_tier"] in [1, 2, 3])
        determinism_score = deterministic_runs / len(successful_runs) * 100
        print(f"Deterministic Selections (Tiers 1-3): {determinism_score:.1f}%")
        
        if determinism_score >= 90:
            print("✓ EXCELLENT: System is highly deterministic")
        elif determinism_score >= 70:
            print("⚠ GOOD: System is mostly deterministic")
        else:
            print("✗ POOR: System relies too heavily on LLM fallback")
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    # Test with a sample topic
    test_topic = "Was roman reigns winning the 2026 royal rumble a good decision?"
    
    if len(sys.argv) > 1:
        test_topic = " ".join(sys.argv[1:])
    
    test_determinism_workflow(test_topic, num_runs=3)
