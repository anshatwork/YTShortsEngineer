from abc import ABC, abstractmethod
from typing import Optional

class BaseLLMProvider(ABC):
    """
    Abstract Base Class for LLM Providers.
    """
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text from a prompt.
        """
        pass
