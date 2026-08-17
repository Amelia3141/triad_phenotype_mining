"""
Web UI for the NLP Case Report Phenotyping Pipeline.

FastAPI backend with SSE log streaming and a React frontend.
Run with: uvicorn nlp_pipeline_v2.web_app:app --reload --port 8000
Or:       python -m nlp_pipeline_v2.web_app

No AI API key needed; the pipeline is entirely rule-based (regex
patterns auto-generated from HPO/MONDO biomedical ontologies).
"""

import asyncio
import glob
import json
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Pipeline imports ──
import sys
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_pkg_dir)
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)

from nlp_pipeline_v2.disease_config_generator import generate_config
from nlp_pipeline_v2.pipeline import NLPExtractionPipeline
from nlp_pipeline_v2.pipeline_log import PipelineLog
from nlp_pipeline_v2.dataset_builder import build_all_outputs
from nlp_pipeline_v2.llm_enhancer import LLMEnhancer
from nlp_pipeline_v2.correction_memory import CorrectionMemory, Correction


# ── Global state ──
app = FastAPI(title="Case Report Phenotyping Pipeline")

# Per-session state (simple single-user; for multi-user, use session IDs)
_state = {
    "log_queue": queue.Queue(),
    "config": None,
    "articles_dir": None,
    "output_dir": None,
    "extractions": [],
    "status": "idle",       # idle | running | done | error
    "progress": "",
    "pmc_results": [],
}

# Persistent correction memory (survives across runs)
_corrections_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corrections.json")
_correction_memory = CorrectionMemory(persistent_path=_corrections_path)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
NCBI_RATE_LIMIT = 0.35  # seconds between requests


def _emit(msg: str, level: str = "info"):
    """Push a log message to the SSE queue."""
    _state["log_queue"].put({
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level": level,
        "message": msg,
    })


# ── Pydantic models ──

class ConfigRequest(BaseModel):
    diseases: List[str]
    comorbidities: List[str] = []

class PMCSearchRequest(BaseModel):
    query: str
    max_results: int = 200
    pub_types: List[str] = []   # UI keys; empty = no publication-type filter


# Map UI checkbox keys -> NLM publication-type values.
PUB_TYPE_FILTERS = {
    "case_reports": "case reports",
    "review": "review",
    "systematic_review": "systematic review",
    "clinical_trial": "clinical trial",
    "meta_analysis": "meta-analysis",
    "observational": "observational study",
    "comparative_study": "comparative study",
}


def build_pubmed_term(query: str, pub_types: List[str]) -> str:
    """Build a PubMed query: topic + optional publication-type filters,
    restricted to the PMC open-access subset so every hit is downloadable.

    We search PubMed (not PMC) because publication-type / MeSH indexing is
    only reliably populated on MEDLINE/PubMed records; the same filters are
    loose in PMC. Ticking types restricts to those (OR-combined), e.g. ticking
    'Case reports' yields:
        (query) AND ("case reports"[pt]) AND "pubmed pmc open access"[filter]
    No ticks leaves all paper types, still restricted to PMC open access.
    """
    term = (query or "").strip()
    pts = [
        f'"{PUB_TYPE_FILTERS[t]}"[pt]'
        for t in (pub_types or []) if t in PUB_TYPE_FILTERS
    ]
    if pts:
        term = f"({term}) AND ({' OR '.join(pts)})"
    # PMC open-access subset: guarantees a downloadable full-text XML exists.
    term = f'({term}) AND "pubmed pmc open access"[filter]'
    return term


# Backwards-compatible alias (older callers/tests).
build_pmc_term = build_pubmed_term

class DownloadRequest(BaseModel):
    # PMCIDs the user de-selected in the Search-results review tab. Optional so
    # older callers that POST no body keep working.
    exclude: List[str] = []

class RunPipelineRequest(BaseModel):
    enable_llm: bool = False
    llm_provider: str = "anthropic"  # "anthropic" or "openai"
    llm_model: str = ""              # blank = use default for provider
    llm_api_key: str = ""
    validate_ontology: bool = True   # filter discovered drugs/comorbidities via RxNorm/Mondo

class CorrectionRequest(BaseModel):
    subtask: str           # "temporal", "family_history", "treatment", "general"
    pattern: str           # short slug, e.g. "possessive_family_ref"
    error_description: str # what went wrong
    fix_instruction: str   # what to do instead
    pmcid: str = ""
    field: str = ""
    example_wrong: Optional[str] = None
    example_right: Optional[str] = None


