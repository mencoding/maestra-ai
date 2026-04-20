"""Tipos do wizard `maestra init`."""
from __future__ import annotations

from typing import Literal, TypedDict

InitState = Literal["A", "A2", "B", "C"]


class InitReport(TypedDict):
    """Resultado de uma execução de init."""

    state_before: InitState
    action: Literal[
        "start_from_scratch",
        "resume_oauth",
        "initial_analysis",
        "update_recent_mood",
        "update_full",
        "reset_partial",
        "reset_full",
        "exit",
    ]
    playlist_id: str | None
    taste_profile_updated: bool
    rationale_path: str | None
    signals: dict | None
    suggestions: list[str]
    warnings: list[str]
