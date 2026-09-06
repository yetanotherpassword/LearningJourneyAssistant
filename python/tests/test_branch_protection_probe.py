"""Deliberately failing. Exists only to verify S3-3's acceptance criterion:
a red CI run must block a merge to main. Close the PR once confirmed."""


def test_this_must_fail_to_prove_protection_works() -> None:
    assert False, "deliberate failure -- S3-3 branch-protection verification"