# ── API endpoints ──

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_path = os.path.join(os.path.dirname(__file__), "frontend.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/status")
async def get_status():
    config = _state.get("config")
    conditions = []
    if config:
        for slug, entry in (config.get("condition_terms") or {}).items():
            conditions.append((entry or {}).get("canonical") or slug.replace("_", " "))
    return {
        "status": _state["status"],
        "progress": _state["progress"],
        "config_ready": config is not None,
        "search_terms": config.get("search_terms", []) if config else [],
        "conditions": conditions,   # authoritative disease names for run labelling
        "articles_count": len(glob.glob(os.path.join(_state.get("articles_dir") or "/tmp/nonexistent", "*.xml"))),
        "extractions_count": len(_state["extractions"]),
    }


@app.post("/api/generate-config")
async def api_generate_config(req: ConfigRequest, background_tasks: BackgroundTasks):
    """Generate extraction config from disease names."""
    _state["status"] = "running"
    _state["progress"] = "Generating config..."
    # NB: do NOT clear extractions here; generating a new config should not
    # wipe the previous run's reviewable results. They are cleared when a new
    # extraction actually starts.

    def _run():
        try:
            _emit(f"Resolving {len(req.diseases)} disease(s) through MONDO ontology...")
            for d in req.diseases:
                _emit(f"  Disease: {d}")
            if req.comorbidities:
                _emit(f"Resolving {len(req.comorbidities)} comorbidity/ies...")
                for c in req.comorbidities:
                    _emit(f"  Comorbidity: {c}")

            # Create output directories
            work_dir = tempfile.mkdtemp(prefix="phenotype_pipeline_")
            _state["output_dir"] = work_dir
            _state["articles_dir"] = os.path.join(work_dir, "articles")
            os.makedirs(_state["articles_dir"], exist_ok=True)

            config_path = os.path.join(work_dir, "config.json")
            log_path = os.path.join(work_dir, "config_generation_log.md")

            config = generate_config(
                disease_names=req.diseases,
                comorbidity_names=req.comorbidities if req.comorbidities else None,
                output_path=config_path,
                log_path=log_path,
            )
            _state["config"] = config

            _emit(f"Config generated successfully:", "success")
            _emit(f"  Conditions: {len(config.get('condition_terms', {}))}")
            _emit(f"  Symptom categories: {len(config.get('symptom_patterns', {}))}")
            _emit(f"  Comorbidity patterns: {len(config.get('comorbidity_patterns', {}))}")
            _emit(f"  Drug classes: {len(config.get('drug_classes', {}))}")

            # Stream the config log
            if os.path.exists(log_path):
                with open(log_path) as f:
                    for line in f:
                        line = line.rstrip()
                        if line:
                            _emit(f"[LOG] {line}", "log")

            _state["status"] = "idle"
            _state["progress"] = "Config ready"
        except Exception as e:
            _emit(f"Error: {e}", "error")
            _emit(traceback.format_exc(), "error")
            _state["status"] = "error"
            _state["progress"] = f"Config generation failed: {e}"

    background_tasks.add_task(_run)
    return {"message": "Config generation started"}


