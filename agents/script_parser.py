"""
Script Parser Agent
Extracts multiple short-form scripts from long-form content.
Rewords existing content for viral short format with optimized hooks.
"""

from typing import Dict, Any, List
import json
import re
from agents.base import BaseAgent
from agents.state import ShortsState
from tools.llm.huggingface import HuggingFaceLLM


class ScriptParserAgent(BaseAgent):
    """
    Agent responsible for extracting multiple shorts from long-form content.
    
    Features:
    - Extract N distinct 30-60s segments
    - Reword for short format (don't generate new content)
    - Optimize hooks (first 3 seconds)
    - Validate length (75-150 words ≈ 30-60s)
    - Return list of scripts for batch processing
    """
    
    def run(self, state: ShortsState) -> Dict[str, Any]:
        """
        Parse source_content into multiple short scripts.
        Returns list of scripts to batch process.
        
        Args:
            state: Current workflow state
            
        Returns:
            Dict with parsed_script_list and updated current_step
        """
        source = state.get("source_content")
        if not source:
            self.logger.warning("No source_content provided, skipping parser")
            return {"current_step": "parser_skipped"}
        
        try:
            self.logger.info(f"Parsing source content ({len(source)} chars)")
            
            llm = HuggingFaceLLM()
            prompt = self._build_extraction_prompt()
            
            # Extract ~5 scripts by default
            target_count = 1
            
            response = llm.generate(
                prompt_template=prompt,
                input_variables={
                    "source_content": source,
                    "target_count": target_count
                }
            )
            
            # Parse and validate scripts
            scripts = self._parse_scripts(response)
            
            self.logger.info(
                f"Successfully extracted {len(scripts)} scripts from source content"
            )
            
            return {
                "parsed_script_list": scripts,  # Temporary list for batch loop
                "current_step": "scripts_parsed"
            }
            
        except Exception as e:
            self.logger.error(f"Script parsing failed: {str(e)}")
            raise Exception(f"Failed to parse scripts: {str(e)}")
    
    def _build_extraction_prompt(self) -> str:
        """Build prompt for extracting shorts from long-form content."""
        return """You are a viral YouTube Shorts content extractor. Extract a single short-form script from this long-form content:

{source_content}

CRITICAL RULES:
1. Each script must be 30-60 seconds when spoken (~150-300 words)
2. REWORD and ADAPT existing content - DO NOT generate new content
3. Each must have a STRONG HOOK (first 3 seconds, ~5-10 words)
4. Include [HOOK]/[BRIDGE]/[CORE SCRIPT] structure for each
5. Make each script standalone (can be understood without context)
6. Extract the most viral-worthy, engaging segments
7. Optimize hooks for maximum retention (use curiosity, fear, identity, or contradiction)

Output format (JSON array):
[
  {{
    "script": "Full script text with [HOOK]\\n...hook text...\\n[BRIDGE]\\n...bridge text...\\n[CORE SCRIPT]\\n...core text...",
    "hook": "Just the hook portion (optimized for first 3s)",
    "word_count": 120,
    "key_point": "Brief note on what this segment covers"
  }},
  ...
]

IMPORTANT: Return ONLY the JSON array, no other text."""
    
    def _parse_scripts(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse and validate extracted scripts from LLM response.
        
        Args:
            response: LLM response containing JSON array of scripts
            
        Returns:
            List of validated script dictionaries
        """
        try:
            # Clean the response first
            response = response.strip()
            print(response)
            # Try to extract JSON array from response
            json_match = re.search(r'\[[\s\S]*\]', response)
            if not json_match:
                self.logger.error(f"No JSON array found in response. Response preview: {response[:500]}")
                raise ValueError("No JSON array found in response")
            
            json_str = json_match.group(0)
            
            # Clean common JSON issues
            # Replace literal \n in strings with actual newlines
            json_str = json_str.replace('\\\\n', '\\n')
            
            # Try to parse JSON
            try:
                scripts_raw = json.loads(json_str)
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON decode error: {e}")
                self.logger.error(f"Problematic JSON: {json_str[:1000]}")
                
                # Try to fix common issues
                # Remove trailing commas before closing brackets
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                
                # Try parsing again
                try:
                    scripts_raw = json.loads(json_str)
                    self.logger.info("Successfully parsed JSON after cleanup")
                except json.JSONDecodeError:
                    # Last resort: try to extract manually
                    self.logger.warning("JSON parsing failed, attempting manual extraction")
                    return self._manual_parse_scripts(response)
            
            if not isinstance(scripts_raw, list):
                raise ValueError("Response is not a JSON array")
            
            validated_scripts = []
            
            for idx, script_data in enumerate(scripts_raw):
                # Validate required fields
                if not isinstance(script_data, dict):
                    self.logger.warning(f"Script {idx} is not a dict, skipping")
                    continue
                
                script_text = script_data.get("script", "")
                hook = script_data.get("hook", "")
                word_count = script_data.get("word_count", 0)
                key_point = script_data.get("key_point", "")
                
                # Validate word count (30-60s = 75-150 words)
                if word_count < 75 or word_count > 150:
                    self.logger.warning(
                        f"Script {idx} has {word_count} words (target: 75-150), "
                        f"may be too short or too long"
                    )
                
                # Validate structure
                has_hook = '[HOOK]' in script_text
                has_bridge = '[BRIDGE]' in script_text
                has_core = '[CORE SCRIPT]' in script_text
                
                if not (has_hook and has_bridge and has_core):
                    self.logger.warning(
                        f"Script {idx} missing structure markers | "
                        f"Hook: {has_hook} | Bridge: {has_bridge} | Core: {has_core}"
                    )
                
                # Add to validated list
                validated_scripts.append({
                    "script": script_text,
                    "hook": hook,
                    "word_count": word_count,
                    "key_point": key_point,
                    "index": idx
                })
            
            if not validated_scripts:
                raise ValueError("No valid scripts extracted")
            
            return validated_scripts
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            raise ValueError(f"Invalid JSON in LLM response: {e}")
        except Exception as e:
            self.logger.error(f"Script parsing error: {e}")
            raise
    
    def _manual_parse_scripts(self, response: str) -> List[Dict[str, Any]]:
        """
        Manually parse scripts if JSON parsing fails.
        Fallback method for malformed JSON.
        
        Args:
            response: Raw LLM response
            
        Returns:
            List of script dictionaries
        """
        self.logger.info("Attempting manual script extraction")
        
        # Look for script patterns
        scripts = []
        
        # Try to find [HOOK] sections
        hook_pattern = r'\[HOOK\](.*?)\[BRIDGE\](.*?)\[CORE SCRIPT\](.*?)(?=\[HOOK\]|$)'
        matches = re.findall(hook_pattern, response, re.DOTALL)
        
        for idx, (hook, bridge, core) in enumerate(matches):
            script_text = f"[HOOK]{hook}[BRIDGE]{bridge}[CORE SCRIPT]{core}"
            word_count = len(script_text.split())
            
            scripts.append({
                "script": script_text.strip(),
                "hook": hook.strip(),
                "word_count": word_count,
                "key_point": f"Manually extracted segment {idx + 1}",
                "index": idx
            })
        
        if scripts:
            self.logger.info(f"Manually extracted {len(scripts)} scripts")
            return scripts
        
        # If still nothing, create a single script from the entire response
        self.logger.warning("Could not extract structured scripts, returning raw response as single script")
        return [{
            "script": response[:500],  # Truncate to reasonable length
            "hook": "Manual extraction",
            "word_count": len(response.split()),
            "key_point": "Full content (manual extraction)",
            "index": 0
        }]
