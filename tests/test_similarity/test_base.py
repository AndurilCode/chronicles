"""Tests for similarity engine base class."""
import pytest
from chronicles.similarity.base import BaseSimilarityEngine


def test_cannot_instantiate_base():
    """ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseSimilarityEngine(config=None)
