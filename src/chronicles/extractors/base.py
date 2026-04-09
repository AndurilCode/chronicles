"""Base extractor abstract class."""
from __future__ import annotations

from abc import ABC, abstractmethod

from chronicles.config import LLMConfig
from chronicles.models import CleanedTranscript, ExtractionResult


class BaseExtractor(ABC):
    """Abstract base class for all LLM extractors."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    @abstractmethod
    def extract(self, transcript: CleanedTranscript) -> ExtractionResult:
        """Extract structured information from a cleaned transcript."""
