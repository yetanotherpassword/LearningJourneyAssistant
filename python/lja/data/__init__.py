from .excel_loader import Assessment, LjaDataset, ResultRow, Silo, StudentSummary, load_dataset

__all__ = ["Assessment", "LjaDataset", "ResultRow", "Silo", "StudentSummary", "load_dataset"]

# synth_generator is deliberately NOT re-exported here. It's also run
# directly as `python -m lja.data.synth_generator` (see its --help); eagerly
# importing it into this package's namespace makes Python import it twice
# (once via this __init__, once as __main__) and print a RuntimeWarning
# about unpredictable behaviour. Import it explicitly where needed instead:
# `from lja.data.synth_generator import generate_synthetic_students`.
