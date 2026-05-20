"""
test_query.py
-------------
CLI test runner for query_engine.py and csv_generator.py.

Three test modes:

    Level 1 — single known district:
        python backend/test_query.py --district "Kent"

    Level 2 — edge case inputs:
        python backend/test_query.py --edge-cases

    Level 3 — all 174 districts (batch):
        python backend/test_query.py --all

All output CSVs are saved to backend/test_output/.
A summary table is printed to the terminal after each run.
"""

import argparse
import sys
import time
import traceback
from pathlib import Path

# Allow running from repo root: python backend/test_query.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.query_engine  import get_all_districts, search_district
from backend.csv_generator import generate_district_csv

OUTPUT_DIR = Path(__file__).resolve().parent / "test_output"


# ── Formatting helpers ────────────────────────────────────────────────────────

def _currency(n: int) -> str:
    return f"${n:,}"


def _pct(n: float) -> str:
    return f"{n}%"


def _print_summary(result: dict):
    """Pretty-print the summary block for a single district result."""
    d = result["district_name"]
    s = result["summary"]

    print(f"\n{'='*60}")
    print(f"  District: {d}")
    print(f"{'='*60}")

    if not result["found"]:
        print("  ✗ District not found in dataset.")
        return

    print(f"  Schools total:           {s['schools_total']}")
    print(f"  Schools contaminated:    {s['schools_contaminated']}")
    print(f"  Fixtures tested:         {s['fixtures_tested']}")
    print(f"  Fixtures above 5 ppb:    {s['fixtures_contaminated']}  ({_pct(s['pct_fixtures_contaminated'])})")
    print(f"  Testing rounds:          {s['testing_rounds']}")
    print()
    print(f"  Contaminated by type:")
    for ft, count in s["fixtures_above_by_type"].items():
        cost = s["remediation_cost_by_type"].get(ft, 0)
        print(f"    {ft:<25} {count:>5} fixtures   {_currency(cost):>10}")
    print(f"  {'TOTAL REMEDIATION COST':<25}             {_currency(s['remediation_cost_total']):>10}")
    print()
    print(f"  fixture_rows shape: {result['fixture_rows'].shape}")
    print(f"  all_rows shape:     {result['all_rows'].shape}")
    print()


def _print_fixture_sample(result: dict, n: int = 5):
    """Print the first n rows of fixture_rows."""
    if result["fixture_rows"].empty:
        print("  (No contaminated fixtures)")
        return
    cols = ["school_name", "fixture_type", "mean_lead_result_ppb",
            "contamination_status", "DOH_testing_round"]
    print(f"  First {n} contaminated fixture rows:")
    print(result["fixture_rows"][cols].head(n).to_string(index=False))
    print()


# ── Test levels ───────────────────────────────────────────────────────────────

def test_single(district_name: str):
    """Level 1: Run a single district through the full pipeline."""
    print(f"\n[Level 1] Testing district: '{district_name}'")

    t0     = time.time()
    result = search_district(district_name)
    elapsed = time.time() - t0

    _print_summary(result)
    _print_fixture_sample(result)

    if result["found"]:
        csv_path = generate_district_csv(result, output_dir=str(OUTPUT_DIR))
        print(f"  CSV saved: {csv_path}")
        print(f"  Query time: {elapsed:.3f}s")

        # Spot-check: open the CSV and show first few rows
        import pandas as pd
        df = pd.read_csv(csv_path)
        print(f"\n  CSV preview ({len(df)} rows total):")
        print(df.head(8).to_string(index=False))
    else:
        print("  Skipped CSV generation (district not found).")


def test_edge_cases():
    """Level 2: Test known edge cases without fuzzy matching."""
    print("\n[Level 2] Edge case tests")
    print("-" * 50)

    cases = [
        # (input, expect_found, description)
        ("Kent",                True,  "Normal district name"),
        ("Federal Way",         True,  "District with most schools (29)"),
        ("Almira",              True,  "Single-school district"),
        ("Onalaska",            True,  "District with ZERO contaminated fixtures"),
        ("Asotin-Anatone",      True,  "Hyphenated district name"),
        ("Columbia (Walla Walla)", True, "District name with parentheses"),
        ("",                    False, "Empty string"),
        ("NotARealDistrict",    False, "Nonexistent district"),
        ("kent",                False, "Lowercase — should NOT match (exact match expected)"),
    ]

    results = []
    for district_input, expect_found, description in cases:
        result  = search_district(district_input)
        passed  = result["found"] == expect_found
        status  = "✓ PASS" if passed else "✗ FAIL"
        results.append((status, district_input or "(empty)", description, result["found"], expect_found))
        print(f"  {status}  '{district_input or '(empty)'}' → found={result['found']}  | {description}")

    fails = sum(1 for r in results if r[0].startswith("✗"))
    print(f"\n  {len(cases) - fails}/{len(cases)} tests passed.")

    # Generate CSV for the zero-contamination case as a special check
    print("\n  Generating CSV for zero-contamination district (Onalaska)...")
    result = search_district("Onalaska")
    if result["found"]:
        csv_path = generate_district_csv(result, output_dir=str(OUTPUT_DIR))
        import pandas as pd
        df = pd.read_csv(csv_path)
        print(f"  CSV rows: {len(df)}  (should have summary but no fixture detail rows)")
        print(f"  CSV saved: {csv_path}")


