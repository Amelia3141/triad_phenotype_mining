"""
Correction memory for iterative extraction improvement.

Two-layer system:
1. Session corrections: accumulated during a pipeline run, injected
   into subsequent article prompts within the same run.
2. Persistent corrections: saved to disk as JSON, loaded at the start
   of every future run.

Each correction is categorised by subtask (temporal, family_history,
treatment) so it's only injected into the relevant LLM prompt.

Over time, if the corrections file grows large (>80 entries per
subtask), older corrections with low recurrence counts are pruned
and the remaining ones are summarised into higher-level rules.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional


class Correction:
    """A single extraction correction."""

    __slots__ = (
        "id", "subtask", "pattern", "error_description",
        "fix_instruction", "example_wrong", "example_right",
        "pmcid", "field", "timestamp", "recurrence_count",
    )

    def __init__(
        self,
        subtask: str,
        pattern: str,
        error_description: str,
        fix_instruction: str,
        example_wrong: Any = None,
        example_right: Any = None,
        pmcid: str = "",
        field: str = "",
        correction_id: str = "",
        timestamp: float = 0,
        recurrence_count: int = 1,
    ):
        self.id = correction_id or f"{subtask}_{int(time.time())}_{id(self) % 10000}"
        self.subtask = subtask          # "temporal", "family_history", "treatment", "general"
        self.pattern = pattern           # short slug, e.g. "possessive_family_reference"
        self.error_description = error_description  # what went wrong
        self.fix_instruction = fix_instruction      # what to do instead
        self.example_wrong = example_wrong
        self.example_right = example_right
        self.pmcid = pmcid
        self.field = field
        self.timestamp = timestamp or time.time()
        self.recurrence_count = recurrence_count

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subtask": self.subtask,
            "pattern": self.pattern,
            "error_description": self.error_description,
            "fix_instruction": self.fix_instruction,
            "example_wrong": self.example_wrong,
            "example_right": self.example_right,
            "pmcid": self.pmcid,
            "field": self.field,
            "timestamp": self.timestamp,
            "recurrence_count": self.recurrence_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Correction":
        return cls(
            subtask=d["subtask"],
            pattern=d["pattern"],
            error_description=d["error_description"],
            fix_instruction=d["fix_instruction"],
            example_wrong=d.get("example_wrong"),
            example_right=d.get("example_right"),
            pmcid=d.get("pmcid", ""),
            field=d.get("field", ""),
            correction_id=d.get("id", ""),
            timestamp=d.get("timestamp", 0),
            recurrence_count=d.get("recurrence_count", 1),
        )

    def to_prompt_line(self) -> str:
        """Format this correction as a line for LLM prompt injection."""
        line = f"- KNOWN PITFALL [{self.pattern}]: {self.error_description}. "
        line += f"FIX: {self.fix_instruction}"
        if self.example_wrong is not None and self.example_right is not None:
            line += f' (e.g. wrong: {json.dumps(self.example_wrong)}, correct: {json.dumps(self.example_right)})'
        return line


class CorrectionMemory:
    """Manages session and persistent corrections.

    Args:
        persistent_path: path to the JSON file for cross-run corrections.
            If None, only session-level corrections are used.
        max_per_subtask: max corrections injected per subtask prompt.
            Beyond this, oldest low-recurrence ones are dropped from
            injection (not from the file).
    """

    SUBTASKS = ("temporal", "family_history", "treatment", "general")

    def __init__(
        self,
        persistent_path: Optional[str] = None,
        max_per_subtask: int = 30,
    ):
        self.persistent_path = persistent_path
        self.max_per_subtask = max_per_subtask

        # Persistent corrections loaded from disk
        self._persistent: List[Correction] = []
        # Session corrections accumulated during this run
        self._session: List[Correction] = []

        if persistent_path and os.path.exists(persistent_path):
            self._load()

    def _load(self):
        """Load corrections from the persistent JSON file."""
        try:
            with open(self.persistent_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._persistent = [Correction.from_dict(d) for d in data.get("corrections", [])]
        except (json.JSONDecodeError, KeyError, TypeError):
            self._persistent = []

    def save(self):
        """Save all corrections (persistent + session) to disk.

        Session corrections are promoted to persistent on save.
        Duplicate patterns are merged (recurrence count incremented).
        """
        if not self.persistent_path:
            return

        # Merge session into persistent
        all_corrections = list(self._persistent)
        existing_patterns = {(c.subtask, c.pattern) for c in all_corrections}

        for sc in self._session:
            key = (sc.subtask, sc.pattern)
            if key in existing_patterns:
                # Increment recurrence count on existing
                for pc in all_corrections:
                    if (pc.subtask, pc.pattern) == key:
                        pc.recurrence_count += 1
                        # Update example if the new one is better (has both wrong + right)
                        if sc.example_wrong is not None and sc.example_right is not None:
                            pc.example_wrong = sc.example_wrong
                            pc.example_right = sc.example_right
                        break
            else:
                all_corrections.append(sc)
                existing_patterns.add(key)

        self._persistent = all_corrections
        self._session = []

        data = {
            "version": 1,
            "saved_at": time.time(),
            "correction_count": len(all_corrections),
            "corrections": [c.to_dict() for c in all_corrections],
        }

        os.makedirs(os.path.dirname(self.persistent_path) or ".", exist_ok=True)
        with open(self.persistent_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add(self, correction: Correction, session_only: bool = False):
        """Add a correction.

        Args:
            correction: the Correction object.
            session_only: if True, only used for the current run
                (not saved to disk). Default False.
        """
        if session_only:
            self._session.append(correction)
        else:
            # Check for duplicate pattern
            for existing in self._persistent:
                if existing.subtask == correction.subtask and existing.pattern == correction.pattern:
                    existing.recurrence_count += 1
                    if correction.example_wrong is not None:
                        existing.example_wrong = correction.example_wrong
                        existing.example_right = correction.example_right
                    return
            self._persistent.append(correction)

    def add_from_review(
        self,
        subtask: str,
        pattern: str,
        error_description: str,
        fix_instruction: str,
        pmcid: str = "",
        field: str = "",
        example_wrong: Any = None,
        example_right: Any = None,
    ) -> Correction:
        """Convenience method to create and add a correction from a review."""
        c = Correction(
            subtask=subtask,
            pattern=pattern,
            error_description=error_description,
            fix_instruction=fix_instruction,
            example_wrong=example_wrong,
            example_right=example_right,
            pmcid=pmcid,
            field=field,
        )
        self.add(c)
        return c

    def get_for_subtask(self, subtask: str) -> List[Correction]:
        """Get all corrections relevant to a subtask.

        Returns persistent + session corrections for the given subtask,
        plus any "general" corrections. Sorted by recurrence count
        (most common errors first). Capped at max_per_subtask.
        """
        relevant = []
        for c in self._persistent + self._session:
            if c.subtask == subtask or c.subtask == "general":
                relevant.append(c)

        # Sort: highest recurrence first, then most recent
        relevant.sort(key=lambda c: (-c.recurrence_count, -c.timestamp))
        return relevant[:self.max_per_subtask]

    def format_for_prompt(self, subtask: str) -> str:
        """Format corrections for injection into an LLM prompt.

        Returns empty string if no corrections exist for this subtask.
        """
        corrections = self.get_for_subtask(subtask)
        if not corrections:
            return ""

        lines = [
            "",
            "IMPORTANT - Known extraction pitfalls (learn from previous errors):",
        ]
        for c in corrections:
            lines.append(c.to_prompt_line())
        lines.append("")
        return "\n".join(lines)

    def get_all(self) -> List[dict]:
        """Return all corrections as dicts (for API responses)."""
        all_c = self._persistent + self._session
        return [c.to_dict() for c in all_c]

    def get_stats(self) -> dict:
        """Return summary statistics."""
        all_c = self._persistent + self._session
        by_subtask = {}
        for c in all_c:
            by_subtask[c.subtask] = by_subtask.get(c.subtask, 0) + 1

        return {
            "total": len(all_c),
            "persistent": len(self._persistent),
            "session": len(self._session),
            "by_subtask": by_subtask,
            "top_patterns": [
                {"pattern": c.pattern, "subtask": c.subtask, "recurrence": c.recurrence_count}
                for c in sorted(all_c, key=lambda x: -x.recurrence_count)[:10]
            ],
        }

    def remove(self, correction_id: str) -> bool:
        """Remove a correction by ID."""
        for lst in [self._persistent, self._session]:
            for i, c in enumerate(lst):
                if c.id == correction_id:
                    lst.pop(i)
                    return True
        return False
