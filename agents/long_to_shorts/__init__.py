"""
agents/long_to_shorts
~~~~~~~~~~~~~~~~~~~~~
Long-form video → multiple 9:16 YouTube Shorts clipping pipeline.

Exposes:
    long_to_shorts_app  – compiled LangGraph StateGraph ready to .invoke()
"""

from agents.long_to_shorts.graph import long_to_shorts_app  # noqa: F401

__all__ = ["long_to_shorts_app"]
