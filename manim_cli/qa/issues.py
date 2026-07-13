from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


Severity = Literal["info", "warning", "error"]
RepairScope = Literal["single_action", "visual_action", "narration_cue", "cross_track_alignment", "artifact_reference", "scene"]


@dataclass(frozen=True)
class IssueLocation:
    file: Optional[str] = None
    dsl_path: Optional[str] = None
    step_id: Optional[str] = None
    step_index: Optional[int] = None
    action_index: Optional[int] = None
    object_ids: List[str] = field(default_factory=list)
    narration_cue_id: Optional[str] = None
    storyboard_event_id: Optional[str] = None
    storyboard_frame_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if value not in (None, [], {}):
                data[key] = value
        return data


@dataclass(frozen=True)
class RepairHint:
    message: str
    repair_scope: RepairScope = "scene"
    dsl_path: Optional[str] = None
    target: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"message": self.message, "repair_scope": self.repair_scope}
        if self.dsl_path:
            data["dsl_path"] = self.dsl_path
        if self.target:
            data["target"] = self.target
        return data


@dataclass(frozen=True)
class Issue:
    type: str
    severity: Severity
    message: str
    location: IssueLocation = field(default_factory=IssueLocation)
    repair_scope: RepairScope = "scene"
    repair_hints: List[RepairHint] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    confidence: str = "medium"
    source: str = "qa"

    def to_dict(self) -> Dict[str, Any]:
        fingerprint = issue_fingerprint(self.type, self.location, self.details)
        issue_id = f"qa-{fingerprint[:12]}"
        data: Dict[str, Any] = {
            "issue_id": issue_id,
            "fingerprint": fingerprint,
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "location": self.location.to_dict(),
            "repair_scope": self.repair_scope,
            "confidence": self.confidence,
            "source": self.source,
        }
        if self.repair_hints:
            data["repair_hints"] = [hint.to_dict() for hint in self.repair_hints]
        if self.details:
            data["details"] = self.details
        return data


def issue_fingerprint(issue_type: str, location: IssueLocation, details: Dict[str, Any]) -> str:
    stable_details = {
        key: value
        for key, value in details.items()
        if key in {"symbol", "object", "objects", "step", "step_id", "frame_id", "storyboard_event_id", "bbox_confidence"}
    }
    payload = {
        "type": issue_type,
        "dsl_path": location.dsl_path,
        "step_id": location.step_id,
        "step_index": location.step_index,
        "action_index": location.action_index,
        "object_ids": sorted(location.object_ids),
        "narration_cue_id": location.narration_cue_id,
        "storyboard_event_id": location.storyboard_event_id,
        "storyboard_frame_id": location.storyboard_frame_id,
        "details": stable_details,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
