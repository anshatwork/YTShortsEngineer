"""
HITL node

Displays fetched trending videos and waits for user selection.
"""

import logging
from typing import Dict, Any

from agents.state import LongToShortsState

logger = logging.getLogger(__name__)


def hitl_select_video_node(state: LongToShortsState) -> Dict[str, Any]:
    """
    Wait for human selection of video.
    """

    videos = state.get("youtube_results", [])

    if not videos:
        raise RuntimeError("No videos found for HITL selection")

    print("\n" + "=" * 70)
    print("TRENDING VIDEOS FOUND")
    print("=" * 70)

    for i, v in enumerate(videos):
        print(f"\n[{i}] {v['title']}")
        print(f"    Channel : {v['channel']}")
        print(f"    URL     : {v['url']}")
        print(f"    Posted  : {v['published_at']}")

    print("\nSelect video index to process:")

    while True:
        try:
            choice = int(input("Enter number: "))
            if 0 <= choice < len(videos):
                break
        except ValueError:
            pass
        print("Invalid selection. Try again.")

    selected_video = videos[choice]

    print(f"\nSelected: {selected_video['title']}\n")

    return {
        "selected_video_url": selected_video["url"],
        "selected_video_meta": selected_video,
    }