@app.post("/api/search-pmc")
async def api_search_pmc(req: PMCSearchRequest, background_tasks: BackgroundTasks):
    """Search PMC for articles matching query."""
    _state["status"] = "running"
    _state["progress"] = "Searching PMC..."
    # Reset ALL prior search state so a new search can't expose a stale total /
    # id list while the fresh preview is still empty.
    _state["pmc_results"] = []
    _state["_pmc_ids"] = []
    _state["_pmc_total"] = 0

    term = build_pubmed_term(req.query, req.pub_types)
    ua = {"User-Agent": "phenotype-pipeline/1.0"}

    def _run():
        try:
            _emit(f"Searching PubMed: {term}")
            if req.pub_types:
                _emit(f"Publication-type filter: {', '.join(req.pub_types)}")
            else:
                _emit("Publication-type filter: all types")
            # max_results <= 0 means "retrieve everything that matches".
            want = req.max_results if req.max_results and req.max_results > 0 else None
            _emit(f"Max results: {'all matches' if want is None else want}")

            # 1) ESearch PubMed (publication-type / MeSH indexing lives here).
            #    A single ESearch returns at most 10,000 IDs, so page through the
            #    result set with retstart to support large (or unbounded) requests.
            PAGE = 9999
            pmids = []
            count = 0
            retstart = 0
            while True:
                batch_size = PAGE if want is None else min(PAGE, want - len(pmids))
                if batch_size <= 0:
                    break
                params = {
                    "db": "pubmed",
                    "term": term,
                    "retmax": batch_size,
                    "retstart": retstart,
                    "retmode": "json",
                }
                url = NCBI_BASE + "esearch.fcgi?" + urllib.parse.urlencode(params)
                with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8", "ignore"), strict=False)
                result = data.get("esearchresult", {})
                count = int(result.get("count", 0))
                ids = result.get("idlist", [])
                if not ids:
                    break
                pmids.extend(ids)
                retstart += len(ids)
                if retstart >= count or len(ids) < batch_size:
                    break
                time.sleep(NCBI_RATE_LIMIT)
            _emit(f"PubMed: {count} matching records, retrieved {len(pmids)} PMIDs")

            # 2) Map PMIDs -> PMCIDs via the PMC ID Converter API (batched, max
            #    200/req). More reliable than elink for large batches. The PMC
            #    open-access filter guarantees each PMID has a PMC full text.
            idconv = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
            pmcid_nums = []
            for i in range(0, len(pmids), 200):
                batch = pmids[i:i + 200]
                time.sleep(NCBI_RATE_LIMIT)
                cu = idconv + "?" + urllib.parse.urlencode({
                    "tool": "phenotype-pipeline",
                    "email": "phenotype-pipeline@example.org",
                    "ids": ",".join(batch), "format": "json",
                })
                with urllib.request.urlopen(urllib.request.Request(cu, headers=ua), timeout=30) as cr:
                    conv = json.loads(cr.read().decode("utf-8", "ignore"), strict=False)
                for rec in conv.get("records", []):
                    pmcid = rec.get("pmcid")
                    if pmcid:
                        pmcid_nums.append(pmcid[3:] if pmcid.upper().startswith("PMC") else pmcid)

            # Dedup, preserve order
            seen = set()
            pmcid_nums = [x for x in pmcid_nums if not (x in seen or seen.add(x))]
            _emit(f"Mapped to {len(pmcid_nums)} open-access PMC articles")

            # 3) Summaries for the preview list
            pmc_results = []
            if pmcid_nums:
                time.sleep(NCBI_RATE_LIMIT)
                summary_params = {
                    "db": "pmc",
                    "id": ",".join(pmcid_nums[:50]),
                    "retmode": "json",
                }
                summary_url = NCBI_BASE + "esummary.fcgi?" + urllib.parse.urlencode(summary_params)
                with urllib.request.urlopen(urllib.request.Request(summary_url, headers=ua), timeout=30) as resp2:
                    summary_data = json.loads(resp2.read().decode("utf-8", "ignore"), strict=False)
                sresult = summary_data.get("result", {})
                for pmcid_num in pmcid_nums[:50]:
                    info = sresult.get(pmcid_num, {})
                    if isinstance(info, dict):
                        pmc_results.append({
                            "pmcid": f"PMC{pmcid_num}",
                            "title": info.get("title", "Unknown"),
                            "source": info.get("source", ""),
                            "pubdate": info.get("pubdate", ""),
                        })

            _state["pmc_results"] = pmc_results
            _state["_pmc_ids"] = [f"PMC{x}" for x in pmcid_nums]
            _state["_pmc_webenv"] = ""
            _state["_pmc_query_key"] = ""
            # "found" = total PubMed matches; "retrievable" = those we pulled.
            _state["_pmc_total"] = count

            _emit(f"Search complete. {len(pmc_results)} previewed, "
                  f"{len(pmcid_nums)} ready for download.", "success")
            _state["status"] = "idle"
            _state["progress"] = f"Found {count} articles ({len(pmcid_nums)} retrievable)"
        except Exception as e:
            _emit(f"Search error: {e}", "error")
            _state["status"] = "error"
            _state["progress"] = f"Search failed: {e}"

    background_tasks.add_task(_run)
    return {"message": "Search started"}


@app.get("/api/pmc-results")
async def get_pmc_results():
    return {
        "results": _state.get("pmc_results", []),
        "total": _state.get("_pmc_total", 0),
        "downloadable": len(_state.get("_pmc_ids", [])),
    }


