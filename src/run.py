"""Entrypoint: classify every element in the dataset with the skill-based agent.

Usage
-----
    python -m src.run                      # full run against dataset.csv
    python -m src.run --dry-run            # no API: route + build evidence only
    python -m src.run --limit 5            # process only the first 5 rows
    python -m src.run --input other.csv --output preds.csv

``--dry-run`` is the cheap verification path: it exercises routing + evidence
formatting over every row and asserts each element gets at least one skill,
without spending any tokens.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import List

import pandas as pd

from . import config, evidence, router


def _log(log_path: Path, sample_id, payload: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 80}\n[{ts}] SAMPLE: {sample_id}\n{payload}\n")


def dry_run(df: pd.DataFrame) -> int:
    """Route + build evidence for every row; report coverage. No LLM."""
    print(f"DRY RUN — routing + evidence over {len(df)} rows (no API calls)\n")
    uncovered = 0
    for _, row in df.iterrows():
        ev = evidence.build(row)
        skills = router.select(ev, row)
        skill_ids = [s.id for s in skills]
        if not skill_ids:
            uncovered += 1
        print(
            f"{str(row.get('sample_id','?'))[:52]:54} "
            f"tag=<{ev.element_tag or '?'}> -> {skill_ids}"
        )

    print("\n--- coverage ---")
    print(f"rows with NO applicable skill : {uncovered}")
    if uncovered:
        print("FAIL: some rows have no skill.")
        return 1
    print("OK: every row routed to >=1 skill.")
    return 0


def full_run(df: pd.DataFrame, output_csv: Path, log_path: Path) -> None:
    # Imported lazily so --dry-run needs no LLM credentials.
    from . import classifier
    from .llm import load_structured_llm

    structured_llm = load_structured_llm()
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Skill-based run started {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")

    processed: List[dict] = []
    for index, row in df.iterrows():
        sample_id = row.get("sample_id")
        ev = evidence.build(row)
        primary, secondary = router.partition(ev, row)
        skills = primary + secondary
        print(
            f"[{index}] {str(row.get('sample_id','?'))[:48]} "
            f"-> {[s.id for s in primary]} + {[s.id for s in secondary]}"
        )
        try:
            pred = classifier.classify(structured_llm, ev, primary, secondary)
            prediction = pred.classification
            reason = pred.reason
            _log(log_path, sample_id, pred.model_dump_json(indent=2))
        except Exception as exc:  # noqa: BLE001 - record and continue
            print(f"   ! error: {exc}")
            prediction = "error"
            reason = {"error": str(exc)}
            pred = None
            _log(log_path, sample_id, f"ERROR: {exc}")

        print(f"   -> {prediction} {reason if reason else ''}")

        record = row.to_dict()
        record["Prediction"] = prediction
        record["Reason"] = reason if reason else None
        record["Confidence"] = getattr(pred, "confidence", None)
        record["EvidenceCitation"] = getattr(pred, "evidence_citation", None)
        record["AppliedSkills"] = ", ".join(s.id for s in skills)
        processed.append(record)

    output_df = pd.DataFrame(processed)
    output_df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"\nSaved predictions to: {output_csv}")

    from . import metrics
    metrics.summarize(output_df)


def main(argv: List[str] | None = None) -> int:
    # Windows consoles default to cp1252; captured phrases and box-drawing may
    # contain characters outside it. Prefer UTF-8 and never crash on output.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="Skill-based WCAG classifier")
    parser.add_argument("--input", default=str(config.DEFAULT_INPUT_CSV))
    parser.add_argument("--output", default=str(config.DEFAULT_OUTPUT_CSV))
    parser.add_argument("--limit", type=int, default=None, help="process first N rows")
    parser.add_argument("--dry-run", action="store_true", help="route+evidence only, no API")
    args = parser.parse_args(argv)

    input_csv = Path(args.input)
    if not input_csv.exists():
        raise FileNotFoundError(f"Missing input CSV: {input_csv}")

    df = pd.read_csv(input_csv)
    if args.limit:
        df = df.head(args.limit)
    print(f"Loaded {len(df)} rows from {input_csv}")

    if args.dry_run:
        return dry_run(df)

    full_run(df, Path(args.output), config.DEFAULT_LOG_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
