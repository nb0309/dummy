"""Run-summary metrics.

The primary metric is the legacy file-level summary (a file is "inaccessible" if
any of its captured elements is flagged), ported unchanged so results are
comparable to the old ``testing.py`` run.

Because ``dataset.csv`` already carries a ground-truth ``label`` column, a small
optional read-only breakdown against it is also printed (no dataset changes) so
the run isn't completely blind. This is additive; the file-level number remains
the headline.
"""

from __future__ import annotations

import pandas as pd

# WCAG success criteria the pipeline currently has skills for.
_KNOWN_SC = (
    "1.1.1", "1.2.1", "1.3.1", "1.3.2", "1.3.3", "1.4.1", "2.1.2", "2.4.3",
    "2.4.4", "2.4.6",
    "3.2.1", "3.2.2", "3.3.1", "3.3.2", "4.1.2", "4.1.3",
)


def summarize(output_df: pd.DataFrame) -> None:
    print("\n" + "=" * 50)
    print("       COMPREHENSIVE RUN METRICS SUMMARY")
    print("=" * 50)

    prediction_counts = output_df["Prediction"].value_counts()
    total_elements = len(output_df)
    if total_elements == 0:
        print("No elements processed.")
        return

    accessible_count = int(prediction_counts.get("accessible", 0))
    inaccessible_count = int(prediction_counts.get("inaccessible", 0))
    insufficient_count = int(prediction_counts.get("insufficient_evidence", 0))
    error_count = int(prediction_counts.get("error", 0))

    def pct(n: int) -> str:
        return f"{n} ({n / total_elements * 100:.1f}%)"

    # File-level first: it is the headline, because `label` is stamped per FILE
    # and copied onto every sample the file produced (crawler/lib/rows.js).
    # A file's non-defective elements therefore carry an "inaccessible" label they
    # can never satisfy, which makes the element-level number below a diagnostic
    # rather than a score.
    _file_level(output_df)

    print("-" * 50)
    print("Element-level detail (diagnostic — see the note in _file_level):")
    print(f"Total Evaluated DOM Elements : {total_elements}")
    print(f"[ACCESSIBLE]        : {pct(accessible_count)}")
    print(f"[INACCESSIBLE]      : {pct(inaccessible_count)}")
    print(f"[INSUFFICIENT EVID] : {pct(insufficient_count)}")
    if error_count:
        print(f"[ERRORS]            : {pct(error_count)}")

    _wcag_breakdown(output_df)
    _label_breakdown(output_df)  # optional, read-only vs ground truth
    print("=" * 50)


def _wcag_breakdown(output_df: pd.DataFrame) -> None:
    print("-" * 50)
    print("     WCAG VIOLATION CLASS BREAKDOWN (from reasons)")
    print("-" * 50)
    counts = {sc: 0 for sc in _KNOWN_SC}
    for reason in output_df.get("Reason", []):
        if isinstance(reason, dict):
            for key in reason:
                sc = str(key).strip()
                counts[sc] = counts.get(sc, 0) + 1
    for sc, count in counts.items():
        print(f"Rule Code {sc.ljust(6)} : {count} occurrences flagged")


def _file_level(output_df: pd.DataFrame) -> None:
    """The headline metric: a file is flagged if ANY of its elements is flagged.

    Also lists the files where nothing was flagged. A rate on its own says how
    much is wrong and nothing about what; the named misses are what the next
    iteration is actually worked from.
    """
    print("-" * 50)
    print("FILE-LEVEL VERIFICATION (headline metric)")
    if "source_file" not in output_df.columns:
        print("(no source_file column; skipping file-level summary)")
        return

    flagged = output_df.groupby("source_file")["Prediction"].apply(
        lambda x: "inaccessible" if "inaccessible" in x.values else "accessible"
    )
    total_files = len(flagged)
    failed_files = int((flagged == "inaccessible").sum())
    print(f"Total Unique HTML Test Files Audited : {total_files}")
    print(
        f"Files Flagged with WCAG Violations   : "
        f"{failed_files} ({failed_files / total_files * 100:.1f}%)"
    )
    print(
        f"File-Level Flag Rate                 : "
        f"{failed_files / total_files * 100:.1f}% (Target: 100.0% on this all-inaccessible set)"
    )

    if "label" not in output_df.columns:
        return
    truth = output_df.groupby("source_file")["label"].first()
    missed = sorted(flagged[(truth == "inaccessible") & (flagged == "accessible")].index)
    if missed:
        print(f"\nMISSED — labelled inaccessible, nothing flagged ({len(missed)}):")
        for name in missed:
            print(f"  - {name}")
    false_alarms = sorted(
        flagged[(truth == "accessible") & (flagged == "inaccessible")].index
    )
    if false_alarms:
        print(f"\nFALSE POSITIVES — labelled accessible, flagged ({len(false_alarms)}):")
        for name in false_alarms:
            print(f"  - {name}")


def _label_breakdown(output_df: pd.DataFrame) -> None:
    """Read-only recall vs the existing ``label`` column, if present."""
    if "label" not in output_df.columns:
        return
    print("-" * 50)
    print("Ground-truth check (read-only, vs `label` column):")
    print(
        "  NOTE: `label` is per-FILE, copied onto every element that file produced. "
        "An element that is itself fine inside a defective page carries an "
        "'inaccessible' label it cannot satisfy, so treat the numbers below as a "
        "diagnostic and the file-level rate above as the score."
    )
    labels = output_df["label"].astype(str).str.lower()
    preds = output_df["Prediction"].astype(str).str.lower()

    truly_inaccessible = int((labels == "inaccessible").sum())
    truly_accessible = int((labels == "accessible").sum())
    # An "insufficient_evidence" prediction is neither a catch nor a miss.
    caught = int(((labels == "inaccessible") & (preds == "inaccessible")).sum())
    missed = int(((labels == "inaccessible") & (preds == "accessible")).sum())
    abstained = int(((labels == "inaccessible") & (preds == "insufficient_evidence")).sum())

    print(f"  labelled inaccessible: {truly_inaccessible} | labelled accessible: {truly_accessible}")
    if truly_inaccessible:
        print(
            f"  Recall on inaccessible: {caught}/{truly_inaccessible} "
            f"({caught / truly_inaccessible * 100:.1f}%) "
            f"| missed (said accessible): {missed} | abstained: {abstained}"
        )
    if truly_accessible:
        fp = int(((labels == "accessible") & (preds == "inaccessible")).sum())
        print(f"  False positives on accessible: {fp}/{truly_accessible}")
