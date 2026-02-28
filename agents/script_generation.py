from typing import Dict, Any
from agents.base import BaseAgent
from workflows.state import ShortsState
from tools.llm.huggingface import HuggingFaceLLM
from core.visual_intents import HookStyle, VisualIntent, validate_hook_style, validate_visual_intent
import re

class ScriptGenerationAgent(BaseAgent):
    """
    Agent responsible for generating the narration script with:
    - Hook style selection from fixed enum
    - Visual intent selection from fixed enum
    - Enforced [HOOK]/[BRIDGE]/[CORE SCRIPT] structure
    """
    
    def run(self, state: ShortsState) -> Dict[str, Any]:
        try:
            # Detect mode: extract if source_content exists, otherwise generate
            source_content = state.get("source_content")
            mode = "extract" if source_content else "generate"
            
            self.logger.info(f"Running script generation in '{mode}' mode")
            
            llm = HuggingFaceLLM()
            
            # Build the deterministic prompt
            template = self._build_prompt_template(mode=mode)
            
            # Prepare input variables based on mode
            if mode == "extract":
                input_vars = {
                    "source_excerpt": source_content[:1500],  # Limit to avoid token overflow
                    "hook_styles": ", ".join(HookStyle.list_values()),
                    "visual_intents": ", ".join(VisualIntent.list_values())
                }
            else:
                input_vars = {
                    "topic": state["broad_topic"],
                    "hook_styles": ", ".join(HookStyle.list_values()),
                    "visual_intents": ", ".join(VisualIntent.list_values())
                }
            
            response = llm.generate(
                prompt_template=template,
                input_variables=input_vars
            )
            
            # Parse and validate the response
            parsed = self._parse_response(response)
            
            self.logger.info(
                f"Generated script ({len(parsed['script'])} chars) | "
                f"Hook: {parsed['hook_style']} (valid: {parsed['hook_validated']}) | "
                f"Intent: {parsed['visual_intent']} (valid: {parsed['intent_validated']})"
            )
            
            return {
                "script": parsed["script"],
                "hook_style": parsed["hook_style"],
                "visual_intent": parsed["visual_intent"],
                "hook_style_validated": parsed["hook_validated"],
                "visual_intent_validated": parsed["intent_validated"],
                "current_step": "script_generated"
            }
            
        except Exception as e:
            self.logger.error(f"Script generation failed: {str(e)}")
            raise Exception(f"Failed to generate script: {str(e)}")
    
    def _build_prompt_template(self, mode: str = "generate") -> str:
        """
        Build the deterministic prompt template.
        
        Args:
            mode: "generate" (from topic) or "extract" (from source content)
        """
        if mode == "extract":
            # NEW MODE: Extract/reword from source content
            return """You are adapting existing content into a viral YouTube Short script.

Source content excerpt:
{source_excerpt}

ADAPTATION RULES:
1. REWORD this content for 30-60s short format (~150-300 words)
2. Keep the core message but make it punchy and viral
3. Add structure: [HOOK]/[BRIDGE]/[CORE SCRIPT]
4. Select hook style from: {hook_styles}
5. Select visual intent based on TONE (not topic): {visual_intents}

CRITICAL: Visual intent should match the EMOTIONAL TONE and PACING:
- tension: Dark, suspenseful, ominous tone
- calm: Peaceful, relaxing, soothing tone
- fast: Energetic, rapid-fire, exciting tone
- serious: Professional, authoritative, factual tone
- reflective: Thoughtful, contemplative, introspective tone
- aspirational: Motivational, uplifting, inspiring tone
- neutral: Generic, balanced, informative tone

OUTPUT FORMAT:
VISUAL_INTENT: [your choice from the list]
HOOK_STYLE: [your choice from the list]

[HOOK]
(0-2s attention grabber)
[BRIDGE]
(Connect hook to main point)
[CORE SCRIPT]
(Main content, adapted from source)

Return ONLY the format above, no extra text."""
        
        else:
            # EXISTING MODE: Generate from scratch
            return """You are a viral YouTube Shorts scriptwriter. Create a compelling 
15-20 second narration script for a short video about: {topic}

CRITICAL RULES:
1. The script MUST follow this EXACT structure:
   [HOOK]
   (A 0-2s hook - attention grabbing opening)
   [BRIDGE]
   (Connects the hook to the main topic)
   [CORE SCRIPT]
   (The main value/story, conversational and energetic)

2. Hook Style Selection:
   You MUST choose ONE hook style from: {hook_styles}
   
   Style Guide:
   - curiosity: Start with a weird fact or questions
   - fear: "Stop doing this..." or "This is why you're failing..."
   - identity: "If you are X, you need to hear this..."
   - contradiction: "Everything you know about X is wrong."

3. VISUAL INTENT SELECTION:
   Based on the TONE and PACING of your script (NOT the topic), choose ONE from: {visual_intents}
   
   Intent Guide:
   - tension: Dark, suspenseful, ominous (e.g., horror, mystery, crime)
   - calm: Peaceful, relaxing, soothing (e.g., nature, meditation)
   - fast: Energetic, rapid-fire, exciting (e.g., action, sports, hype)
   - serious: Professional, authoritative, factual (e.g., news, business)
   - reflective: Thoughtful, contemplative, introspective (e.g., philosophy, life lessons)
   - aspirational: Motivational, uplifting, inspiring (e.g., success stories, goals)
   - neutral: Generic, balanced, informative (e.g., tutorials, explanations)

4. Total script length: 50-60 words MAX (15-20 seconds when spoken)

OUTPUT FORMAT:
VISUAL_INTENT: [your choice from the list]
HOOK_STYLE: [your choice from the list]

[HOOK]
(Your hook text here)
[BRIDGE]
(Your bridge text here)
[CORE SCRIPT]
(Your core script text here)

Return ONLY the format above, no extra text."""
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parse and validate LLM response.
        Extracts script, hook_style, and visual_intent.
        """
        response = response.strip()
        
        # Extract visual intent
        visual_intent = "calm"  # default fallback
        intent_validated = False
        intent_match = re.search(r'VISUAL_INTENT:\s*(\w+)', response, re.IGNORECASE)
        if intent_match:
            intent_str = intent_match.group(1).strip()
            is_valid, validated_intent = validate_visual_intent(intent_str)
            if is_valid and validated_intent:
                visual_intent = validated_intent.value
                intent_validated = True
            else:
                self.logger.warning(f"Invalid visual intent '{intent_str}', using default 'calm'")
        
        # Extract hook style
        hook_style = "curiosity"  # default fallback
        hook_validated = False
        hook_match = re.search(r'HOOK_STYLE:\s*(\w+)', response, re.IGNORECASE)
        if hook_match:
            hook_str = hook_match.group(1).strip()
            is_valid, validated_hook = validate_hook_style(hook_str)
            if is_valid and validated_hook:
                hook_style = validated_hook.value
                hook_validated = True
            else:
                self.logger.warning(f"Invalid hook style '{hook_str}', using default 'curiosity'")
        
        # Extract script content (remove metadata lines)
        script_content = response
        script_content = re.sub(r'VISUAL_INTENT:.*', '', script_content, flags=re.IGNORECASE)
        script_content = re.sub(r'HOOK_STYLE:.*', '', script_content, flags=re.IGNORECASE)
        script_content = script_content.strip()
        
        # Validate structure
        has_hook = '[HOOK]' in script_content
        has_bridge = '[BRIDGE]' in script_content
        has_core = '[CORE SCRIPT]' in script_content
        
        if not (has_hook and has_bridge and has_core):
            self.logger.warning(
                f"Script structure incomplete | "
                f"Hook: {has_hook} | Bridge: {has_bridge} | Core: {has_core}"
            )
        
        return {
            "script": script_content,
            "hook_style": hook_style,
            "visual_intent": visual_intent,
            "hook_validated": hook_validated,
            "intent_validated": intent_validated
        }

