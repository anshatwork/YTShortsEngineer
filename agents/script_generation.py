from typing import Dict, Any

from pydantic import BaseModel

from agents.base import BaseAgent
from workflows.state import ShortsState
from tools.llm import get_llm
from core.visual_intents import HookStyle, VisualIntent


class Script(BaseModel):
    """Structured-output schema for a generated narration script.

    The enum-typed fields make hook-style / visual-intent validation automatic —
    the model can only emit a valid value — replacing the old regex + validate_*
    parsing path.
    """

    visual_intent: VisualIntent
    hook_style: HookStyle
    hook: str
    bridge: str
    core_script: str


# Static instructions are passed as the cached `system` prompt; the topic / source
# excerpt (the only varying part) goes in the user turn.
_GENERATE_SYSTEM = """\
You are a viral YouTube Shorts scriptwriter. Write a compelling 15-20 second narration
script (50-60 words max) for the topic the user provides, in three parts:
- hook: a 0-2s attention-grabbing opener.
- bridge: connects the hook to the main point.
- core_script: the main value/story, conversational and energetic.

Also choose:
- hook_style — the style of the hook: curiosity (weird fact or question),
  fear ("Stop doing this..." / "This is why you're failing..."),
  identity ("If you are X, you need to hear this..."),
  contradiction ("Everything you know about X is wrong.").
- visual_intent — based on the script's TONE and PACING (not the topic):
  tension (dark, suspenseful), calm (peaceful, soothing), fast (energetic, rapid-fire),
  serious (professional, factual), reflective (thoughtful), aspirational (motivational,
  uplifting), neutral_explainer (balanced, informative), financial (business/data-driven)."""

_EXTRACT_SYSTEM = """\
You are adapting existing content into a viral YouTube Short script. From the source
excerpt the user provides, reword the material into a punchy 30-60s short (~150-300
words) that keeps the core message, in three parts:
- hook: a 0-2s attention-grabbing opener.
- bridge: connects the hook to the main point.
- core_script: the main content, adapted from the source.

Also choose:
- hook_style: curiosity, fear, identity, or contradiction.
- visual_intent — based on the EMOTIONAL TONE and PACING (not the topic):
  tension, calm, fast, serious, reflective, aspirational, neutral_explainer, financial."""


class ScriptGenerationAgent(BaseAgent):
    """
    Agent responsible for generating the narration script with:
    - Hook style selection from a fixed enum (enforced by structured output)
    - Visual intent selection from a fixed enum (enforced by structured output)
    - [HOOK]/[BRIDGE]/[CORE SCRIPT] structure (assembled from discrete fields)
    """

    def run(self, state: ShortsState) -> Dict[str, Any]:
        try:
            source_content = state.get("source_content")
            mode = "extract" if source_content else "generate"

            self.logger.info(f"Running script generation in '{mode}' mode")

            llm = get_llm()

            if mode == "extract":
                system = _EXTRACT_SYSTEM
                user = f"Source content excerpt:\n\"\"\"\n{source_content[:1500]}\n\"\"\""
            else:
                system = _GENERATE_SYSTEM
                user = f"Topic: {state['broad_topic']}"

            parsed: Script = llm.parse(user, Script, system=system)

            # Assemble the marked script for downstream consumers (script_parser,
            # voice_synthesis) that expect [HOOK]/[BRIDGE]/[CORE SCRIPT] structure.
            script = (
                f"[HOOK]\n{parsed.hook.strip()}\n"
                f"[BRIDGE]\n{parsed.bridge.strip()}\n"
                f"[CORE SCRIPT]\n{parsed.core_script.strip()}"
            )

            self.logger.info(
                f"Generated script ({len(script)} chars) | "
                f"Hook: {parsed.hook_style.value} | Intent: {parsed.visual_intent.value}"
            )

            return {
                "script": script,
                "hook_style": parsed.hook_style.value,
                "visual_intent": parsed.visual_intent.value,
                "hook_style_validated": True,
                "visual_intent_validated": True,
                "current_step": "script_generated",
            }

        except Exception as e:
            self.logger.error(f"Script generation failed: {str(e)}")
            raise Exception(f"Failed to generate script: {str(e)}")
