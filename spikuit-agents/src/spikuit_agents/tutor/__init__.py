"""Spikuit agents — tutor grading backends.

Concrete ``LLMGrader`` implementations. The cli package defines the
``LLMGrader`` Protocol in ``spikuit_cli.quiz.grader``; this module
satisfies it with LLM-backed strategies. Dependency flow stays
``core ← cli ← agents``.
"""

from __future__ import annotations

from .agent_grader import AgentLLMGrader, GradeFn, build_grade_prompt

__all__ = ["AgentLLMGrader", "GradeFn", "build_grade_prompt"]