@app.post("/api/download-articles")
async def api_download_articles(
    background_tasks: BackgroundTasks,
    max_articles: int = Query(default=100),
    req: Optional[DownloadRequest] = None,
):
    """Download full-text XML from PMC OA.

    An optional JSON body ``{"exclude": ["PMC123", ...]}`` drops articles the
    user de-selected in the review tab before the max-articles cap is applied.
    """
    _state["status"] = "running"
    _state["progress"] = "Downloading articles..."

    exclude = {x.upper() for x in (req.exclude if req else [])}

    def _run():
        try:
            all_ids = _state.get("_pmc_ids", [])
            kept = [p for p in all_ids if p.upper() not in exclude]
            if exclude:
                _emit(f"Excluding {len(all_ids) - len(kept)} de-selected article(s) from download")
            # max_articles <= 0 means "download all retrieved (non-excluded)".
            pmc_ids = kept if max_articles <= 0 else kept[:max_articles]
            if not pmc_ids:
                _emit("No PMCIDs to download. Run a search first.", "error")
                _state["status"] = "error"
                return

            articles_dir = _state.get("articles_dir")
            if not articles_dir:
                articles_dir = tempfile.mkdtemp(prefix="articles_")
                _state["articles_dir"] = articles_dir

            _emit(f"Downloading {len(pmc_ids)} articles from PMC OA...")
            downloaded = 0
            failed = 0

            for i, pmcid in enumerate(pmc_ids):
                try:
                    # PMC OA API for full text
                    oa_url = f"https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmcid.replace('PMC','')}&metadataPrefix=pmc"
                    req_obj = urllib.request.Request(oa_url, headers={"User-Agent": "phenotype-pipeline/1.0"})

                    with urllib.request.urlopen(req_obj, timeout=30) as resp:
                        xml_data = resp.read().decode("utf-8")

                    # Check if we got actual article content
                    if "<article" in xml_data:
                        out_path = os.path.join(articles_dir, f"{pmcid}.xml")
                        with open(out_path, "w", encoding="utf-8") as f:
                            f.write(xml_data)
                        downloaded += 1
                    else:
                        # Try efetch as fallback
                        efetch_url = f"{NCBI_BASE}efetch.fcgi?db=pmc&id={pmcid.replace('PMC','')}&rettype=xml"
                        req_obj2 = urllib.request.Request(efetch_url, headers={"User-Agent": "phenotype-pipeline/1.0"})
                        with urllib.request.urlopen(req_obj2, timeout=30) as resp2:
                            xml_data2 = resp2.read().decode("utf-8")
                        if "<article" in xml_data2 or "<body>" in xml_data2:
                            out_path = os.path.join(articles_dir, f"{pmcid}.xml")
                            with open(out_path, "w", encoding="utf-8") as f:
                                f.write(xml_data2)
                            downloaded += 1
                        else:
                            failed += 1
                            _emit(f"  {pmcid}: no full text available", "warn")

                except Exception as e:
                    failed += 1
                    _emit(f"  {pmcid}: download failed ({e})", "warn")

                if (i + 1) % 10 == 0 or i == len(pmc_ids) - 1:
                    _emit(f"  Progress: {i+1}/{len(pmc_ids)} ({downloaded} downloaded, {failed} failed)")

                time.sleep(NCBI_RATE_LIMIT)

            _emit(f"Download complete: {downloaded} articles, {failed} failed", "success")
            _state["status"] = "idle"
            _state["progress"] = f"{downloaded} articles downloaded"
        except Exception as e:
            _emit(f"Download error: {e}", "error")
            _state["status"] = "error"

    background_tasks.add_task(_run)
    return {"message": "Download started"}


