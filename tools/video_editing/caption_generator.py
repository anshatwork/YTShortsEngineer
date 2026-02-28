from moviepy import TextClip
from typing import List, Dict, Any

# Ensure we deal with API changes in MoviePy 2.x - assuming 2.x as per code I saw earlier
# In MoviePy 2.0.2 TextClip is imported directly usually, but check imports from original file.
# Original file: from moviepy import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip, ColorClip

def create_caption_clips(
    timestamps: List[Dict[str, Any]],
    video_duration: float,
) -> List[TextClip]:
    """
    Create animated caption clips from timestamps.
    """
    try:
        clips: List[TextClip] = []

        for ts in timestamps:
            word = ts.get("word")
            if not word:
                continue

            start = float(ts["start"])
            end = min(float(ts["end"]), video_duration)
            duration = max(end - start, 0.01)

            emphasis = len(word) > 6 or word.isupper()

            # Note: Font path is hardcoded for Windows in original. 
            # Ideally config, but let's keep it working for now.
            font = r"C:\Windows\Fonts\impact.ttf"
            
            # MoviePy 2.x TextClip initialization might vary slightly, using what was in editor_engine
            clip = TextClip(
                text=word.upper(),
                font=font,
                font_size=70 if emphasis else 60,
                color="yellow" if emphasis else "white",
                stroke_color="black",
                stroke_width=3,
                method="caption",
                text_align="center",
                size=(900, None),
            )

            clip = (
                clip
                .with_position("center")
                .with_start(start)
                .with_duration(duration)
            )

            if emphasis:
                # Simple zoom effect simulation or just keeping it static if resize func is complex to port
                # The original used a lambda for resizing.
                clip = clip.resized(
                    lambda t, d=duration: 1 + 0.05 * (1 - abs(t - d / 2) / (d / 2))
                )

            clips.append(clip)

        return clips

    except Exception as e:
        # In a real app, maybe log or raise
        raise RuntimeError(f"Caption creation failed: {e}") from e
