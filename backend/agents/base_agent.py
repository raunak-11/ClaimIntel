from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Run the agent and return a result dict."""
        ...
