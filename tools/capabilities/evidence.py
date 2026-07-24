"""
Evidence — collection, storage, and redaction of verification evidence.

Evidence is stored as raw data with sensitive fields redacted before
serialization. Only redacted references are stored in traces.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .models import EvidenceReference


# Fields that are always redacted (never stored in evidence references)
SENSITIVE_FIELDS = frozenset({
    "phone", "phone_number", "sms_body", "message_body",
    "password", "token", "secret", "api_key", "auth",
    "email", "address", "location_coords", "gps",
    "contact_name", "contact_number", "recipient",
    "credit_card", "ssn", "pin",
})


@dataclass
class EvidenceEntry:
    """A single evidence entry with raw data and safe summary."""
    observer_type: str
    raw_data: dict[str, Any]
    safe_summary: str
    timestamp: float = field(default_factory=time.time)
    evidence_id: str = field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:12]}")


@dataclass
class RedactedEvidence:
    """Evidence with sensitive fields removed."""
    evidence_id: str
    observer_type: str
    raw_data: dict[str, Any]
    safe_summary: str
    timestamp: float


class EvidenceCollector:
    """Collects and manages evidence entries with automatic redaction."""

    def __init__(self):
        self.entries: list[EvidenceEntry] = []

    def add(self, entry: EvidenceEntry) -> None:
        """Add an evidence entry."""
        self.entries.append(entry)

    def _redact_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive fields from data."""
        return {
            k: v for k, v in data.items()
            if k.lower() not in SENSITIVE_FIELDS
        }

    def get_redacted(self) -> list[RedactedEvidence]:
        """Return all entries with sensitive fields redacted."""
        result = []
        for entry in self.entries:
            result.append(RedactedEvidence(
                evidence_id=entry.evidence_id,
                observer_type=entry.observer_type,
                raw_data=self._redact_data(entry.raw_data),
                safe_summary=entry.safe_summary,
                timestamp=entry.timestamp,
            ))
        return result

    def to_references(self) -> list[EvidenceReference]:
        """Convert entries to EvidenceReference objects for trace storage."""
        refs = []
        for entry in self.entries:
            refs.append(EvidenceReference(
                evidence_id=entry.evidence_id,
                observer_type=entry.observer_type,
                timestamp=entry.timestamp,
                safe_summary=entry.safe_summary,
            ))
        return refs

    def clear(self) -> None:
        """Clear all collected evidence."""
        self.entries.clear()

    def count(self) -> int:
        return len(self.entries)
