import pytest

from nlp_pipeline_v2.disease_config_generator import generate_config
from nlp_pipeline_v2.pipeline import NLPExtractionPipeline


def test_generate_config_rejects_empty_disease_names():
    with pytest.raises(ValueError, match="non-empty disease"):
        generate_config(["", "   "])


def test_generate_config_keeps_literal_condition_when_ontology_has_no_match(monkeypatch):
    monkeypatch.setattr(
        "nlp_pipeline_v2.disease_config_generator.search_disease",
        lambda query, log=None: [],
    )

    config = generate_config(["Example Unknown Disease"])

    assert config["source_diseases"] == ["Example Unknown Disease"]
    assert "example_unknown_disease" in config["condition_terms"]
    assert config["condition_terms"]["example_unknown_disease"]["patterns"]


def test_explicit_empty_symptom_config_does_not_use_eds_pots_mcas_legacy_defaults():
    config = {
        "schema_version": "3.0",
        "condition_terms": {
            "example_unknown_disease": {
                "patterns": [r"example\s+unknown\s+disease"],
            }
        },
        "symptom_patterns": {},
        "drug_classes": {},
        "measurement_patterns": {},
        "negation_triggers": {"pre": [], "post": []},
        "section_blacklist": [],
    }
    pipeline = NLPExtractionPipeline(config=config)

    symptoms = pipeline._extract_symptoms_with_negation([
        "The patient had joint hypermobility and tachycardia."
    ])

    assert symptoms == []
