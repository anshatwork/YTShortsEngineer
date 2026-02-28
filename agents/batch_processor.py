"""
Batch Processing Wrapper for YouTube Shorts Engine
Handles batch processing of multiple scripts from parsed content.
"""

import logging
from typing import Dict, Any, List
from agents.graph import app
from agents.state import ShortsState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_batch_workflow(
    source_content: str,
    broad_topic: str,
    config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Run batch processing workflow for multiple scripts.
    
    Args:
        source_content: Long-form content to parse
        broad_topic: General topic for the content
        config: LangGraph config with thread_id
        
    Returns:
        List of results for each processed script
    """
    logger.info("Starting batch workflow")
    
    # Initial state with source content
    initial_state: ShortsState = {
        "broad_topic": broad_topic,
        "source_content": source_content,
        "search_queries": [],
        "video_candidates": [],
        "selected_video": None,
        "overlay_style": "split_screen",
        "background_video_path": None,
        "script": None,
        "script_prompt": None,
        "voiceover_audio_path": None,
        "voiceover_url": None,
        "word_timestamps": None,
        "downloaded_video_path": None,
        "review_status": "pending",
        "review_notes": None,
        "current_step": "initial",
        "final_video_path": None,
        "audio_theme": None,
        "audio_file_path": None,
        "batch_index": 0
    }
    
    # Run workflow to parse scripts
    logger.info("Step 1: Parsing scripts from source content")
    parsed_scripts = None
    
    for event in app.stream(initial_state, config):
        logger.info(f"Event: {event}")
        if "parse_scripts" in event:
            parsed_scripts = event["parse_scripts"].get("parsed_script_list")
            break
    
    if not parsed_scripts:
        logger.error("No scripts parsed from source content")
        return []
    
    logger.info(f"Parsed {len(parsed_scripts)} scripts, processing each...")
    
    # Process each script through the workflow
    results = []
    
    for idx, script_data in enumerate(parsed_scripts):
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing script {idx + 1}/{len(parsed_scripts)}")
        logger.info(f"Key point: {script_data.get('key_point')}")
        logger.info(f"{'='*80}\n")
        
        # Create state for this script
        script_state: ShortsState = {
            **initial_state,
            "script": script_data["script"],
            "batch_index": idx,
            "current_step": "script_ready"
        }
        
        # Create unique thread ID for this script
        script_config = {
            "configurable": {
                "thread_id": f"{config['configurable']['thread_id']}_script_{idx}"
            }
        }
        
        try:
            # Run workflow for this script
            final_state = None
            for event in app.stream(script_state, script_config):
                logger.info(f"Script {idx + 1} event: {list(event.keys())}")
                final_state = event
            
            results.append({
                "script_index": idx,
                "script_data": script_data,
                "final_state": final_state,
                "status": "completed"
            })
            
        except Exception as e:
            logger.error(f"Error processing script {idx + 1}: {e}")
            results.append({
                "script_index": idx,
                "script_data": script_data,
                "error": str(e),
                "status": "failed"
            })
    
    logger.info(f"\nBatch processing complete: {len(results)} scripts processed")
    return results


def run_single_workflow(
    broad_topic: str,
    config: Dict[str, Any],
    background_video_path: str = None
) -> Dict[str, Any]:
    """
    Run single script generation workflow (existing behavior).
    
    Args:
        broad_topic: Topic for script generation
        config: LangGraph config with thread_id
        background_video_path: Optional background video path
        
    Returns:
        Final workflow state
    """
    logger.info("Starting single workflow")
    
    initial_state: ShortsState = {
        "broad_topic": broad_topic,
        "source_content": None,  # No source content = generate mode
        "search_queries": [],
        "video_candidates": [],
        "selected_video": None,
        "overlay_style": "split_screen",
        "background_video_path": background_video_path,
        "script": None,
        "script_prompt": None,
        "voiceover_audio_path": None,
        "voiceover_url": None,
        "word_timestamps": None,
        "downloaded_video_path": None,
        "review_status": "pending",
        "review_notes": None,
        "current_step": "initial",
        "final_video_path": None,
        "audio_theme": None,
        "audio_file_path": None,
        "batch_index": 0
    }
    
    final_state = None
    for event in app.stream(initial_state, config):
        logger.info(f"Event: {list(event.keys())}")
        final_state = event
    
    return final_state