@app.post("/api/run-pipeline")
async def api_run_pipeline(req: RunPipelineRequest, background_tasks: BackgroundTasks):
    """Run the extraction pipeline on downloaded articles."""
    _state["status"] = "running"
    _state["progress"] = "Running extraction..."
    _state["extractions"] = []

    # Capture request params for the background thread
    enable_llm = req.enable_llm
    llm_provider = req.llm_provider
    llm_model = req.llm_model
    llm_api_key = req.llm_api_key
    validate_ontology = req.validate_ontology

    def _run():
        try:
            config = _state.get("config")
            if not config:
                _emit("No config generated. Generate config first.", "error")
                _state["status"] = "error"
                return

            articles_dir = _state.get("articles_dir")
            if not articles_dir:
                _emit("No articles downloaded. Download articles first.", "error")
                _state["status"] = "error"
                return

            xml_files = sorted(glob.glob(os.path.join(articles_dir, "*.xml")))
            if not xml_files:
                _emit("No XML files found in articles directory.", "error")
                _state["status"] = "error"
                return

            _emit(f"Running extraction on {len(xml_files)} articles...")
            _emit(f"Config: {len(config.get('symptom_patterns', {}))} symptom categories, "
                  f"{len(config.get('comorbidity_patterns', {}))} comorbidities, "
                  f"{len(config.get('drug_classes', {}))} drug classes")

            # Set up LLM enhancer if enabled
            enhancer = None
            if enable_llm and llm_api_key:
                corr_stats = _correction_memory.get_stats()
                _emit(f"LLM enhancement enabled: {llm_provider} / {llm_model or 'default'}")
                if corr_stats["total"] > 0:
                    _emit(f"Correction memory: {corr_stats['total']} corrections loaded ({corr_stats['by_subtask']})")
                enhancer = LLMEnhancer(
                    api_key=llm_api_key,
                    provider=llm_provider,
                    model=llm_model or None,
                    log_fn=lambda msg: _emit(f"[LLM] {msg}"),
                    correction_memory=_correction_memory,
                )
            elif enable_llm and not llm_api_key:
                _emit("LLM enhancement requested but no API key provided; running rule-based only.", "warn")

            # Set up pipeline with logging
            work_dir = _state["output_dir"]
            log_path = os.path.join(work_dir, "extraction_log.md")
            log = PipelineLog(log_path, title="NLP Extraction Run")
            pipeline = NLPExtractionPipeline(config, log=log, llm_enhancer=enhancer)
            pipeline.start_batch_log(len(xml_files))

            extractions = []
            errors = 0
            start_time = time.time()

            for i, xml_path in enumerate(xml_files):
                pmcid = os.path.basename(xml_path).replace(".xml", "")
                try:
                    result = pipeline.extract_from_xml(xml_path)
                    extractions.append(result)

                    if result.get("error"):
                        errors += 1
                        _emit(f"  {pmcid}: {result['error']}", "warn")
                    else:
                        summary = result.get("completeness", {}).get("_summary", {})
                        symp_count = len(result.get("symptoms_affirmed", []))
                        drug_count = result.get("drug_count", 0)
                        comorb_count = len(result.get("comorbidities", {}))
                        _emit(f"  {pmcid}: {symp_count} symptoms, {drug_count} drugs, "
                              f"{comorb_count} comorbidities, "
                              f"completeness={summary.get('completeness_score', 0):.1%}")
                except Exception as e:
                    errors += 1
                    _emit(f"  {pmcid}: extraction error ({e})", "error")

                if (i + 1) % 25 == 0 or i == len(xml_files) - 1:
                    elapsed = time.time() - start_time
                    rate = (i + 1) / elapsed if elapsed > 0 else 0
                    eta = (len(xml_files) - i - 1) / rate if rate > 0 else 0
                    _emit(f"  Progress: {i+1}/{len(xml_files)} "
                          f"({rate:.1f} articles/sec, ETA {eta:.0f}s)")

            pipeline.finalise_log()

            # ── Ontology validation (maximum-precision mode) ──
            # Filter corpus-discovered drugs/comorbidities to those that resolve
            # against RxNorm / Mondo, dropping heuristic false positives. Only
            # touches *discovered* terms — configured/known terms are untouched.
            if validate_ontology:
                try:
                    from nlp_pipeline_v2.ontology_validation import validate_terms
                    cfg = config or {}
                    comorb_discovery = (not cfg.get("comorbidity_patterns")
                                        and not cfg.get("use_legacy_comorbidity_patterns"))

                    drug_cands = {
                        d["drug"] for e in extractions
                        for d in (e.get("drugs_affirmed", []) + e.get("drugs_negated", []))
                        if d.get("drug_class") == "discovered"
                    }
                    if drug_cands:
                        _emit(f"Validating {len(drug_cands)} discovered drug(s) against RxNorm...")
                        ok = validate_terms(drug_cands, "drug", log_fn=_emit)
                        for e in extractions:
                            for key in ("drugs_affirmed", "drugs_negated"):
                                e[key] = [
                                    d for d in e.get(key, [])
                                    if d.get("drug_class") != "discovered"
                                    or d["drug"].lower() in ok
                                ]
                            e["drug_count"] = len(e.get("drugs_affirmed", []))

                    if comorb_discovery:
                        comb_cands = {name for e in extractions for name in e.get("comorbidities", {})}
                        if comb_cands:
                            _emit(f"Validating {len(comb_cands)} discovered comorbidit(y/ies) against Mondo...")
                            ok = validate_terms(comb_cands, "disease", log_fn=_emit)
                            for e in extractions:
                                e["comorbidities"] = {
                                    k: v for k, v in e.get("comorbidities", {}).items()
                                    if k.lower() in ok
                                }
                    _emit("Ontology validation complete.", "success")
                except Exception as ve:
                    _emit(f"Ontology validation skipped ({ve}); keeping unvalidated terms.", "warn")

            _state["extractions"] = extractions

            # Build dataset outputs
            _emit("Building dataset outputs...")
            outputs_dir = os.path.join(work_dir, "outputs")
            os.makedirs(outputs_dir, exist_ok=True)

            # Save raw extractions
            raw_path = os.path.join(outputs_dir, "extractions.json")
            with open(raw_path, "w") as f:
                json.dump(extractions, f, indent=2, default=str)

            try:
                build_all_outputs(extractions, outputs_dir)
                _emit("Dataset outputs built:", "success")
                for fname in sorted(os.listdir(outputs_dir)):
                    fsize = os.path.getsize(os.path.join(outputs_dir, fname))
                    _emit(f"  {fname} ({fsize:,} bytes)")
            except Exception as e:
                _emit(f"Warning: dataset builder error: {e}", "warn")
                _emit("Raw extractions JSON still available.", "warn")

            elapsed = time.time() - start_time
            _emit(f"Extraction complete: {len(extractions)} articles in {elapsed:.1f}s, {errors} errors", "success")
            if enhancer:
                stats = enhancer.get_stats()
                _emit(f"LLM usage: {stats['total_calls']} calls, ~{stats['total_tokens']} tokens ({stats['provider']}/{stats['model']})")
                llm_enhanced = sum(1 for e in extractions if e.get("_llm_enhanced"))
                _emit(f"LLM enhanced {llm_enhanced}/{len(extractions)} articles")

            # Stream the extraction log
            if os.path.exists(log_path):
                _emit("--- Extraction Log ---", "log")
                with open(log_path) as f:
                    for line in f:
                        line = line.rstrip()
                        if line:
                            _emit(f"[LOG] {line}", "log")

            _state["status"] = "done"
            _state["progress"] = f"Done: {len(extractions)} articles extracted"
        except Exception as e:
            _emit(f"Pipeline error: {e}", "error")
            _emit(traceback.format_exc(), "error")
            _state["status"] = "error"
            _state["progress"] = f"Pipeline failed: {e}"

    background_tasks.add_task(_run)
    return {"message": "Pipeline started"}


