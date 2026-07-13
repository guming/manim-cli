from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TeachingSequenceItem(StrictBaseModel):
    id: str
    goal: str
    method: Optional[str] = None


class SymbolLedgerItem(StrictBaseModel):
    symbol: str
    meaning: str
    canonical_tex: Optional[str] = None
    color_role: Optional[str] = None
    unit: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    scope: str = "global"
    symbol_type: Optional[str] = None
    domain: Optional[str] = None
    shape: Optional[str] = None


class NarrationCue(StrictBaseModel):
    id: str
    text: str
    duration_seconds: Optional[float] = None


class TeachingPlan(StrictBaseModel):
    id: str
    topic: str
    audience_level: str
    duration_seconds: int
    learning_goals: List[str]
    teaching_sequence: List[TeachingSequenceItem]
    symbol_ledger: List[SymbolLedgerItem] = Field(default_factory=list)
    narration_cues: List[NarrationCue] = Field(default_factory=list)


class VisualEvent(StrictBaseModel):
    id: str
    intent: str
    focus: List[str] = Field(default_factory=list)
    duration_seconds: Optional[float] = None


class StoryboardFrame(StrictBaseModel):
    id: str
    section: Optional[str] = None
    duration_seconds: Optional[float] = None
    narration_cue_ids: List[str] = Field(default_factory=list)
    visual_events: List[VisualEvent] = Field(default_factory=list)
    layout_constraints: Dict[str, Any] = Field(default_factory=dict)
    input_goal: Optional[str] = None
    visual_elements: List[str] = Field(default_factory=list)
    animation_logic: Optional[str] = None
    state_transitions: List[str] = Field(default_factory=list)
    camera_behavior: Optional[str] = None
    mathematical_derivation: List[str] = Field(default_factory=list)


class Storyboard(StrictBaseModel):
    id: str
    plan_id: str
    frames: List[StoryboardFrame]
