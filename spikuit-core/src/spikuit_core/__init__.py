"""Spikuit Core — FSRS + Knowledge Graph + Spreading Activation engine."""

__version__ = "0.4.0"

from .circuit import Circuit, ReadOnlyError
from .config import BrainConfig, find_spikuit_root, init_brain, load_config
from .embedder import Embedder, EmbeddingType, NullEmbedder, OllamaEmbedder, OpenAICompatEmbedder, create_embedder
from .models import (
    ExamResult,
    Grade,
    Neuron,
    Plasticity,
    QuizItem,
    QuizItemRole,
    QuizRequest,
    QuizResult,
    Scaffold,
    ScaffoldLevel,
    Source,
    Spike,
    Synapse,
    SynapseConfidence,
    SynapseType,
    TutorAction,
    strip_frontmatter,
)
from .learn import AutoQuiz, Flashcard, Learn
from .rag import QABot
from .scaffold import compute_scaffold
from .session import LearnSession, QABotSession, Session
from .tutor import TutorSession, TutorState

__all__ = [
    "AutoQuiz",
    "Circuit",
    "ReadOnlyError",
    "ExamResult",
    "Grade",
    "Neuron",
    "Plasticity",
    "QuizItem",
    "QuizItemRole",
    "QuizRequest",
    "QuizResult",
    "Scaffold",
    "ScaffoldLevel",
    "Source",
    "Spike",
    "Synapse",
    "SynapseConfidence",
    "SynapseType",
    "TutorAction",
    "TutorSession",
    "strip_frontmatter",
    "TutorState",
    "compute_scaffold",
    "Embedder",
    "EmbeddingType",
    "Flashcard",
    "Learn",
    "LearnSession",
    "NullEmbedder",
    "OllamaEmbedder",
    "OpenAICompatEmbedder",
    "QABot",
    "QABotSession",
    "Session",
]