@app.get("/api/stream-logs")
async def stream_logs():
    """SSE endpoint for real-time log streaming."""
    async def event_generator():
        while True:
            try:
                msg = _state["log_queue"].get_nowait()
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                # Send keepalive
                yield f": keepalive\n\n"
                await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/results")
async def get_results():
    """Get extraction results summary."""
    extractions = _state.get("extractions", [])
    if not extractions:
        return {"count": 0, "summary": None, "articles": []}

    # Compute aggregate stats
    total = len(extractions)
    has_error = sum(1 for e in extractions if e.get("error"))
    ages = [e["age_at_presentation"] for e in extractions if e.get("age_at_presentation") is not None]
    sexes = {}
    for e in extractions:
        s = e.get("sex", "unknown") or "unknown"
        sexes[s] = sexes.get(s, 0) + 1

    all_symptoms = {}
    for e in extractions:
        for s in e.get("symptoms_affirmed", []):
            name = s["symptom"]
            all_symptoms[name] = all_symptoms.get(name, 0) + 1

    all_drugs = {}
    for e in extractions:
        for d in e.get("drugs_affirmed", []):
            name = d["drug"]
            all_drugs[name] = all_drugs.get(name, 0) + 1

    all_comorbidities = {}
    for e in extractions:
        for name, data in e.get("comorbidities", {}).items():
            if data.get("mentioned") and not data.get("negated"):
                all_comorbidities[name] = all_comorbidities.get(name, 0) + 1

    avg_completeness = 0
    comp_scores = [
        e.get("completeness", {}).get("_summary", {}).get("completeness_score", 0)
        for e in extractions if not e.get("error")
    ]
    if comp_scores:
        avg_completeness = sum(comp_scores) / len(comp_scores)

    top_symptoms = sorted(all_symptoms.items(), key=lambda x: -x[1])[:20]
    top_drugs = sorted(all_drugs.items(), key=lambda x: -x[1])[:20]
    top_comorbidities = sorted(all_comorbidities.items(), key=lambda x: -x[1])[:15]

    # ── Condition co-occurrence ──
    # For each user-defined (top-level) condition, count the articles where it
    # is affirmed, then count how often the conditions appear together. This
    # generalises the EDS/POTS/MCAS triad view to any set of conditions.
    valid = [e for e in extractions if not e.get("error")]
    n_valid = len(valid)
    config = _state.get("config") or {}
    condition_terms = config.get("condition_terms", {})

    def _present_conditions(e):
        cmap = e.get("conditions", {})
        return {
            slug for slug in condition_terms
            if cmap.get(slug, {}).get("mentioned") and not cmap.get(slug, {}).get("negated")
        }

    condition_presence = []
    for slug, conf in condition_terms.items():
        cnt = sum(1 for e in valid if slug in _present_conditions(e))
        condition_presence.append({
            "name": slug,
            "full_name": (conf or {}).get("canonical") or slug,
            "count": cnt,
            "pct": round(cnt / n_valid * 100, 1) if n_valid else 0,
        })

    cooccurrence = []
    if len(condition_terms) >= 2:
        import itertools
        keys = list(condition_terms.keys())
        present_sets = [_present_conditions(e) for e in valid]
        for a, b in itertools.combinations(keys, 2):
            cnt = sum(1 for ps in present_sets if a in ps and b in ps)
            cooccurrence.append({"name": f"{a} + {b}", "count": cnt,
                                 "pct": round(cnt / n_valid * 100, 1) if n_valid else 0})
        cooccurrence.sort(key=lambda x: -x["count"])
        cooccurrence = cooccurrence[:10]
        if len(keys) > 2:
            allcnt = sum(1 for ps in present_sets if set(keys) <= ps)
            cooccurrence.append({
                "name": f"All {len(keys)} ({' + '.join(keys)})", "count": allcnt,
                "pct": round(allcnt / n_valid * 100, 1) if n_valid else 0, "full": True,
            })

    # ── Comorbidity analysis ──
    # Rate (% of cases) for each detected comorbidity, plus the share of cases
    # that report at least one comorbidity (i.e. the patient had other diseases).
    comorbidity_rates = [
        {"name": name, "count": cnt,
         "pct": round(cnt / n_valid * 100, 1) if n_valid else 0}
        for name, cnt in top_comorbidities
    ]
    any_comorb = sum(
        1 for e in valid
        if any(d.get("mentioned") and not d.get("negated")
               for d in e.get("comorbidities", {}).values())
    )
    comorbidity_any = {
        "count": any_comorb,
        "pct": round(any_comorb / n_valid * 100, 1) if n_valid else 0,
    }

    return {
        "count": total,
        "errors": has_error,
        "summary": {
            "age_range": [min(ages), max(ages)] if ages else None,
            "age_mean": round(sum(ages) / len(ages), 1) if ages else None,
            "sex_distribution": sexes,
            "avg_completeness": round(avg_completeness, 3),
            "top_symptoms": top_symptoms,
            "top_drugs": top_drugs,
            "top_comorbidities": top_comorbidities,
            "condition_presence": condition_presence,
            "cooccurrence": cooccurrence,
            "comorbidity_rates": comorbidity_rates,
            "comorbidity_any": comorbidity_any,
        },
    }



