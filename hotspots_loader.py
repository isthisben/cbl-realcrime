"""
Top-5 stop-and-search hotspots per force.

    load_hotspots()  ->  DataFrame: force, rank, lat, lon, searches, linked_finds, find_rate

For each force, the five locations with the most recorded stop-and-searches
(data.police.uk, 2023-2026), and the find rate at each — the share of searches
there that led to a linked outcome (find_rate = linked_finds / searches).

Stop-and-search data is published for 39 of the dashboard's 42 forces, so three
forces (Gwent, South Yorkshire, Warwickshire) have no extract and are absent
here; the dashboard shows a "no data" note for them.

Source file: data/raw/hotspots.csv (the model team's extract). Force names are
data.police.uk slugs there, normalised to the dashboard's canonical names below.
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "hotspots.csv"

# Forces with no stop-and-search extract, so no hotspots. Surfaced as a note.
FORCES_WITHOUT_DATA = {"Gwent", "South Yorkshire", "Warwickshire"}

# data.police.uk slugs that don't come out right from the plain hyphen->space
# title-case rule below.
_SLUG_FIXES = {
    "metropolitan":   "Metropolitan Police",
    "city-of-london": "City of London",
    "dyfed-powys":    "Dyfed-Powys",
}


def _canonical(slug: str) -> str:
    """data.police.uk force slug -> the dashboard's canonical force name."""
    if slug in _SLUG_FIXES:
        return _SLUG_FIXES[slug]
    return slug.replace("-", " ").title().replace(" And ", " and ")


def load_hotspots() -> pd.DataFrame:
    """The five stop-and-search hotspots per force, long format, canonical
    force names. Fails loud if the file or any expected column is missing, or
    if a force doesn't carry exactly five ranked rows."""
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Hotspots file not found at {SOURCE}. See data/raw/SOURCES.md."
        )

    df = pd.read_csv(SOURCE)
    required = {"force", "rank", "Latitude", "Longitude",
                "searches", "linked_finds", "find_rate"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"hotspots.csv is missing columns {sorted(missing)}. "
            f"Found {list(df.columns)}."
        )

    df = df.rename(columns={"Latitude": "lat", "Longitude": "lon"})
    df["force"] = df["force"].map(_canonical)

    counts = df.groupby("force").size()
    bad = counts[counts != 5]
    if not bad.empty:
        raise ValueError(
            f"hotspots.csv: expected 5 ranked rows per force, got {dict(bad)}."
        )

    out = df[["force", "rank", "lat", "lon",
              "searches", "linked_finds", "find_rate"]]
    return out.sort_values(["force", "rank"]).reset_index(drop=True)
