from typing import Dict, Any
from agents.base import BaseAgent
from workflows.state import ShortsState
from tools.llm.huggingface import HuggingFaceLLM

class TrendDiscoveryAgent(BaseAgent):
    """
    Agent responsible for generating trendy search queries.
    """
    
    def run(self, state: ShortsState) -> Dict[str, Any]:
        try:
            self.logger.info(f"Generating queries for topic: {state['broad_topic']}")
            
            llm = HuggingFaceLLM()
            
            template = """You are a YouTube Shorts trend expert. Generate 3 specific, 
trendy search queries that would find viral short-form content related to: {topic}

Focus on current trends, viral formats, and high-engagement topics.
Return ONLY the 3 queries, one per line, without numbering or extra text.

Queries:"""
            
            response_text = llm.generate(
                prompt_template=template,
                input_variables={"topic": state["broad_topic"]}
            )
            
            # Parse queries from response
            queries = [q.strip() for q in response_text.split('\n') if q.strip()][:3]
            
            self.logger.info(f"Generated queries: {queries}")
            print("Generated Querries " , queries)
            return {
                "search_queries": queries,
                "current_step": "queries_generated"
            }
            
        except Exception as e:
            self.logger.error(f"Query generation failed: {str(e)}")
            raise Exception(f"Failed to generate queries: {str(e)}")
