import os
from typing import Optional
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_core.prompts import PromptTemplate
from tools.llm.base import BaseLLMProvider
from core.config import settings

class HuggingFaceLLM(BaseLLMProvider):
    """
    HuggingFace LLM Provider.
    """
    
    def __init__(self):
        self.api_key = settings.HUGGINGFACE_API_KEY
        self.repo_id = settings.LLM_MODEL_ID
        
        self.llm = HuggingFaceEndpoint(
            repo_id=self.repo_id,
            huggingfacehub_api_token=self.api_key,
            task="conversational",
            max_new_tokens=512,
            temperature=0.7,
        )
        self.chat_model = ChatHuggingFace(llm=self.llm)

    def generate(self, prompt_template: str, input_variables: dict) -> str:
        """
        Generate text using a prompt template and variables.
        """
        prompt = PromptTemplate(
            input_variables=list(input_variables.keys()),
            template=prompt_template
        )
        
        chain = prompt | self.chat_model
        response = chain.invoke(input_variables)

        # Extract content from AIMessage object
        return response.content if hasattr(response, 'content') else str(response)

    def complete(self, prompt: str) -> str:
        """Single-turn completion for the parse() path.

        Invokes the chat model with the raw string directly (no PromptTemplate) so
        a JSON schema containing literal ``{`` / ``}`` doesn't break templating.
        """
        response = self.chat_model.invoke(prompt)
        return response.content if hasattr(response, 'content') else str(response)
