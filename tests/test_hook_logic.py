
import unittest
from unittest.mock import MagicMock, patch
from agents.script_generation import ScriptGenerationAgent
from agents.video_selection import VideoSelectionAgent
from workflows.state import ShortsState

class TestHookAndSelection(unittest.TestCase):
    
    @patch('agents.script_generation.HuggingFaceLLM')
    def test_script_generation_hook_and_intent(self, MockLLM):
        # Mock LLM Response
        mock_instance = MockLLM.return_value
        mock_instance.generate.return_value = """[HOOK]
Did you know this?
[BRIDGE]
This is crazy.
[CORE SCRIPT]
Here is the core content.

VISUAL_INTENT: Tension"""
        
        agent = ScriptGenerationAgent()
        state = {"broad_topic": "Test Topic", "video_candidates": []}
        
        result = agent.run(state)
        
        # Verify Hook Style Selection
        self.assertIn("hook_style", result)
        self.assertIn(result["hook_style"], ["curiosity", "fear", "identity", "contradiction"])
        
        # Verify Intent Extraction
        self.assertEqual(result["visual_intent"], "tension")
        self.assertIn("VISUAL_INTENT", mock_instance.generate.call_args[1]["prompt_template"])

    def test_video_selection_logic(self):
        agent = VideoSelectionAgent()
        
        # Mock Candidates
        candidates = [
            {"title": "Calm Relaxing Nature", "description": "Peaceful forest", "video_id": "1"},
            {"title": "Fast High Energy Explainer", "description": "Quick cuts", "video_id": "2"},
            {"title": "Scary Horror Clip", "description": "Tension building", "video_id": "3"}
        ]
        
        # Test 1: Calm Intent -> Should pick Calm/Nature (deprioritize fast/scary?)
        # My simple heuristic penalizes "Fast" for Calm intent.
        state_calm = {
            "video_candidates": candidates,
            "visual_intent": "calm"
        }
        res_calm = agent.run(state_calm)
        # Note: My current simple logic just avoids negative words. 
        # "Fast" has avoid list: [slow, calm...] -> "Calm" video has "calm" in title, so score -1 for Fast intent?
        # Let's trace logic:
        # Intent: Calm. Avoid: [fast, chaos...]
        # Vid 1: "Calm..." -> No penalty. Bonus if "calm" in title? Yes (+1). Score: 1.
        # Vid 2: "Fast..." -> Penalty "fast" in title. Score: -1.
        # Result: Vid 1.
        self.assertEqual(res_calm["selected_video"]["video_id"], "1")
        
        # Test 2: Fast Intent -> Should pick Fast
        # Intent: Fast. Avoid: [slow, calm...]
        # Vid 1: "Calm..." -> Penalty. Score -1.
        # Vid 2: "Fast..." -> Bonus "fast"? (If I added it). 
        # Actually my logic only has "Avoid" map in the plan, but I added "Boost" in code: `if intent in text_block: score += 1`
        state_fast = {
            "video_candidates": candidates,
            "visual_intent": "fast"
        }
        res_fast = agent.run(state_fast)
        self.assertEqual(res_fast["selected_video"]["video_id"], "2")

if __name__ == '__main__':
    unittest.main()
