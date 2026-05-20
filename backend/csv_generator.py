"""
csv_generator.py
----------------
Generates a downloadable CSV report for a single school district,
using the result dict returned by query_engine.search_district().

Primary function:
    generate_district_csv(result, output_dir)  → path to saved .csv file

The output CSV has two sections:
    1. Fixture Detail — one row per school × fixture_type × testing_round
       (only contaminated fixtures, i.e. contamination_status == "Contaminated")
    2. District Summary — appended at the bottom after a blank row

Usage:
    from backend.query_engine   import search_district
    from backend.csv_generator  import generate_district_csv

    result   = search_district("Kent")
    csv_path = generate_district_csv(result, output_dir="exports/")
    # → "exports/Kent_lead_report.csv"
"""

import os
import re
import pandas as pd
from pathlib import Path
from datetime import datetime

# Unit costs mirror query_engine.UNIT_COSTS — keep in sync with project_config.txt
# TODO: UPDATE THIS TO BE MORE ACCURATE WITH REAL-WORLD COSTS PER FIXTURE TYPE
UNIT_COSTS = {
    "Tap/Sink":               600,
    "Water Fountain":        1500,
    "Bottle Refill Station": 1500,
    "Water Cooler":           800,
    "Ice Machine/Fridge":     800,
    "Pot Filler":             600,
    "Sprayer/Hose":           400,
    "Other":                  600,
}

CONTAMINATION_THRESHOLD_PPB = 5


def _safe_filename(name: str) -> str:
    """Converts a district name to a safe filename string."""
    return re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")


def generate_district_csv(result: dict, output_dir: str = "exports") -> str:
    """
    Generates a CSV report for a district and saves it to output_dir.

    Args:
        result:     The dict returned by query_engine.search_district()
        output_dir: Directory to save the file (created if it doesn't exist)

    Returns:
        Absolute path to the saved CSV file.

    Raises:
        ValueError: If result["found"] is False (district not in dataset)
    """
    if not result.get("found"):
        raise ValueError(
            f"District '{result.get('district_name')}' was not found in the dataset. "
            f"Cannot generate CSV."
        )

    district_name = result["district_name"]
    summary       = result["summary"]
    fixture_rows  = result["fixture_rows"]   # contaminated rows only

    # ── Build fixture detail table ────────────────────────────────────────────
    # Group by school × fixture_type × testing_round
    # Each row = one school's contaminated fixtures of a given type in a given year

    if fixture_rows.empty:
        # District has no contaminated fixtures — still produce a CSV, just empty detail
        detail_df = pd.DataFrame(columns=[
            "school_name", "fixture_type", "fixture_location",
            "fixtures_above_5ppb", "avg_lead_ppb", "year_sampled",
            "unit_replacement_cost_usd", "total_estimated_cost_usd",
        ])
    else:
        grouped = (
            fixture_rows
            .groupby(["school_name", "fixture_type", "DOH_testing_round"], sort=True)
            .agg(
                fixtures_above_5ppb   = ("contamination_status", "count"),
                avg_lead_ppb          = ("mean_lead_result_ppb", "mean"),
                fixture_location      = (
                    "fixture_housing_location",
                    # Collapse multiple location strings into one readable cell
                    lambda x: " | ".join(
                        loc.strip().strip(";")
                        for loc in x.dropna().unique()
                        if loc.strip().strip(";")
                    )
                ),
            )
            .reset_index()
        )

        grouped["avg_lead_ppb"] = grouped["avg_lead_ppb"].round(1)

        # Look up unit cost for each fixture type
        grouped["unit_replacement_cost_usd"] = grouped["fixture_type"].map(
            lambda ft: UNIT_COSTS.get(ft, UNIT_COSTS["Other"])
        )

        # Total cost = unit cost × number of contaminated fixtures
        grouped["total_estimated_cost_usd"] = (
            grouped["unit_replacement_cost_usd"] * grouped["fixtures_above_5ppb"]
        )

        # Rename and reorder columns for the output
        detail_df = grouped.rename(columns={
            "school_name":       "school_name",
            "fixture_type":      "fixture_type",
            "fixture_location":  "fixture_location",
            "DOH_testing_round": "year_sampled",
        })[[
            "school_name",
            "fixture_type",
            "fixture_location",
            "fixtures_above_5ppb",
            "avg_lead_ppb",
            "year_sampled",
            "unit_replacement_cost_usd",
            "total_estimated_cost_usd",
        ]]

    # ── Build district summary rows ───────────────────────────────────────────
    # Appended at the bottom of the CSV after a blank separator row

    summary_rows = []

    summary_rows.append({
        "school_name":               "DISTRICT SUMMARY",
        "fixture_type":              "",
        "fixture_location":          "",
        "fixtures_above_5ppb":       "",
        "avg_lead_ppb":              "",
        "year_sampled":              "",
        "unit_replacement_cost_usd": "",
        "total_estimated_cost_usd":  "",
    })

    meta_items = [
        ("District",                   district_name),
        ("Testing Round(s)",           ", ".join(str(r) for r in summary["testing_rounds"])),
        ("Total Schools in District",  summary["schools_total"]),
        ("Schools with Contamination", summary["schools_contaminated"]),
        ("Total Fixtures Tested",      summary["fixtures_tested"]),
        ("Fixtures Above 5 ppb",       summary["fixtures_contaminated"]),
        ("% Fixtures Contaminated",    f"{summary['pct_fixtures_contaminated']}%"),
        ("",                           ""),
        ("--- Remediation Costs ---",  ""),
    ]

    # Add per-type cost breakdown
    for fixture_type, cost in summary["remediation_cost_by_type"].items():
        count     = summary["fixtures_above_by_type"].get(fixture_type, 0)
        unit_cost = UNIT_COSTS.get(fixture_type, UNIT_COSTS["Other"])
        meta_items.append((
            f"  {fixture_type} ({count} fixtures × ${unit_cost:,})",
            f"${cost:,}"
        ))

    meta_items.append(("TOTAL REMEDIATION COST ESTIMATE", f"${summary['remediation_cost_total']:,}"))
    meta_items.append(("", ""))
    meta_items.append((
        "Note",
        "Cost estimates cover material replacement only. "
        "Labor, inspection, and disposal costs are not included."
    ))
    meta_items.append(("Report Generated", datetime.now().strftime("%Y-%m-%d %H:%M")))
    meta_items.append(("Data Source", "WA DOH Lead in School Drinking Water Program (doh.wa.gov)"))

    for label, value in meta_items:
        summary_rows.append({
            "school_name":               label,
            "fixture_type":              value,
            "fixture_location":          "",
            "fixtures_above_5ppb":       "",
            "avg_lead_ppb":              "",
            "year_sampled":              "",
            "unit_replacement_cost_usd": "",
            "total_estimated_cost_usd":  "",
        })

    summary_df = pd.DataFrame(summary_rows)

    # ── Combine detail + blank separator + summary ────────────────────────────
    blank_row = pd.DataFrame([{col: "" for col in detail_df.columns}])
    final_df  = pd.concat([detail_df, blank_row, summary_df], ignore_index=True)

    # ── Save ──────────────────────────────────────────────────────────────────
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(district_name)
    filename  = output_path / f"{safe_name}_lead_report.csv"

    final_df.to_csv(filename, index=False)

    return str(filename.resolve())