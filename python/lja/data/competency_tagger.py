"""Group a catalogue's SILOs into competencies with embeddings (IOLG-113).

    cd python
    python -m lja.data.competency_tagger ../data-fixtures/handbook/catalogue_raw.yaml \
        --out ../data-fixtures/handbook/catalogue.yaml --k 40

Why embeddings and not the LLM clustering call: cluster_silos() asks one
chat completion to partition every SILO at once and validates coverage; it
fails at 52 SILOs on the local 30B model and hundreds is hopeless. Grouping
sentences by meaning is what embedding vectors are for, and k-means over
them is seconds of numpy. The LLM is still used, but only for the one job
it is good at here: giving each cluster a human label and description, in a
few batched calls. Without an LLM the clusters get keyword labels.

Two outputs per competency:

- `id`/`label`/`description` -- the competency the generator, the gap
  detector (through the ground-truth clustering) and the Moodle framework
  CSVs all use.
- `traits` -- loadings onto a small number of latent aptitude axes, from a
  PCA of the cluster centroids. Competencies near each other in meaning get
  similar loadings, so the generator can make a student who is strong in
  one quantitative competency tend to be strong in the others. That is the
  "excel in differing areas" the cohort is supposed to show.

These clusters are the cohort's ground truth BY CONSTRUCTION -- the
generator makes students consistent with them -- so their job is to be
coherent and reviewable, not to be the one true competency map of the
university. Look at the printed table; re-run with a different --k if a
cluster is obviously two things.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict

from .catalogue import Catalogue, load_catalogue, save_catalogue

_STOP = set(
    "a an the and or of to in for on with by from as at into through using use apply applying be is are this that "
    "their its own about which such between within across including both each other than more most also how what "
    "will can should key range variety basic advanced relevant appropriate different various specific general".split()
)


# -- k-means over unit vectors (cosine) ---------------------------------------


def _normalise(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.where(norms == 0, 1.0, norms)


def _kmeans_pp_init(x: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    n = x.shape[0]
    centres = [x[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min(((x[:, None, :] - np.array(centres)[None, :, :]) ** 2).sum(-1), axis=1)
        probs = d2 / d2.sum() if d2.sum() > 0 else np.full(n, 1.0 / n)
        centres.append(x[rng.choice(n, p=probs)])
    return np.array(centres)


def kmeans(x: np.ndarray, k: int, *, seed: int = 0, restarts: int = 4, iters: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Returns (labels, centres). Spherical k-means: inputs are unit vectors,
    centres are re-normalised each step, assignment is by cosine."""
    x = _normalise(x)
    best: tuple[float, np.ndarray, np.ndarray] | None = None
    for r in range(restarts):
        rng = np.random.default_rng(seed + r)
        centres = _kmeans_pp_init(x, k, rng)
        labels = np.zeros(x.shape[0], dtype=int)
        for _ in range(iters):
            sims = x @ centres.T
            new_labels = sims.argmax(axis=1)
            if np.array_equal(new_labels, labels) and _ > 0:
                break
            labels = new_labels
            for c in range(k):
                members = x[labels == c]
                if len(members):
                    centres[c] = members.mean(axis=0)
                else:  # re-seed an empty cluster from the worst-fit point
                    centres[c] = x[sims.max(axis=1).argmin()]
            centres = _normalise(centres)
        inertia = float((1.0 - (x @ centres.T).max(axis=1)).sum())
        if best is None or inertia < best[0]:
            best = (inertia, labels.copy(), centres.copy())
    assert best is not None
    return best[1], best[2]


def pca_loadings(centres: np.ndarray, n_traits: int) -> np.ndarray:
    """Each centre projected onto the top principal axes, then unit-normalised
    per competency so loading . N(0, I) traits is N(0, 1)."""
    n_traits = max(1, min(n_traits, centres.shape[0] - 1, centres.shape[1]))
    centred = centres - centres.mean(axis=0, keepdims=True)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    proj = centred @ vt[:n_traits].T
    return _normalise(proj)


# -- labels ---------------------------------------------------------------------


class ClusterLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster: int
    id: str
    label: str
    description: str


class ClusterLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    labels: list[ClusterLabel]


_LABEL_PROMPT = """You are naming competencies for a university learning-analytics tool. Each cluster below \
is a group of subject intended learning outcomes (SILOs) from different subjects that were grouped together \
because they describe the same underlying capability.

For EVERY cluster, return: its cluster number; a short kebab-case id (2-4 words, e.g. "quantitative-modelling"); \
a label of at most 8 words; and a one-sentence description of the capability. Name what the outcomes have in \
common, not any one subject. Ids must be unique across clusters. Australian English.
"""


def keyword_label(texts: list[str], k: int = 3) -> str:
    words = Counter(
        w for t in texts for w in re.findall(r"[a-z][a-z\-]{2,}", t.lower()) if w not in _STOP
    )
    top = [w for w, _ in words.most_common(k)]
    return " / ".join(top) if top else "unlabelled"


def label_clusters(members: dict[int, list[str]], client, *, batch: int = 20) -> dict[int, ClusterLabel]:
    out: dict[int, ClusterLabel] = {}
    ids = sorted(members)
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        lines = []
        for c in chunk:
            lines.append(f"Cluster {c} ({len(members[c])} outcomes):")
            lines.extend(f"  - {t}" for t in members[c][:8])
        try:
            result = client.complete_structured(system=_LABEL_PROMPT, user="\n".join(lines), schema=ClusterLabels)
        except Exception as exc:  # noqa: BLE001 -- keep going with keyword labels for this batch
            print(f"  label call failed for clusters {chunk[0]}-{chunk[-1]}: {exc}", file=sys.stderr)
            continue
        for lab in result.labels:
            if lab.cluster in chunk:
                out[lab.cluster] = lab
    return out


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "competency"