@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download an output file."""
    work_dir = _state.get("output_dir")
    if not work_dir:
        return JSONResponse({"error": "No outputs available"}, status_code=404)

    # Check outputs dir first, then work dir root
    for search_dir in [os.path.join(work_dir, "outputs"), work_dir]:
        fpath = os.path.join(search_dir, filename)
        if os.path.exists(fpath) and os.path.isfile(fpath):
            return FileResponse(fpath, filename=filename)

    return JSONResponse({"error": f"File not found: {filename}"}, status_code=404)


@app.get("/api/download-all")
async def download_all_files():
    """Bundle every output file into a single zip for one-click download."""
    import io
    import zipfile

    work_dir = _state.get("output_dir")
    if not work_dir:
        return JSONResponse({"error": "No outputs available"}, status_code=404)

    seen = set()
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # outputs/ first so it wins on any name clash with the work-dir root
        for search_dir in [os.path.join(work_dir, "outputs"), work_dir]:
            if not os.path.isdir(search_dir):
                continue
            for fname in sorted(os.listdir(search_dir)):
                fpath = os.path.join(search_dir, fname)
                if os.path.isfile(fpath) and fname not in seen:
                    seen.add(fname)
                    zf.write(fpath, arcname=fname)
                    count += 1

    if count == 0:
        return JSONResponse({"error": "No output files to download"}, status_code=404)

    buf.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="phenotyping_outputs.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


@app.get("/api/output-files")
async def list_output_files():
    """List available output files."""
    work_dir = _state.get("output_dir")
    if not work_dir:
        return {"files": []}

    files = []
    outputs_dir = os.path.join(work_dir, "outputs")
    for search_dir in [outputs_dir, work_dir]:
        if os.path.exists(search_dir):
            for fname in sorted(os.listdir(search_dir)):
                fpath = os.path.join(search_dir, fname)
                if os.path.isfile(fpath):
                    files.append({
                        "name": fname,
                        "size": os.path.getsize(fpath),
                        "dir": os.path.basename(search_dir),
                    })

    return {"files": files}


# ── Review & corrections ──

def _load_extractions():
    """Return the current run's extractions, falling back to the last run's
    extractions.json on disk if in-memory state was cleared (e.g. after a new
    config was generated, or the server restarted)."""
    extractions = _state.get("extractions", [])
    if extractions:
        return extractions
    work_dir = _state.get("output_dir")
    if work_dir:
        path = os.path.join(work_dir, "outputs", "extractions.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return []


@app.get("/api/review")
async def list_reviewable_articles():
    """List extracted articles available for review."""
    extractions = _load_extractions()
    articles = []
    for e in extractions:
        if e.get("error"):
            continue
        articles.append({
            "pmcid": e.get("pmcid", ""),
            "age": e.get("age_at_presentation"),
            "sex": e.get("sex"),
            "symptom_count": len(e.get("symptoms_affirmed", [])),
            "drug_count": e.get("drug_count", 0),
            "completeness": e.get("completeness", {}).get("_summary", {}).get("completeness_score", 0),
            "llm_enhanced": e.get("_llm_enhanced", False),
        })
    return {"articles": articles, "total": len(articles)}


@app.get("/api/review/{pmcid}")
async def get_article_for_review(pmcid: str):
    """Get a single article's extraction for review."""
    # Use the same source as the list endpoint (in-memory, else last run on
    # disk) so a detail lookup never 404s for an article the list returned.
    extractions = _load_extractions()
    for e in extractions:
        if e.get("pmcid") == pmcid:
            return {"extraction": e}
    return JSONResponse({"error": f"Article {pmcid} not found"}, status_code=404)


