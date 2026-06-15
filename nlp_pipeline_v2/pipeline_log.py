"""
Scientific reproducibility logger.

Writes a structured markdown log at every pipeline step, to the level
of detail needed for Methods sections and precise reproducibility.
Records: data sources, API queries, parameter choices, processing
decisions, counts, and timestamps.
"""

import datetime
import json
import os
from typing import Any, Optional


class PipelineLog:
    """Append-only markdown log for scientific reproducibility.

    Usage:
        log = PipelineLog("logs/pipeline_run.md", title="EDS/POTS/MCAS Extraction")
        log.section("Corpus Retrieval")
        log.step("Search PubMed Central", query="...", results=1400)
        log.decision("Excluded 5 articles with no body text")
        log.parameter("negation_window", 60, "characters")
        log.data_source("HPO", "https://hpo.jax.org", version="2024-04-04")
        log.close()
    """

    def __init__(self, path: str, title: str = "NLP Extraction Pipeline"):
        self.path = path
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

        self._lines = []
        self._section_count = 0
        self._step_count = 0

        self._write(f"# {title}")
        self._write(f"")
        self._write(f"**Generated**: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        self._write(f"**Pipeline version**: nlp_v2")
        self._write(f"**Purpose**: Full provenance log for scientific reproducibility")
        self._write(f"")
        self._write(f"---")
        self._write(f"")

    def section(self, title: str):
        """Start a new major section (e.g., 'Configuration Generation')."""
        self._section_count += 1
        self._step_count = 0
        self._write(f"## {self._section_count}. {title}")
        self._write(f"")

    def step(self, description: str, **kwargs):
        """Log a processing step with optional key-value details."""
        self._step_count += 1
        ts = datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')
        self._write(f"### {self._section_count}.{self._step_count} {description}")
        self._write(f"")
        self._write(f"*Timestamp*: {ts} UTC")
        if kwargs:
            for k, v in kwargs.items():
                if isinstance(v, (dict, list)):
                    self._write(f"- **{k}**:")
                    self._write(f"  ```json")
                    self._write(f"  {json.dumps(v, indent=2, default=str)[:500]}")
                    self._write(f"  ```")
                else:
                    self._write(f"- **{k}**: {v}")
        self._write(f"")

    def detail(self, text: str):
        """Add a detail line within the current step."""
        self._write(f"- {text}")

    def decision(self, description: str, reason: str = ""):
        """Log a processing decision with rationale."""
        self._write(f"**Decision**: {description}")
        if reason:
            self._write(f"  *Reason*: {reason}")
        self._write(f"")

    def parameter(self, name: str, value: Any, unit: str = ""):
        """Log a parameter value."""
        unit_str = f" {unit}" if unit else ""
        self._write(f"- Parameter `{name}` = `{value}`{unit_str}")

    def data_source(self, name: str, url: str, version: str = "",
                    accessed: str = ""):
        """Log an external data source."""
        if not accessed:
            accessed = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
        self._write(f"**Data source**: {name}")
        self._write(f"- URL: {url}")
        if version:
            self._write(f"- Version: {version}")
        self._write(f"- Accessed: {accessed}")
        self._write(f"")

    def result(self, description: str, **counts):
        """Log a result with optional counts."""
        self._write(f"**Result**: {description}")
        for k, v in counts.items():
            self._write(f"- {k}: {v}")
        self._write(f"")

    def warning(self, text: str):
        """Log a warning."""
        self._write(f"> **Warning**: {text}")
        self._write(f"")

    def error(self, text: str):
        """Log an error."""
        self._write(f"> **Error**: {text}")
        self._write(f"")

    def table(self, headers: list, rows: list):
        """Write a markdown table."""
        self._write(f"| {' | '.join(str(h) for h in headers)} |")
        self._write(f"| {' | '.join('---' for _ in headers)} |")
        for row in rows:
            self._write(f"| {' | '.join(str(c) for c in row)} |")
        self._write(f"")

    def code_block(self, content: str, lang: str = "json"):
        """Write a fenced code block."""
        self._write(f"```{lang}")
        self._write(content[:2000])
        self._write(f"```")
        self._write(f"")

    def _write(self, line: str):
        """Append a line and flush to disk."""
        self._lines.append(line)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def close(self):
        """Write closing section."""
        self._write(f"---")
        self._write(f"")
        self._write(f"**Log complete**: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        self._write(f"**Total sections**: {self._section_count}")
