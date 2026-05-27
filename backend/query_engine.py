"""
query_engine.py
---------------
Core data engine for the WA School Lead Testing project.

Primary functions:
    get_all_districts()        → sorted list of all district names (for dropdown)
    search_district(name)      → full result dict for one district

Usage:
    from backend.query_engine import get_all_districts, search_district

    districts = get_all_districts()          # populate the dropdown
    result    = search_district("Kent")      # user selects from dropdown
"""

import os
import pandas as pd
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

# Path to the cleaned CSV, relative to repo root.
# Assumes this file lives at backend/query_engine.py
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_CSV  = REPO_ROOT / "datasets" / "all_lead_datasets.csv"

# Contamination threshold (ppb). Fixtures above this are counted as contaminated.
# Must match project_config.txt: CONTAMINATION_THRESHOLD_PPB
CONTAMINATION_THRESHOLD_PPB = 5

# Unit replacement costs per fixture type (USD).
# Must match project_config.txt cost values.
# TODO - UPDATE THESE VALUES TO BE MORE`ACCURATE
UNIT_COSTS = {
    "Tap/Sink":              600,
    "Water Fountain":       1500,
    "Bottle Refill Station":1500,
    "Water Cooler":          800,
    "Ice Machine/Fridge":    800,
    "Pot Filler":            600,
    "Sprayer/Hose":          400,
    "Other":                 600,
}

# ── Data loading ──────────────────────────────────────────────────────────────

# Module-level cache: CSV is loaded once per process, not on every query.
_df_cache: pd.DataFrame | None = None


def _load_data() -> pd.DataFrame:
    """Load and cache lead_data_clean.csv. Raises FileNotFoundError if missing."""
    global _df_cache
    if _df_cache is None:
        if not DATA_CSV.exists():
            raise FileNotFoundError(
                f"Data file not found: {DATA_CSV}\n"
                f"Make sure lead_data_clean.csv is in the repo root."
            )
        _df_cache = pd.read_csv(DATA_CSV, encoding="latin1", low_memory=False)
        # Normalize key text columns once at load time
        _df_cache["school_district"]     = _df_cache["school_district"].str.strip()
        _df_cache["school_name"]         = _df_cache["school_name"].str.strip()
        _df_cache["contamination_status"]= _df_cache["contamination_status"].str.strip()
        _df_cache["fixture_type"]        = _df_cache["fixture_type"].str.strip()
    return _df_cache


# ── Public API ────────────────────────────────────────────────────────────────

def get_all_districts() -> list[str]:
    """
    Returns a sorted list of all district names in the dataset.
    Call this once at app startup to populate the dropdown.

    Example:
        ["Aberdeen", "Adna", "Almira", ..., "Yakima"]
    """
    df = _load_data()
    return sorted(df["school_district"].unique().tolist())


def search_district(district_name: str) -> dict:
    """
    Returns a structured result dict for the given district.
    The district_name must exactly match a value from get_all_districts().

    Returns:
        {
            "district_name":  str,
            "found":          bool,       # False if district not in dataset
            "schools":        list[str],  # all schools in district
            "summary":        dict,       # stats for the summary card
            "fixture_rows":   DataFrame,  # contaminated rows, used by csv_generator
            "all_rows":       DataFrame,  # all rows for the district
        }

    Summary dict keys:
        schools_total           int   unique schools in the dataset for this district
        schools_tested          int   schools that have at least one fixture sample
        schools_contaminated    int   schools with at least one fixture > threshold
        fixtures_tested         int   total fixture samples taken
        fixtures_contaminated   int   fixture samples > threshold
        pct_fixtures_contaminated float
        fixtures_above_by_type  dict  { fixture_type: count } contaminated only
        remediation_cost_by_type dict  { fixture_type: total_cost }
        remediation_cost_total  int
        testing_rounds          list[int]
    """
    df = _load_data()

    # ── Validate district name ────────────────────────────────────────────────
    if district_name not in df["school_district"].values:
        return {
            "district_name": district_name,
            "found":         False,
            "schools":       [],
            "summary":       {},
            "fixture_rows":  pd.DataFrame(),
            "all_rows":      pd.DataFrame(),
        }

    # ── Filter to district ────────────────────────────────────────────────────
    district_df    = df[df["school_district"] == district_name].copy()
    contaminated_df = district_df[district_df["contamination_status"] == "Contaminated"].copy()

    # ── School-level counts ───────────────────────────────────────────────────
    all_schools          = district_df["school_name"].unique().tolist()
    schools_total        = len(all_schools)
    # A school is "tested" if it appears in the dataset at all
    schools_tested       = schools_total
    # A school is "contaminated" if it has at least one contaminated fixture
    schools_contaminated = contaminated_df["school_name"].nunique()

    # ── Fixture-level counts ──────────────────────────────────────────────────
    fixtures_tested        = len(district_df)
    fixtures_contaminated  = len(contaminated_df)
    pct_contaminated       = (
        round(100 * fixtures_contaminated / fixtures_tested, 1)
        if fixtures_tested > 0 else 0.0
    )

    # Contaminated fixture counts by type
    fixtures_above_by_type = (
        contaminated_df["fixture_type"]
        .value_counts()
        .to_dict()
    )

    # ── Remediation cost calculation ──────────────────────────────────────────
    remediation_cost_by_type = {}
    for fixture_type, count in fixtures_above_by_type.items():
        unit_cost = UNIT_COSTS.get(fixture_type, UNIT_COSTS["Other"])
        remediation_cost_by_type[fixture_type] = unit_cost * count

    remediation_cost_total = sum(remediation_cost_by_type.values())

    # ── Testing rounds present ────────────────────────────────────────────────
    testing_rounds = sorted(district_df["DOH_testing_round"].dropna().unique().astype(int).tolist())

    # ── Build summary dict ────────────────────────────────────────────────────
    summary = {
        "schools_total":              schools_total,
        "schools_tested":             schools_tested,
        "schools_contaminated":       schools_contaminated,
        "fixtures_tested":            fixtures_tested,
        "fixtures_contaminated":      fixtures_contaminated,
        "pct_fixtures_contaminated":  pct_contaminated,
        "fixtures_above_by_type":     fixtures_above_by_type,
        "remediation_cost_by_type":   remediation_cost_by_type,
        "remediation_cost_total":     remediation_cost_total,
        "testing_rounds":             testing_rounds,
    }

    return {
        "district_name": district_name,
        "found":         True,
        "schools":       sorted(all_schools),
        "summary":       summary,
        "fixture_rows":  contaminated_df.reset_index(drop=True),
        "all_rows":      district_df.reset_index(drop=True),
    }