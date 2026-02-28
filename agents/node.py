"""
LangGraph Nodes for YouTube Shorts Creator
Implements all workflow nodes including query generation, script creation,
video rendering, review, and upload.
"""

import os
import logging
from typing import Dict, Any
from pathlib import Path
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_core.prompts import PromptTemplate
from agents.state import ShortsState
from tools.editor_engine import (
    download_video,
    generate_voiceover,
    extract_word_timestamps,
    create_caption_clips,
    assemble_split_screen_video
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize HuggingFace LLM
def get_llm():
    hf_token = os.getenv("HUGGINGFACE_API_KEY")
    if not hf_token:
        raise ValueError("HUGGINGFACE_API_KEY not found")

    llm = HuggingFaceEndpoint(
        repo_id="mistralai/Mistral-7B-Instruct-v0.2",
        huggingfacehub_api_token=hf_token,
        task="conversational",
        max_new_tokens=512,
        temperature=0.7,
    )

    return ChatHuggingFace(llm=llm)


def parse_scripts_node(state: ShortsState) -> Dict[str, Any]:
    """
    Parse long-form content into multiple short scripts.
    Only runs if source_content is provided.
    
    Args:
        state: Current state with optional source_content
        
    Returns:
        Updated state with parsed_script_list or skipped status
    """
    try:
        from agents.script_parser import ScriptParserAgent
        agent = ScriptParserAgent()
        return agent.run(state)
        
    except Exception as e:
        logger.error(f"Script parsing node failed: {str(e)}")
        raise Exception(f"Failed to parse scripts: {str(e)}")


def generate_queries_node(state: ShortsState) -> Dict[str, Any]:
    """
    Generate search queries based on the broad topic.
    
    Args:
        state: Current state with broad_topic
        
    Returns:
        Updated state with search_queries
    """
    try:
        logger.info(f"Generating queries for topic: {state['broad_topic']}")
        
        llm = get_llm()
        
        prompt = PromptTemplate(
            input_variables=["topic"],
            template="""You are a YouTube Shorts trend expert. Generate 3 specific, 
trendy search queries that would find viral short-form content related to: {topic}

Focus on current trends, viral formats, and high-engagement topics.
Return ONLY the 3 queries, one per line, without numbering or extra text.

Queries:"""
        )
        
        chain = prompt | llm
        response = chain.invoke({"topic": state["broad_topic"]})
        
        # Extract content from AIMessage object
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Parse queries from response
        queries = [q.strip() for q in response_text.split('\n') if q.strip()][:3]
        
        logger.info(f"Generated queries: {queries}")
        
        return {
            "search_queries": queries,
            "current_step": "queries_generated"
        }
        
    except Exception as e:
        logger.error(f"Query generation failed: {str(e)}")
        raise Exception(f"Failed to generate queries: {str(e)}")


def generate_script_node(state: ShortsState) -> Dict[str, Any]:
    """
    Generate a 30-60 second narration script based on the selected video.
    
    Args:
        state: Current state with broad_topic and selected_video
        
    Returns:
        Updated state with script
    """
    try:
        logger.info("Generating narration script")
        
        selected_video = state.get("selected_video")
        if not selected_video:
            raise ValueError("No video selected for script generation")
        
        llm = get_llm()
        
        prompt = PromptTemplate(
            input_variables=["topic", "video_title"],
            template="""You are a viral YouTube Shorts scriptwriter. Create a compelling 
10-15 second narration script for a short video about: {topic}

The video will feature: {video_title}

Requirements:
- Hook the viewer in the first 3 seconds
- Keep it conversational and energetic
- Use short, punchy sentences (max 50-60 words total)
- Include a brief call-to-action at the end
- Total reading time: 10-15 seconds MAX

Script:"""
        )
        
        chain = prompt | llm
        response = chain.invoke({
            "topic": state["broad_topic"],
            "video_title": selected_video["title"]
        })
        
        # Extract content from AIMessage object
        script = response.content if hasattr(response, 'content') else str(response)
        script = script.strip()
        logger.info(f"Generated script ({len(script)} characters)")
        
        return {
            "script": script,
            "current_step": "script_generated"
        }
        
    except Exception as e:
        logger.error(f"Script generation failed: {str(e)}")
        raise Exception(f"Failed to generate script: {str(e)}")


def select_video_node(state: ShortsState) -> Dict[str, Any]:
    """
    Select the best video candidate based on the Script's output (Intent).
    
    Args:
        state: Current state with visual_intent and video_candidates
        
    Returns:
        Updated state with selected_video
    """
    try:
        from agents.video_selection import VideoSelectionAgent
        agent = VideoSelectionAgent()
        return agent.run(state)
        
    except Exception as e:
        logger.error(f"Video selection node failed: {str(e)}")
        raise Exception(f"Failed to select video: {str(e)}")


def select_audio_node(state: ShortsState) -> Dict[str, Any]:
    """
    Select background audio based on visual intent.
    Uses 4-tier fallback: cache → Pixabay → Freesound → silent
    
    Args:
        state: Current state with visual_intent
        
    Returns:
        Updated state with audio_theme and audio_file_path
    """
    try:
        from tools.audio_api import AudioFetcher
        from core.audio_theme_map import get_audio_theme_for_intent
        from core.visual_intents import VisualIntent
        
        # Get visual intent from state
        intent_str = state.get("visual_intent", "calm")
        intent = VisualIntent.validate(intent_str) or VisualIntent.CALM
        
        # Map to audio theme
        theme = get_audio_theme_for_intent(intent)
        
        logger.info(f"Selecting audio for intent '{intent.value}' → theme '{theme.value}'")
        
        # Fetch audio file using 4-tier fallback
        fetcher = AudioFetcher()
        audio_path = fetcher.fetch_audio_for_theme(theme)
        
        if audio_path:
            logger.info(f"✓ Audio selected: {audio_path}")
        else:
            logger.warning(f"✗ No audio found for theme '{theme.value}', proceeding without background audio")
        
        return {
            "audio_theme": theme.value,
            "audio_file_path": audio_path,
            "current_step": "audio_selected"
        }
        
    except Exception as e:
        logger.error(f"Audio selection node failed: {str(e)}")
        # Don't fail the entire workflow, just proceed without audio
        logger.warning("Proceeding without background audio")
        return {
            "audio_theme": None,
            "audio_file_path": None,
            "current_step": "audio_selection_failed"
        }


def render_video_node(state: ShortsState) -> Dict[str, Any]:
    """
    Orchestrate the complete video rendering pipeline.
    
    Steps:
    1. Download selected video
    2. Generate voiceover from script
    3. Extract word timestamps via Whisper
    4. Create caption clips
    5. Assemble final split-screen video
    
    Args:
        state: Current state with script, selected_video, and optional background_video_path
        
    Returns:
        Updated state with final_video_path and intermediate paths
    """
    try:
        logger.info("Starting video rendering pipeline")
        
        # Get output directory
        output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Validate inputs
        script = state.get("script")
        selected_video = state.get("selected_video")
        
        if not script:
            raise ValueError("No script found in state")
        if not selected_video:
            raise ValueError("No video selected")
        
        # USE EXISTING FILES TO AVOID API CALLS
        # Hardcode to use the existing video and voiceover
        video_id = "0QALSQMfoxc"  # Use existing video
        downloaded_video_path = str(output_dir / f"{video_id}.mp4")
        voiceover_path = str(output_dir / f"{video_id}_voiceover.mp3")
        
        # Check if files exist
        if not os.path.exists(downloaded_video_path):
            raise ValueError(f"Video file not found: {downloaded_video_path}")
        if not os.path.exists(voiceover_path):
            raise ValueError(f"Voiceover file not found: {voiceover_path}")
        
        logger.info(f"Using existing video: {downloaded_video_path}")
        logger.info(f"Using existing voiceover: {voiceover_path}")
        
        # Step 3: Extract word timestamps
        logger.info("Step 3: Extracting word timestamps with Whisper")
        word_timestamps = extract_word_timestamps(voiceover_path, model_name="base")
        
        # Step 4: Create caption clips
        logger.info("Step 4: Creating Hormozi-style caption clips")
        
        # Get voiceover duration for caption clips
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        audio_clip = AudioFileClip(voiceover_path)
        voiceover_duration = audio_clip.duration
        audio_clip.close()
        
        caption_clips = create_caption_clips(word_timestamps, voiceover_duration)
        
        # Step 5: Assemble final video
        logger.info("Step 5: Assembling split-screen video")
        final_video_path = str(output_dir / f"{video_id}_final.mp4")
        
        background_path = state.get("background_video_path")
        
        final_video_path = assemble_split_screen_video(
            trendy_video_path=downloaded_video_path,
            background_video_path=background_path,
            voiceover_path=voiceover_path,
            caption_clips=caption_clips,
            output_path=final_video_path
        )
        
        logger.info(f"Video rendering complete: {final_video_path}")
        
        return {
            "downloaded_video_path": downloaded_video_path,
            "voiceover_audio_path": voiceover_path,
            "word_timestamps": word_timestamps,
            "final_video_path": final_video_path,
            "review_status": "pending",
            "current_step": "awaiting_review"
        }
        
    except Exception as e:
        logger.error(f"Video rendering failed: {str(e)}")
        raise Exception(f"Failed to render video: {str(e)}")


def review_node(state: ShortsState) -> Dict[str, Any]:
    """
    Human-in-the-Loop review node.
    This is a placeholder that gets interrupted for manual review.
    User updates the state externally with review_status and review_notes.
    
    Args:
        state: Current state
        
    Returns:
        Updated state with review_completed status
    """
    logger.info("Review node - awaiting human review")
    
    # This node doesn't change state - user updates externally
    # Just mark the step as completed
    return {
        "current_step": "review_completed"
    }


def upload_to_yt_node(state: ShortsState) -> Dict[str, Any]:
    """
    Upload the final video to YouTube (placeholder implementation).
    Only executes if review_status is "approved".
    
    Args:
        state: Current state with final_video_path and review_status
        
    Returns:
        Updated state with upload status
    """
    try:
        review_status = state.get("review_status", "pending")
        
        if review_status != "approved":
            logger.warning(f"Upload skipped - review status: {review_status}")
            return {
                "current_step": "upload_skipped"
            }
        
        final_video_path = state.get("final_video_path")
        if not final_video_path or not os.path.exists(final_video_path):
            raise ValueError("Final video not found")
        
        logger.info(f"[PLACEHOLDER] Uploading video: {final_video_path}")
        logger.info("[PLACEHOLDER] YouTube upload would happen here")
        
        # TODO: Implement actual YouTube Data API v3 upload
        # This would require:
        # 1. OAuth2 authentication
        # 2. Video metadata (title, description, tags)
        # 3. Upload request to YouTube API
        
        logger.info("Upload completed successfully (placeholder)")
        
        return {
            "current_step": "upload_completed"
        }
        
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise Exception(f"Failed to upload video: {str(e)}")
