"""
Police Force Area boundaries.

Downloads the December 2023 PFA boundaries from the ONS Open Geography
Portal (BUC = Ultra Generalised Clipped, ~340KB) on first run and caches
to disk. Subsequent runs read from cache.

The downloaded GeoJSON uses two force names that don't match the brief's
canonical list:
    "Devon & Cornwall"   ->  "Devon and Cornwall"
    "London, City of"    ->  "City of London"

These are rewritten in-place so the rest of the app can use a single
naming convention.
"""

from __future__ import annotations

import json
import pathlib

import requests


# ONS Open Geography Portal — Police Force Areas (Dec 2023), ultra generalised.
# The Dec 2024 BGC variant referenced in the brief currently 400s; this is the
# next-best stable equivalent and is small enough to load quickly.
GEOJSON_URL = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Police_Force_Areas_December_2023_EW_BUC/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=geojson"
)

CACHE_DIR  = pathlib.Path(__file__).parent / "data"
CACHE_FILE = CACHE_DIR / "pfa_2023_buc.geojson"

# GeoJSON property holding the force name
NAME_FIELD = "PFA23NM"

# Reconcile GeoJSON force names with the canonical list used in data.py
NAME_FIXES = {
    "Devon & Cornwall":  "Devon and Cornwall",
    "London, City of":   "City of London",
}


def _download() -> dict:
    """Fetch the GeoJSON from ONS, rewrite force names, and cache to disk."""
    resp = requests.get(GEOJSON_URL, timeout=30)
    resp.raise_for_status()
    geo = resp.json()

    for feature in geo.get("features", []):
        props = feature.get("properties", {})
        name = props.get(NAME_FIELD)
        if name in NAME_FIXES:
            props[NAME_FIELD] = NAME_FIXES[name]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(geo))
    return geo


def get_pfa_geojson() -> dict:
    """Return the GeoJSON dict, downloading on first call."""
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return _download()
