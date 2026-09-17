"""Descriptive statistics over a cohort of students, plus the binning the
dashboard's distribution chart needs.

Lives under dashboard/ rather than model/ on purpose. This is presentation
summarisation over StudentSummary.average_total -- a whole-student figure the
Excel loader already computed -- not a pipeline stage. Nothing here
classifies anything and nothing here carries a threshold, which is also
deliberate: what counts as an "at risk" cohort is an open team decision
(Sprint 3 runbook, Sec 9 -- Scott confirmed there is no institutional number
to match), and this module must not pre-empt that decision by quietly
baking in a cut-off. Cohort membership is decided by the caller and passed
in already filtered.

**Population statistics, not sample statistics** -- pvariance/pstdev rather
than variance/stdev. A cohort here is every student we hold, not a sample
drawn from some larger body, so the n-1 Bessel correction would be
correcting for an inference nobody is making. Report the spread of the group
in front of us. If cohorts ever become genuine samples of a wider student
population, this is the line to revisit, and the difference is visible at
n=150 but not large.

On median: this uses statistics.median from the standard library rather than
a hand-rolled one. WP2 (relative gap detection) is about to introduce median
and MAD over each student's *competency profile* -- a different population
to this module's "students within one cohort" -- but there should still be
exactly one median implementation in this codebase, and the standard library
is the obvious candidate. If WP2 needs a MAD helper, it belongs beside that
median, not as a second private implementation.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class CohortStats:
    """Every field is None when it is genuinely undefined for the input --
    an empty cohort has no mean, and quartiles need at least two points.
    Rendering "0.0" for "we cannot say" is how a dashboard starts lying, so
    the templates check for None and print an em dash instead.
    """

    n: int
    mean: float | None
    median: float | None
    variance: float | None
    stdev: float | None
    minimum: float | None
    maximum: float | None
    q1: float | None
    q3: float | None

    @property
    def iqr(self) -> float | None:
        if self.q1 is None or self.q3 is None:
            return None
        return round(self.q3 - self.q1, 2)


@dataclass(frozen=True)
class HistogramBin:
    lower: float
    upper: float
    count: int

    @property
    def label(self) -> str:
        # Integer bounds read better on an axis than "60.0-70.0", and every
        # caller so far bins percentages on whole numbers.
        return f"{self.lower:g}-{self.upper:g}"


def summarise(values: list[float]) -> CohortStats:
    """Descriptive statistics over one cohort's values, rounded for display.

    Rounding here rather than in the template because these numbers are also
    handed to Chart.js as JSON, and a chart axis and a table cell disagreeing
    in the last decimal place is the kind of thing that costs an afternoon.
    """
    n = len(values)
    if n == 0:
        return CohortStats(
            n=0, mean=None, median=None, variance=None, stdev=None,
            minimum=None, maximum=None, q1=None, q3=None,
        )

    # Population variance of a single point is 0.0, which is true and not
    # misleading. Quartiles of a single point are not defined at all.
    quartiles = statistics.quantiles(values, n=4, method="inclusive") if n >= 2 else None

    return CohortStats(
        n=n,
        mean=round(statistics.fmean(values), 2),
        median=round(statistics.median(values), 2),
        variance=round(statistics.pvariance(values), 2),
        stdev=round(statistics.pstdev(values), 2),
        minimum=round(min(values), 2),
        maximum=round(max(values), 2),
        q1=round(quartiles[0], 2) if quartiles else None,
        q3=round(quartiles[2], 2) if quartiles else None,
    )


def histogram(values: list[float], *, lower: float = 0.0, upper: float = 100.0, bin_width: float = 10.0) -> list[HistogramBin]:
    """Fixed-width bins across a fixed range, not data-derived bins.

    Fixed on purpose: two cohorts viewed one after the other must have
    comparable x-axes, and bins computed from each cohort's own min/max
    would silently rescale between pages -- making a strong cohort and a weak
    one look identically shaped. Values are percentages, so 0-100 in tens is
    the natural frame regardless of who is in the cohort.

    The top bin is closed at both ends so a student on exactly 100 is
    counted; every other bin is [lower, upper). Values outside the range are
    clamped into the end bins rather than dropped -- losing a student off the
    edge of a chart is worse than a slightly overfull first or last bar.
    """
    if bin_width <= 0:
        raise ValueError(f"bin_width must be positive, got {bin_width}")

    edges: list[float] = []
    edge = lower
    while edge < upper:
        edges.append(edge)
        edge += bin_width

    counts = [0] * len(edges)
    for value in values:
        clamped = min(max(value, lower), upper)
        index = int((clamped - lower) // bin_width)
        index = min(index, len(counts) - 1)  # value == upper lands in the top bin
        counts[index] += 1

    return [
        HistogramBin(lower=edge, upper=min(edge + bin_width, upper), count=count)
        for edge, count in zip(edges, counts, strict=True)
    ]