# -- main -----------------------------------------------------------------------


def tag_catalogue(
    catalogue: Catalogue,
    embeddings: np.ndarray,
    silo_keys: list[str],
    *,
    k: int,
    n_traits: int,
    seed: int,
    labels: dict[int, ClusterLabel] | None,
) -> Catalogue:
    labels_arr, centres = kmeans(embeddings, k, seed=seed)
    loadings = pca_loadings(centres, n_traits)
    key_to_cluster = dict(zip(silo_keys, labels_arr.tolist()))
    texts_by_cluster: dict[int, list[str]] = defaultdict(list)
    text_by_key = {f"{s.code}:{silo.id}": silo.text for s in catalogue.subjects for silo in s.silos}
    for key, c in key_to_cluster.items():
        texts_by_cluster[c].append(text_by_key[key])

    data = catalogue.model_dump(mode="json", exclude_none=True)
    used_ids: set[str] = set()
    comp_id_by_cluster: dict[int, str] = {}
    competencies = []
    for c in range(k):
        if c not in texts_by_cluster:
            continue
        lab = labels.get(c) if labels else None
        cid = _slug(lab.id) if lab else f"comp-{c:02d}-{_slug(keyword_label(texts_by_cluster[c]))}"
        while cid in used_ids:
            cid += "-x"
        used_ids.add(cid)
        comp_id_by_cluster[c] = cid
        competencies.append(
            {
                "id": cid,
                "label": lab.label if lab else keyword_label(texts_by_cluster[c]),
                "description": lab.description if lab else f"Embedding cluster {c}: {len(texts_by_cluster[c])} SILOs.",
                "traits": [round(float(v), 4) for v in loadings[c]],
            }
        )
    data["competencies"] = competencies
    for subject in data["subjects"]:
        for silo in subject["silos"]:
            silo["competency"] = comp_id_by_cluster[key_to_cluster[f"{subject['code']}:{silo['id']}"]]
    data["title"] = re.sub(r",? ?competencies untagged", "", data.get("title", "")) or data.get("title", "")
    return Catalogue.model_validate(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tag catalogue SILOs with embedding-derived competencies (IOLG-113)")
    parser.add_argument("catalogue")
    parser.add_argument("--out", required=True)
    parser.add_argument("--k", type=int, default=None, help="Number of competencies (default: SILOs/10, clamped to 8..60)")
    parser.add_argument("--traits", type=int, default=4, help="Latent aptitude axes for the ability model")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-llm-labels", action="store_true", help="Keyword labels only; no chat-model call")
    parser.add_argument("--embeddings-cache", default=None, help=".npy cache for the SILO embeddings (default: beside --out)")
    args = parser.parse_args(argv)

    catalogue = load_catalogue(args.catalogue)
    silo_keys = [f"{s.code}:{silo.id}" for s in catalogue.subjects for silo in s.silos]
    texts = [silo.text for s in catalogue.subjects for silo in s.silos]
    k = args.k or max(8, min(60, len(texts) // 10))
    print(f"{len(catalogue.subjects)} subjects, {len(texts)} SILOs -> {k} competencies, {args.traits} traits")

    cache = Path(args.embeddings_cache) if args.embeddings_cache else Path(args.out).with_suffix(".embeddings.npy")
    digest = hashlib.sha256("\n".join(texts).encode()).hexdigest()[:16]
    meta = cache.with_suffix(".sha")
    if cache.exists() and meta.exists() and meta.read_text().strip() == digest:
        embeddings = np.load(cache)
        print(f"Loaded cached embeddings from {cache}")
    else:
        from ..llm.embeddings import EmbeddingClient

        client = EmbeddingClient()
        print(f"Embedding with {client.describe()} ...")
        embeddings = np.array(client.embed(texts), dtype=np.float32)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache, embeddings)
        meta.write_text(digest)
        print(f"  {client.usage_summary()}; cached to {cache}")

    labels: dict[int, ClusterLabel] | None = None
    if not args.no_llm_labels:
        from ..llm.factory import get_llm_client

        chat = get_llm_client()
        print(f"Labelling clusters with {chat.describe()} ...")
        prelim, _ = kmeans(embeddings, k, seed=args.seed)
        members: dict[int, list[str]] = defaultdict(list)
        for t, c in zip(texts, prelim.tolist()):
            members[c].append(t)
        labels = label_clusters(members, chat)
        print(f"  {len(labels)}/{k} clusters labelled by the model; {chat.usage_summary()}")

    tagged = tag_catalogue(catalogue, embeddings, silo_keys, k=k, n_traits=args.traits, seed=args.seed, labels=labels)
    save_catalogue(tagged, args.out)

    per_comp_subjects = tagged.competency_subjects()
    per_comp_silos = Counter(tagged.silo_key_to_competency().values())
    print(f"\nWrote {args.out}")
    print(f"{'competency':<42} {'silos':>5} {'subjects':>8}  label")
    for c in tagged.competencies:
        print(f"{c.id:<42} {per_comp_silos[c.id]:>5} {len(per_comp_subjects[c.id]):>8}  {c.label}")
    single = [c.id for c in tagged.competencies if len(per_comp_subjects[c.id]) < 2]
    print(f"\n{len(tagged.competencies) - len(single)} competencies span 2+ subjects; {len(single)} are single-subject.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