@app.post("/api/correction")
async def submit_correction(req: CorrectionRequest):
    """Submit a correction from review. Persists to disk."""
    if req.subtask not in CorrectionMemory.SUBTASKS:
        return JSONResponse(
            {"error": f"Invalid subtask. Must be one of: {CorrectionMemory.SUBTASKS}"},
            status_code=400,
        )

    c = _correction_memory.add_from_review(
        subtask=req.subtask,
        pattern=req.pattern,
        error_description=req.error_description,
        fix_instruction=req.fix_instruction,
        pmcid=req.pmcid,
        field=req.field,
        example_wrong=req.example_wrong,
        example_right=req.example_right,
    )
    _correction_memory.save()
    _emit(f"Correction added: [{req.subtask}] {req.pattern} - {req.error_description}", "success")
    return {"message": "Correction saved", "correction": c.to_dict()}


@app.get("/api/corrections")
async def list_corrections():
    """List all corrections with stats."""
    return {
        "corrections": _correction_memory.get_all(),
        "stats": _correction_memory.get_stats(),
    }


@app.delete("/api/correction/{correction_id}")
async def delete_correction(correction_id: str):
    """Remove a correction."""
    if _correction_memory.remove(correction_id):
        _correction_memory.save()
        return {"message": "Correction deleted"}
    return JSONResponse({"error": "Correction not found"}, status_code=404)


# ── Serve app ──
if __name__ == "__main__":
    import uvicorn
    print("Starting pipeline UI at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
