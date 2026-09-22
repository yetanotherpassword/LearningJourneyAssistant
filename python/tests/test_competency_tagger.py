"""Tests for lja.data.competency_tagger on synthetic vectors -- no embedding
server, no chat model."""

from __future__ import annotations

import numpy as np

from lja.data.catalogue import Catalogue
from lja.data.competency_tagger import ClusterLabel, keyword_label, kmeans, pca_loadings, tag_catalogue


def _blobs(n_per: int = 10, dim: int = 16, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(3, dim))
    x = np.concatenate([c + 0.05 * rng.normal(size=(n_per, dim)) for c in centres])
    truth = np.repeat(np.arange(3), n_per)
    return x, truth


def test_kmeans_recovers_well_separated_blobs() -> None:
    x, truth = _blobs()
    labels, centres = kmeans(x, 3, seed=1)
    assert centres.shape == (3, 16)
    # Same partition up to relabelling.
    for t in range(3):
        assert len(set(labels[truth == t])) == 1
    assert len(set(labels)) == 3


def test_kmeans_is_deterministic_for_a_seed() -> None:
    x, _ = _blobs(seed=3)
    a, _ = kmeans(x, 3, seed=5)
    b, _ = kmeans(x, 3, seed=5)
    assert np.array_equal(a, b)


def test_pca_loadings_are_unit_rows() -> None:
    rng = np.random.default_rng(0)
    centres = rng.normal(size=(9, 32))
    load = pca_loadings(centres, 4)
    assert load.shape == (9, 4)
    assert np.allclose(np.linalg.norm(load, axis=1), 1.0)
    assert pca_loadings(centres, 100).shape[1] == 8  # capped at k-1


def test_keyword_label_skips_stopwords() -> None:
    label = keyword_label(["applying the titration method to acids", "titration of bases using the method"])
    assert "titration" in label and "the" not in label.split(" / ")


def _raw_catalogue() -> Catalogue:
    subjects = []
    for code, texts in (("CHE1A", ["titrating acids", "writing lab reports"]), ("BIO1B", ["culturing cells", "writing lab reports well"]),
                        ("MAT1C", ["solving linear equations", "proving theorems"])):
        subjects.append({
            "code": code, "title": code, "year_level": 1,
            "silos": [{"id": f"SILO{i + 1}", "text": t, "competency": "untagged"} for i, t in enumerate(texts)],
            "assessments": [{"name": "Exam", "weight": 1.0, "silos": [f"SILO{i + 1}" for i in range(len(texts))]}],
        })
    return Catalogue.model_validate({"competencies": [{"id": "untagged", "label": "Untagged"}], "subjects": subjects})


def test_tag_catalogue_assigns_every_silo_and_writes_traits() -> None:
    catalogue = _raw_catalogue()
    keys = [f"{s.code}:{silo.id}" for s in catalogue.subjects for silo in s.silos]
    # Two "lab report" SILOs identical, two "wet lab" alike, two maths alike.
    base = np.eye(3)
    emb = np.array([base[0], base[1], base[0] + 0.01, base[1] + 0.01, base[2], base[2] + 0.01])
    labels = {0: ClusterLabel(cluster=0, id="a", label="A", description="a"),
              1: ClusterLabel(cluster=1, id="b", label="B", description="b")}
    tagged = tag_catalogue(catalogue, emb, keys, k=3, n_traits=2, seed=0, labels=labels)
    assert len(tagged.competencies) == 3
    assert "untagged" not in {c.id for c in tagged.competencies}
    assert all(c.traits is not None and len(c.traits) == 2 for c in tagged.competencies)
    mapping = tagged.silo_key_to_competency()
    assert mapping["CHE1A:SILO2"] == mapping["BIO1B:SILO2"]  # lab reports together
    assert mapping["MAT1C:SILO1"] == mapping["MAT1C:SILO2"]
    assert len(set(mapping.values())) == 3
    assert sum(1 for c in tagged.competencies if c.id in {"a", "b"}) == 2  # LLM labels used where given
