#!/usr/bin/env python3
"""
Phase 1: Retrieve PMCIDs and metadata for EDS/hEDS, POTS, MCAS case reports
from PMC Open Access subset via NCBI E-utilities.

Provenance: All queries logged with timestamps and parameters.
"""

import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import json
import csv
import time
import datetime
import os

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
OUTPUT_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining/data/raw"
LOG_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining/logs"

# Rate limit: NCBI allows 3 requests/sec without API key, 10/sec with
RATE_LIMIT = 0.35  # seconds between requests

def log_query(query_name, params, result_count):
    """Append query details to the retrieval log."""
    log_file = os.path.join(LOG_DIR, "retrieval_queries.jsonl")
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "query_name": query_name,
        "parameters": params,
        "result_count": result_count
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"  Logged: {query_name} -> {result_count} results")

def esearch(db, term, retmax=0, usehistory="y"):
    """Run an ESearch query, return (count, webenv, query_key)."""
    params = {
        "db": db,
        "term": term,
        "rettype": "count" if retmax == 0 else "xml",
        "retmax": retmax,
        "usehistory": usehistory
    }
    url = BASE_URL + "esearch.fcgi?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        xml_data = resp.read().decode("utf-8")
    root = ET.fromstring(xml_data)
    count = int(root.findtext("Count", "0"))
    webenv = root.findtext("WebEnv", "")
    query_key = root.findtext("QueryKey", "")
    return count, webenv, query_key, xml_data

def efetch_summaries(db, webenv, query_key, count, batch_size=500):
    """Fetch document summaries in batches using history server."""
    all_docs = []
    for start in range(0, count, batch_size):
        params = {
            "db": db,
            "query_key": query_key,
            "WebEnv": webenv,
            "retstart": start,
            "retmax": batch_size,
            "rettype": "xml",
            "retmode": "xml"
        }
        url = BASE_URL + "esummary.fcgi?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=60) as resp:
            xml_data = resp.read().decode("utf-8")
        root = ET.fromstring(xml_data)
        
        for doc in root.findall(".//DocSum"):
            pmcid = ""
            title = ""
            source = ""
            pubdate = ""
            authors = ""
            doi = ""
            
            uid = doc.findtext("Id", "")
            for item in doc.findall("Item"):
                name = item.get("Name", "")
                if name == "Title":
                    title = item.text or ""
                elif name == "Source":
                    source = item.text or ""
                elif name == "PubDate":
                    pubdate = item.text or ""
                elif name == "AuthorList":
                    author_items = item.findall("Item")
                    authors = "; ".join(a.text for a in author_items if a.text)
                elif name == "DOI":
                    doi = item.text or ""
                elif name == "ArticleIds":
                    for sub in item.findall("Item"):
                        if sub.get("Name") == "pmcid":
                            pmcid = sub.text or ""
            
            all_docs.append({
                "uid": uid,
                "pmcid": pmcid if pmcid.startswith("PMC") else f"PMC{uid}",
                "title": title,
                "journal": source,
                "pubdate": pubdate,
                "authors": authors,
                "doi": doi
            })
        
        print(f"  Fetched {min(start + batch_size, count)}/{count} summaries")
        time.sleep(RATE_LIMIT)
    
    return all_docs

# Define search queries - refined for case reports with OA filter
QUERIES = {
    "EDS_hEDS": (
        '("ehlers-danlos syndrome"[Title/Abstract] OR "ehlers danlos"[Title/Abstract] '
        'OR "hypermobile ehlers"[Title/Abstract] OR "hEDS"[Title/Abstract] '
        'OR "hypermobility syndrome"[Title/Abstract]) '
        'AND "case reports"[Publication Type] '
        'AND "open access"[Filter]'
    ),
    "POTS": (
        '("postural orthostatic tachycardia syndrome"[Title/Abstract] '
        'OR "postural tachycardia syndrome"[Title/Abstract] '
        'OR "POTS"[Title/Abstract]) '
        'AND "case reports"[Publication Type] '
        'AND "open access"[Filter]'
    ),
    "MCAS": (
        '("mast cell activation syndrome"[Title/Abstract] '
        'OR "mast cell activation disease"[Title/Abstract] '
        'OR "MCAS"[Title/Abstract] '
        'OR "mastocytosis"[Title/Abstract]) '
        'AND "case reports"[Publication Type] '
        'AND "open access"[Filter]'
    ),
    "TRIAD_cooccurrence": (
        '(("ehlers-danlos"[Title/Abstract] OR "hEDS"[Title/Abstract] '
        'OR "hypermobility"[Title/Abstract]) '
        'AND ("postural orthostatic tachycardia"[Title/Abstract] OR "POTS"[Title/Abstract]) '
        'AND ("mast cell"[Title/Abstract] OR "MCAS"[Title/Abstract])) '
        'AND "open access"[Filter]'
    )
}

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_results = {}
    
    for query_name, term in QUERIES.items():
        print(f"\n{'='*60}")
        print(f"Query: {query_name}")
        print(f"{'='*60}")
        
        # Step 1: Get count and history
        count, webenv, query_key, _ = esearch("pmc", term, retmax=10000, usehistory="y")
        print(f"  Count: {count}")
        log_query(query_name, {"db": "pmc", "term": term}, count)
        time.sleep(RATE_LIMIT)
        
        if count == 0:
            print(f"  No results for {query_name}, skipping.")
            continue
        
        # Step 2: Fetch summaries
        docs = efetch_summaries("pmc", webenv, query_key, min(count, 10000))
        all_results[query_name] = docs
        
        # Step 3: Save to CSV
        outfile = os.path.join(OUTPUT_DIR, f"{query_name}_metadata.csv")
        with open(outfile, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["uid", "pmcid", "title", "journal", "pubdate", "authors", "doi"])
            writer.writeheader()
            writer.writerows(docs)
        print(f"  Saved {len(docs)} records to {outfile}")
        
        time.sleep(1)  # Be polite between major queries
    
    # Summary
    print(f"\n{'='*60}")
    print("CORPUS SUMMARY")
    print(f"{'='*60}")
    for qname, docs in all_results.items():
        print(f"  {qname}: {len(docs)} articles")
    
    # Save combined summary
    summary = {
        "retrieval_date": datetime.datetime.utcnow().isoformat(),
        "queries": {k: len(v) for k, v in all_results.items()},
        "total_unique_pmcids": len(set(
            d["pmcid"] for docs in all_results.values() for d in docs
        ))
    }
    with open(os.path.join(OUTPUT_DIR, "corpus_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n  Total unique PMCIDs: {summary['total_unique_pmcids']}")
    print("Done.")

if __name__ == "__main__":
    main()
