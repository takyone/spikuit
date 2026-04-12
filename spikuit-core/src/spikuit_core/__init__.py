"""Spikuit Core — FSRS + Knowledge Graph + Spreading Activation engine.

Two install profiles:

    pip install spikuit-core           # minimal: QABot client only
    pip install spikuit-core[engine]   # full: Circuit engine + Sessions

The minimal install ships embedder + QABot (read-only retrieval over
exported Brain bundles) with only `httpx` and `numpy` as dependencies.
The `[engine]` extras pull `fsrs`, `networkx`, `aiosqlite`, `sqlite-vec`,
and `msgspec` for the live Brain engine.

Engine symbols (`Circuit`, `Neuron`, etc.) are loaded lazily via PEP 562
`__getattr__`. Importing them without the `[engine]` extras raises a
helpful `ImportError` pointing at the install command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.5.3"

# -- Always available (lightweight) ---------------------------------------

from .config import BrainConfig, EmbedderConfig, find_spikuit_root
from .embedder import (
    Embedder,
    EmbeddingType,
    NullEmbedder,
    OllamaEmbedder,
    OpenAICompatEmbedder,
    create_embedder,
)
from .rag import EmbedderConfigError, EmbedderSpec, QABot, RetrievalHit

# -- Engine symbols (lazy) ------------------------------------------------

# (export name) -> (submodule, attribute)
_ENGINE_SYMBOLS: dict[str, tuple[str, str]] = {
    # circuit
    "Circuit": ("circuit", "Circuit"),
    "ReadOnlyError": ("circuit", "ReadOnlyError"),
    # config helpers that touch the engine
    "init_brain": ("config", "init_brain"),
    "load_config": ("config", "load_config"),
    # models
    "ExamResult": ("models", "ExamResult"),
    "Grade": ("models", "Grade"),
    "Neuron": ("models", "Neuron"),
    "Plasticity": ("models", "Plasticity"),
    "QuizItem": ("models", "QuizItem"),
    "QuizItemRole": ("models", "QuizItemRole"),
    "QuizRequest": ("models", "QuizRequest"),
    "QuizResult": ("models", "QuizResult"),
    "Scaffold": ("models", "Scaffold"),
    "ScaffoldLevel": ("models", "ScaffoldLevel"),
    "Source": ("models", "Source"),
    "Spike": ("models", "Spike"),
    "Synapse": ("models", "Synapse"),
    "SynapseConfidence": ("models", "SynapseConfidence"),
    "SynapseType": ("models", "SynapseType"),
    "TutorAction": ("models", "TutorAction"),
    "strip_frontmatter": ("models", "strip_frontmatter"),
    # learn
    "AutoQuiz": ("learn", "AutoQuiz"),
    "Flashcard": ("learn", "Flashcard"),
    "Learn": ("learn", "Learn"),
    # scaffold
    "compute_scaffold": ("scaffold", "compute_scaffold"),
    # session
    "LearnSession": ("session", "LearnSession"),
    "QABotSession": ("session", "QABotSession"),
    "Session": ("session", "Session"),
    # tutor
    "TutorSession": ("tutor", "TutorSession"),
    "TutorState": ("tutor", "TutorState"),
}


def __getattr__(name: str) -> Any:
    if name in _ENGINE_SYMBOLS:
        from importlib import import_module

        module_name, attr_name = _ENGINE_SYMBOLS[name]
        try:
            mod = import_module(f".{module_name}", __name__)
        except ImportError as e:
            raise ImportError(
                f"spikuit_core.{name} requires the engine extras.\n"
                f"  Install with: pip install spikuit-core[engine]\n"
                f"  (missing module: {e.name})"
            ) from e
        value = getattr(mod, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'spikuit_core' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_ENGINE_SYMBOLS))


# Static type checkers and IDEs see these names; runtime gets them via __getattr__.
if TYPE_CHECKING:
    from .circuit import Circuit, ReadOnlyError
    from .config import init_brain, load_config
    from .learn import AutoQuiz, Flashcard, Learn
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
    from .scaffold import compute_scaffold
    from .session import LearnSession, QABotSession, Session
    from .tutor import TutorSession, TutorState


__all__ = [
    # Always available
    "BrainConfig",
    "Embedder",
    "EmbedderConfig",
    "EmbedderConfigError",
    "EmbedderSpec",
    "EmbeddingType",
    "NullEmbedder",
    "OllamaEmbedder",
    "OpenAICompatEmbedder",
    "QABot",
    "RetrievalHit",
    "create_embedder",
    "find_spikuit_root",
    # Engine (lazy)
    *sorted(_ENGINE_SYMBOLS.keys()),
]
