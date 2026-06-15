"""
Negation detection using the ConText algorithm (Harkema et al. 2009).

Pure Python implementation. No dependencies beyond stdlib.
Detects negated, hypothetical, and historical mentions in clinical text.
"""

import re
from typing import List, Tuple, Set


class NegationDetector:
    """ConText-inspired negation detection for clinical text.

    Given a sentence and a target span, determines whether the target
    is negated, hypothetical, or affirmed.
    """

    def __init__(self, pre_negation: List[str] = None, post_negation: List[str] = None):
        # Default pre-negation triggers (appear BEFORE the negated term)
        self.pre_negation = pre_negation or [
            "no", "no evidence of", "no signs of", "no history of",
            "no significant", "denies", "denied", "denying",
            "negative for", "without", "absence of", "absent",
            "ruled out", "rules out", "ruling out",
            "not consistent with", "not suggestive of",
            "unlikely", "did not have", "does not have",
            "did not show", "does not show",
            "was not", "were not", "is not", "are not",
            "failed to demonstrate", "failed to reveal",
            "no indication of", "not indicative of",
            "unremarkable for", "normal",
            "no evidence to suggest", "never had",
            "no complaint of", "no complaints of",
            "rather than", "instead of",
            "except for", "other than",
            "free of", "void of", "devoid of",
        ]

        # Post-negation triggers (appear AFTER the negated term)
        self.post_negation = post_negation or [
            "was ruled out", "were ruled out",
            "was negative", "were negative",
            "was absent", "were absent",
            "was not found", "were not found",
            "was not detected", "were not detected",
            "was not identified", "were not identified",
            "was excluded", "were excluded",
            "was not present", "were not present",
            "was unremarkable", "were unremarkable",
            "was normal", "were normal",
            "was within normal limits",
        ]

        # Pseudo-negation (looks like negation but isn't)
        self.pseudo_negation = [
            "no change", "no increase", "no decrease",
            "no longer", "not only", "not necessarily",
            "no further", "no additional",
            "without difficulty", "without complication",
            "without incident", "no improvement",  # these are negative outcomes, not negation
        ]

        # Termination terms: negation scope stops here
        self.terminators = [
            "but", "however", "although", "though", "yet",
            "except", "apart from", "aside from",
            "which", "who", "that was", "that were",
            "nevertheless", "nonetheless", "still",
        ]

        # Sort by length descending so longer triggers match first
        self.pre_negation.sort(key=len, reverse=True)
        self.post_negation.sort(key=len, reverse=True)
        self.pseudo_negation.sort(key=len, reverse=True)

        # Compile patterns
        self._pre_patterns = [
            (re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE), t)
            for t in self.pre_negation
        ]
        self._post_patterns = [
            (re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE), t)
            for t in self.post_negation
        ]
        self._pseudo_patterns = [
            re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE)
            for t in self.pseudo_negation
        ]
        self._terminator_patterns = [
            re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE)
            for t in self.terminators
        ]

    def is_negated(self, sentence: str, target_start: int, target_end: int) -> Tuple[bool, str]:
        """Check if a target span in a sentence is negated.

        Args:
            sentence: The full sentence text.
            target_start: Character offset of target start in sentence.
            target_end: Character offset of target end in sentence.

        Returns:
            (is_negated: bool, trigger: str or "" if affirmed)
        """
        sent_lower = sentence.lower()

        # Check pseudo-negation first (these override real negation)
        for pat in self._pseudo_patterns:
            m = pat.search(sent_lower)
            if m and m.start() < target_start and m.end() >= target_start - 3:
                return False, ""

        # Check pre-negation: trigger must appear before target,
        # with no terminator between trigger and target
        for pat, trigger_text in self._pre_patterns:
            for m in pat.finditer(sent_lower):
                if m.end() <= target_start:
                    # Check for terminator between trigger and target
                    between = sent_lower[m.end():target_start]
                    terminated = False
                    for term_pat in self._terminator_patterns:
                        if term_pat.search(between):
                            terminated = True
                            break
                    if not terminated:
                        # Check distance: negation scope is typically within ~30 chars
                        # but some triggers like "no history of" can have wider scope
                        max_dist = 60 if len(trigger_text) > 5 else 30
                        if target_start - m.end() <= max_dist:
                            return True, trigger_text

        # Check post-negation: trigger must appear after target
        for pat, trigger_text in self._post_patterns:
            for m in pat.finditer(sent_lower):
                if m.start() >= target_end:
                    between = sent_lower[target_end:m.start()]
                    terminated = False
                    for term_pat in self._terminator_patterns:
                        if term_pat.search(between):
                            terminated = True
                            break
                    if not terminated and m.start() - target_end <= 40:
                        return True, trigger_text

        return False, ""

    def detect_negated_terms(self, sentence: str, targets: List[Tuple[int, int, str]]) -> List[dict]:
        """Detect negation for multiple targets in a sentence.

        Args:
            sentence: Full sentence text.
            targets: List of (start, end, label) tuples.

        Returns:
            List of {label, start, end, negated, trigger} dicts.
        """
        results = []
        for start, end, label in targets:
            negated, trigger = self.is_negated(sentence, start, end)
            results.append({
                "label": label,
                "text": sentence[start:end],
                "start": start,
                "end": end,
                "negated": negated,
                "trigger": trigger,
            })
        return results


# Module-level singleton for convenience
_default_detector = None

def get_detector() -> NegationDetector:
    global _default_detector
    if _default_detector is None:
        _default_detector = NegationDetector()
    return _default_detector