def test_all_districts():
    """Level 3: Run every district through the full pipeline and report."""
    print("\n[Level 3] Batch test — all districts")
    print("-" * 50)

    districts = get_all_districts()
    print(f"  Found {len(districts)} districts in dataset.")

    results = []
    errors  = []

    for i, district in enumerate(districts, 1):
        try:
            t0     = time.time()
            result = search_district(district)
            elapsed = time.time() - t0

            if not result["found"]:
                errors.append((district, "search_district returned found=False"))
                continue

            csv_path = generate_district_csv(result, output_dir=str(OUTPUT_DIR))
            s = result["summary"]

            results.append({
                "district":         district,
                "schools":          s["schools_total"],
                "fixtures_tested":  s["fixtures_tested"],
                "contaminated":     s["fixtures_contaminated"],
                "pct":              s["pct_fixtures_contaminated"],
                "cost":             s["remediation_cost_total"],
                "rounds":           str(s["testing_rounds"]),
                "time_ms":          round(elapsed * 1000, 1),
                "csv":              Path(csv_path).name,
            })

            # Progress indicator
            if i % 25 == 0 or i == len(districts):
                print(f"  Progress: {i}/{len(districts)}")

        except Exception as e:
            errors.append((district, str(e)))
            traceback.print_exc()

    # ── Print results table ───────────────────────────────────────────────
    import pandas as pd
    df = pd.DataFrame(results)

    print(f"\n{'='*60}")
    print(f"  BATCH RESULTS: {len(results)}/{len(districts)} districts succeeded")
    print(f"{'='*60}")

    if not df.empty:
        print(f"\n  Top 10 districts by total remediation cost:")
        top = df.nlargest(10, "cost")[["district", "schools", "contaminated", "cost"]]
        top["cost"] = top["cost"].apply(lambda x: f"${x:,.0f}")
        print(top.to_string(index=False))

        print(f"\n  Districts with zero contamination ({(df['contaminated']==0).sum()} total):")
        zero = df[df["contaminated"] == 0]["district"].tolist()
        print("  " + ", ".join(zero))

        print(f"\n  Query speed stats (ms):")
        print(f"    Mean:  {df['time_ms'].mean():.1f}ms")
        print(f"    Max:   {df['time_ms'].max():.1f}ms")
        print(f"    Min:   {df['time_ms'].min():.1f}ms")

        # Save batch summary
        summary_path = OUTPUT_DIR / "_batch_summary.csv"
        df.to_csv(summary_path, index=False)
        print(f"\n  Batch summary saved: {summary_path}")

    if errors:
        print(f"\n  ✗ ERRORS ({len(errors)}):")
        for district, msg in errors:
            print(f"    {district}: {msg}")
    else:
        print(f"\n  ✓ No errors.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Test runner for query_engine + csv_generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backend/test_query.py --district "Kent"
  python backend/test_query.py --district "Federal Way"
  python backend/test_query.py --edge-cases
  python backend/test_query.py --all
        """
    )
    parser.add_argument("--district",    type=str, help="Test a single district by name")
    parser.add_argument("--edge-cases",  action="store_true", help="Run edge case tests")
    parser.add_argument("--all",         action="store_true", help="Batch test all 174 districts")
    parser.add_argument("--list",        action="store_true", help="Print all district names and exit")

    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.list:
        districts = get_all_districts()
        print(f"\n{len(districts)} districts:\n")
        for d in districts:
            print(f"  {d}")
        return

    if args.district:
        test_single(args.district)
    elif args.edge_cases:
        test_edge_cases()
    elif args.all:
        test_all_districts()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()