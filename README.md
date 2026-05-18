# triad_phenotype_mining

Literature mining of the EDS / POTS / MCAS triad and adjacent phenotypes from PubMed/PMC.

## Layout

- `scripts/` — pipeline stages (corpus retrieval → fulltext extraction → dataset build → analysis → figures → PDF build)
- `data/` — `raw/` metadata + fulltext (fulltext is gitignored; regenerate via `scripts/03_fulltext_extract.py`), `processed/` derived datasets
- `outputs/` — figures, tables, preliminary phenotyping report (markdown + PDF)
- `logs/` — provenance and retrieval logs
- `methodology/`, `validation/` — placeholders

## Pipeline

Numbered scripts in `scripts/` are intended to be run in order. The corpus is rebuilt from PubMed queries; fulltext is fetched from PMC where available.
