"""Spikuit Core — FSRS + Knowledge Graph + Spreading Activation engine."""

__version__ = "0.0.1"

from .circuit import Circuit
from .config import BrainConfig, find_spikuit_root, init_brain, load_config
from .embedder import Embedder, NullEmbedder, OllamaEmbedder, OpenAICompatEmbedder, create_embedder
from .models import (
    Grade,
    Neuron,
    Plasticity,
    QuizItem,
    QuizItemRole,
    QuizRequest,
    QuizResult,
    Scaffold,
    ScaffoldLevel,
    Spike,
    Synapse,
    SynapseType,
)
from .learn import AutoQuiz, Flashcard, Learn
from .scaffold import compute_scaffold
from .session import LearnSession, QABotSession, Session
from .tutor import TutorSession, TutorState

__all__ = [
    "AutoQuiz",
    "Circuit",
    "Grade",
    "Neuron",
    "Plasticity",
    "QuizItem",
    "QuizItemRole",
    "QuizRequest",
    "QuizResult",
    "Scaffold",
    "ScaffoldLevel",
    "Spike",
    "Synapse",
    "SynapseType",
    "TutorSession",
    "TutorState",
    "compute_scaffold",
    "Embedder",
    "Flashcard",
    "Learn",
    "LearnSession",
    "NullEmbedder",
    "OllamaEmbedder",
    "OpenAICompatEmbedder",
    "QABotSession",
    "Session",
]
