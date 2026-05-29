from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class TriageLLM(ABC):
    @abstractmethod
    def analyze(
        self,
        role: str,
        system: str,
        prompt: str,
        max_tokens: int = 2048,
        content_hint: Optional[str] = None,
    ) -> LLMResponse: ...
