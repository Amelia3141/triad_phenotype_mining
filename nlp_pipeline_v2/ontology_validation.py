"""Ontology validation for corpus-discovered terms (maximum-precision mode).

Discovered drugs and comorbidities are heuristic (morphology + cue) matches, so
they can include false positives. This module validates each *unique* candidate
against an authoritative ontology and keeps only the ones that resolve:

  * drugs       -> NIH RxNorm via the RxNav REST API
  * diseases    -> Mondo via the EBI OLS4 search API

Results are cached on disk (so repeat runs are instant) and in memory. Network
calls are made once per unique candidate, rate-limited and resilient: if the
service looks unreachable we keep all candidates rather than wrongly dropping
real terms.
"""

import json
import os
import threading
import urllib.parse
import urllib.request

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ontology_cache.json")
_LOCK = threading.Lock()

RXNAV_URL = "https://rxnav.nlm.nih.gov/REST/rxcui.json"
OLS_URL = "https://www.ebi.ac.uk/ols4/api/search"
_UA = {"Accept": "application/json", "User-Agent": "phenotype-pipeline/1.0"}


def _load_cache() -> dict:
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            c = json.load(f)
    except Exception:
        c = {}
    c.setdefault("drug", {})
    c.setdefault("disease", {})
    return c


def _save_cache(cache: dict) -> None:
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _get_json(url: str, timeout: int = 15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _is_drug(name: str) -> bool:
    """True if RxNorm recognises the name as a drug (normalised match)."""
    url = RXNAV_URL + "?" + urllib.parse.urlencode({"name": name, "search": 1})
    data = _get_json(url)
    ids = (data.get("idGroup") or {}).get("rxnormId") or []
    return bool(ids)


def _is_disease(name: str) -> bool:
    """True if the name resolves to a Mondo disease term (exact, else a label
    that contains the full candidate phrase)."""
    exact = OLS_URL + "?" + urllib.parse.urlencode(
        {"q": name, "ontology": "mondo", "exact": "true", "rows": 1})
    docs = ((_get_json(exact).get("response") or {}).get("docs") or [])
    if docs:
        return True
    loose = OLS_URL + "?" + urllib.parse.urlencode(
        {"q": name, "ontology": "mondo", "rows": 1})
    docs = ((_get_json(loose).get("response") or {}).get("docs") or [])
    return bool(docs and name.lower() in (docs[0].get("label", "").lower()))


def validate_terms(names, kind: str, log_fn=None, max_workers: int = 10) -> set:
    """Return the subset of `names` (lower-cased) that validate against the
    ontology for `kind` ("drug" or "disease").

    Uncached terms are looked up concurrently (a thread pool) with periodic
    progress so a large candidate set doesn't look like a hang. Resilient: a
    transient failure keeps that term; a total outage keeps everything.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    checker = _is_drug if kind == "drug" else _is_disease
    names = sorted({(n or "").strip().lower() for n in names if n and n.strip()})
    if not names:
        return set()

    with _LOCK:
        cache = _load_cache()
    kc = cache.get(kind, {})

    valid = set()
    to_check = []
    for n in names:
        if n in kc:
            if kc[n]:
                valid.add(n)
        else:
            to_check.append(n)

    if to_check and log_fn:
        log_fn(f"  {kind}: {len(names) - len(to_check)} cached, looking up {len(to_check)} "
               f"with {max_workers} workers...")

    def _work(n):
        try:
            return n, bool(checker(n)), False
        except Exception:
            return n, None, True

    done = errors = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_work, n) for n in to_check]
        for fut in as_completed(futures):
            n, ok, err = fut.result()
            done += 1
            if err:
                errors += 1
                valid.add(n)            # benefit of the doubt on a transient failure
            else:
                kc[n] = ok
                if ok:
                    valid.add(n)
            if log_fn and (done % 50 == 0 or done == len(to_check)):
                log_fn(f"  {kind} validation: {done}/{len(to_check)} checked")

    if to_check:
        with _LOCK:
            full = _load_cache()
            full[kind].update(kc)
            _save_cache(full)

    if errors and log_fn:
        log_fn(f"  {kind}: {errors} lookups failed (kept those terms).", "warn")
    if log_fn:
        dropped = len(names) - len(valid)
        log_fn(f"Ontology check ({kind}): {len(valid)}/{len(names)} validated, {dropped} dropped.")
    return valid
