"""Unit tests for lja.dashboard.stats -- pure arithmetic over plain lists of
floats, so they need no dataset, no app and no TestClient. Separated from
test_dashboard.py for the same reason test_gap_detection.py is separate from
the loader tests: this module's job is computation and should be testable as
computation.

Every expected value below is hand-calculated in the test's own docstring
rather than copied from a run. A test that asserts whatever the code printed
the first time only detects change, not incorrectness.
"""

from __future__ import annotations

import pytest

from lja.dashboard.stats import histogram, summarise


def test_summarise_over_a_known_four_point_cohort() -> None:
    """Values [10, 20, 30, 40].

    mean     = (10+20+30+40)/4 = 100/4 = 25
    median   = midpoint of the two central values = (20+30)/2 = 25
    variance = POPULATION variance, divisor n not n-1:
               deviations -15, -5, 5, 15 -> squares 225, 25, 25, 225 = 500
               500/4 = 125
    stdev    = sqrt(125) = 11.1803... -> 11.18 at 2dp
    quartiles are the 'inclusive' method: linear interpolation at position
               (n-1)*p over the sorted values, so with n=4:
               Q1 at 3*0.25 = 0.75 -> 10 + 0.75*(20-10) = 17.5
               Q3 at 3*0.75 = 2.25 -> 30 + 0.25*(40-30) = 32.5
    IQR      = 32.5 - 17.5 = 15
    """
    stats = summarise([10.0, 20.0, 30.0, 40.0])

    assert stats.n == 4
    assert stats.mean == 25.0
    assert stats.median == 25.0
    assert stats.variance == 125.0
    assert stats.stdev == 11.18
    assert stats.minimum == 10.0
    assert stats.maximum == 40.0
    assert stats.q1 == 17.5
    assert stats.q3 == 32.5
    assert stats.iqr == 15.0


def test_variance_is_population_not_sample() -> None:
    """The one that pins the Bessel-correction decision down.

    Values [10, 20, 30, 40]: population variance is 500/4 = 125, sample
    variance would be 500/3 = 166.67. A cohort is every student it describes,
    not a sample drawn from a larger body, so 125 is the intended answer --
    and this test exists so that switching to statistics.variance() fails
    loudly rather than quietly shifting every figure on the dashboard.
    """
    assert summarise([10.0, 20.0, 30.0, 40.0]).variance == 125.0


def test_single_student_has_zero_spread_but_no_quartiles() -> None:
    """One value is enough to have a mean and a spread of exactly nothing,
    but not enough to have quartiles. Reporting 0.0 for a quartile would be
    a fabricated figure; None renders as an em dash instead.
    """
    stats = summarise([50.0])

    assert stats.n == 1
    assert stats.mean == 50.0
    assert stats.median == 50.0
    assert stats.variance == 0.0
    assert stats.stdev == 0.0
    assert stats.q1 is None
    assert stats.q3 is None
    assert stats.iqr is None


def test_empty_cohort_reports_nothing_rather_than_zero() -> None:
    """An empty cohort has no mean. The distinction between "the average is
    zero" and "there is no average" is the whole reason these fields are
    optional -- a dashboard that prints 0.0% here is stating something false.
    """
    stats = summarise([])

    assert stats.n == 0
    assert stats.mean is None
    assert stats.median is None
    assert stats.variance is None
    assert stats.minimum is None
    assert stats.maximum is None
    assert stats.iqr is None


def test_histogram_bins_are_fixed_regardless_of_the_data() -> None:
    """Two cohorts must be visually comparable, so bins come from the 0-100
    range and not from the cohort's own min/max. A cohort spanning 60-70 still
    gets ten bins across the full range, nine of them empty.
    """
    bins = histogram([61.0, 62.0, 69.0])

    assert len(bins) == 10
    assert [b.label for b in bins][:3] == ["0-10", "10-20", "20-30"]
    assert sum(b.count for b in bins) == 3
    assert next(b for b in bins if b.label == "60-70").count == 3


def test_histogram_bin_boundaries_and_the_closed_top() -> None:
    """Values [0, 5, 10, 99, 100] across ten bins of width 10.

    0   -> 0//10  = bin 0   ([0,10) is half-open at the top)
    5   -> 5//10  = bin 0
    10  -> 10//10 = bin 1   (a boundary value belongs to the bin it opens)
    99  -> 99//10 = bin 9
    100 -> 100//10 = 10, clamped down to bin 9, because the top bin is closed
           at both ends so a perfect score is counted rather than dropped.

    Expected: bin 0 = 2, bin 1 = 1, bin 9 = 2, everything else 0.
    """
    bins = histogram([0.0, 5.0, 10.0, 99.0, 100.0])
    counts = {b.label: b.count for b in bins}

    assert counts["0-10"] == 2
    assert counts["10-20"] == 1
    assert counts["90-100"] == 2
    assert sum(b.count for b in bins) == 5


def test_histogram_clamps_out_of_range_values_instead_of_dropping_them() -> None:
    """A negative or >100 value is almost certainly a data problem, but
    silently vanishing off the edge of a chart is worse than a slightly
    overfull end bar -- the count must still reconcile with the cohort size.
    """
    bins = histogram([-20.0, 130.0])

    assert sum(b.count for b in bins) == 2
    assert bins[0].count == 1
    assert bins[-1].count == 1


def test_histogram_rejects_a_non_positive_bin_width() -> None:
    with pytest.raises(ValueError, match="bin_width must be positive"):
        histogram([50.0], bin_width=0)
