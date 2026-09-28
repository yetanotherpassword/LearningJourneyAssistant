# ADR 0002 — No-Embedding SILO Clustering

**Status:** Accepted  
**Date:** 2026-09-20  
**Work item:** IOLG-109  

## Context

The Learning Journey Assistant needs to identify semantically related Subject Intended Learning Outcomes (SILOs) across different subjects.

An embedding-based approach was considered, where SILO text would first be converted to vector embeddings and then compared using similarity measures such as cosine similarity.

For the current project scope, the team instead uses direct LLM-based semantic clustering.

## Decision

Use direct LLM semantic clustering of SILO text without a separate embedding or vector-similarity stage.

The LLM receives the SILOs from all subjects and groups outcomes that represent the same underlying competency.

## Reasons

- The current SILO dataset is small enough to compare directly in the LLM prompt.
- Direct semantic reasoning can identify relationships even when SILOs use different wording.
- The clustering pipeline is already implemented and integrated with the gap-detection workflow.
- Avoiding embeddings keeps the architecture simpler by removing an additional embedding model, vector store, similarity threshold, and retrieval stage.
- The clustering output is validated before downstream use.

## Stability and validation evidence

Live testing showed that LLM clustering can vary between runs.

Observed behaviour included:

- smaller models grouping SILOs mainly by subject rather than by shared competency;
- a stronger model producing meaningful cross-subject clustering;
- one run omitting SILOs even though another run with the same model produced complete coverage.

Because of this variation, the system validates every clustering result before use.

The grounding validator checks that:

- every SILO from the input appears in the clustering;
- no unknown SILO is introduced;
- no SILO is duplicated across clusters.

If validation fails, clustering is retried and the validation error is supplied to the model.

Staff review is also required before AI-generated clustering should be relied on for downstream student-facing outputs.

## Tender deviation

This decision documents the project's deviation from an embedding-based implementation option described in the tender.

The required semantic matching is still performed, but through direct LLM reasoning rather than embedding similarity.

## Alternatives considered

### Embeddings and cosine similarity

This would provide a deterministic similarity stage and could scale better when the number of SILOs becomes much larger.

It was not selected for the current implementation because it would add architectural complexity without a demonstrated need at the current dataset size.

### Keyword matching

Keyword matching was rejected because SILOs may express the same competency using substantially different wording.

## Consequences

Positive consequences:

- simpler architecture;
- fewer external components;
- direct cross-subject semantic reasoning;
- easier integration with the existing LLM layer.

Trade-offs:

- LLM outputs can vary between runs;
- clustering quality depends on model capability and prompt quality;
- validation, retries, and staff review are necessary controls.

## Future review

The team should reconsider embeddings if:

- the number of SILOs grows substantially;
- LLM prompt size or latency becomes problematic;
- clustering consistency remains inadequate;
- a deterministic candidate-generation stage is needed before LLM review.
