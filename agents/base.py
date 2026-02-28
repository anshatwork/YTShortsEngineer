from abc import ABC, abstractmethod
from typing import Dict, Any
from workflows.state import ShortsState
import logging

class BaseAgent(ABC):
    """
    Abstract Base Class for Workflow Agents.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
    @abstractmethod
    def run(self, state: ShortsState) -> Dict[str, Any]:
        """
        Execute the agent's logic.
        
        Args:
            state: The current workflow state.
            
        Returns:
            Dict containing state updates.
        """
        pass
