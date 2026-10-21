"""
tools/vision
~~~~~~~~~~~~~
Side-effecting perception adapters for the knowledge-graph ingestion pipeline —
the visual counterpart of ``tools/youtube`` / ``tools/assets``. Imports only from
``core/`` (never graph state or api). Every function degrades rather than failing:

    from tools.vision import detect_scenes, extract_keyframe, ocr_image

    scenes = detect_scenes(video_path)                 # [(start_s, end_s), ...]
    frame  = extract_keyframe(video_path, t_s, dest)   # CAS-cached JPEG path | None
    blocks = ocr_image(frame)                          # [{"text","bbox",...}] | []

Deeper perception (VLM captioning, object detection, diarization) is designed to
arrive later behind its own ``tools/vlm`` provider registry (mirroring
``tools/llm``), without changing this module's contract.
"""

from tools.vision.keyframe import extract_keyframe
from tools.vision.ocr import ocr_available, ocr_image
from tools.vision.scene import detect_scenes, probe_duration

__all__ = [
    "detect_scenes",
    "probe_duration",
    "extract_keyframe",
    "ocr_image",
    "ocr_available",
]
