"""
Load TIGER 2024 state, county, and congressional district boundaries into
prism_states, prism_counties, prism_districts.

Defaults to VT + NV pilot scope. Override with PRISM_PILOT_STATES env var or
--states flag.

Usage:
    python -m prism.boundaries.load_tiger                  # VT,NV
    python -m prism.boundaries.load_tiger --states VT,NV,FL
    python -m prism.boundaries.load_tiger --download-only   # cache shapefiles, no DB

Downloads TIGER shapefiles into modal/cache/tiger/ on first run.
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Iterable

import click
import geopandas as gpd
import requests
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from prism.db import pg_conn
from prism.log import db_log, get_logger

logger = get_logger(__name__)

TIGER_YEAR = 2024
CONGRESS = 119
CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "tiger"

# State FIPS index for filtering counties + districts to selected states
STATE_FIPS_BY_ABBR: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}


def _tiger_url(kind: str) -> str:
    base = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}"
    if kind == "state":
        return f"{base}/STATE/tl_{TIGER_YEAR}_us_state.zip"
    if kind == "county":
        return f"{base}/COUNTY/tl_{TIGER_YEAR}_us_county.zip"
    if kind == "cd":
        return f"{base}/CD/tl_{TIGER_YEAR}_us_cd{CONGRESS}.zip"
    raise ValueError(f"Unknown TIGER kind: {kind}")


def _download_and_extract(kind: str) -> Path:
    """Download a TIGER zip to the cache dir, extract, return path to .shp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = CACHE_DIR / kind
    target_dir.mkdir(exist_ok=True)
    # Reuse cached extract if present
    shp = next(target_dir.glob("*.shp"), None)
    if shp:
        logger.info("Using cached %s shapefile: %s", kind, shp)
        return shp
    url = _tiger_url(kind)
    logger.info("Downloading %s from %s", kind, url)
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        zf.extractall(target_dir)
    shp = next(target_dir.glob("*.shp"))
    return shp


def _ensure_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    raise ValueError(f"Expected (Multi)Polygon, got {type(geom).__name__}")


def load_states(fips_set: set[str]) -> int:
    shp = _download_and_extract("state")
    gdf = gpd.read_file(shp).to_crs("EPSG:4326")
    gdf = gdf[gdf["STATEFP"].isin(fips_set)].copy()
    if gdf.empty:
        logger.warning("No state rows matched FIPS %s", fips_set)
        return 0

    with pg_conn() as conn, conn.cursor() as cur:
        for _, row in gdf.iterrows():
            geom = _ensure_multipolygon(row.geometry)
            cur.execute(
                """
                INSERT INTO prism_states (state_fips, state_name, state_abbr, geom, area_sq_km)
                VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                ON CONFLICT (state_fips) DO UPDATE
                  SET state_name = EXCLUDED.state_name,
                      state_abbr = EXCLUDED.state_abbr,
                      geom = EXCLUDED.geom,
                      area_sq_km = EXCLUDED.area_sq_km
                """,
                (
                    row["STATEFP"],
                    row["NAME"],
                    row["STUSPS"],
                    geom.wkt,
                    float(row.geometry.area) * 111.0 * 111.0,  # crude km^2
                ),
            )
        conn.commit()
    logger.info("Loaded %d states", len(gdf))
    return len(gdf)


def load_counties(fips_set: set[str]) -> int:
    shp = _download_and_extract("county")
    gdf = gpd.read_file(shp).to_crs("EPSG:4326")
    gdf = gdf[gdf["STATEFP"].isin(fips_set)].copy()
    if gdf.empty:
        logger.warning("No county rows matched FIPS %s", fips_set)
        return 0

    with pg_conn() as conn, conn.cursor() as cur:
        for _, row in gdf.iterrows():
            geom = _ensure_multipolygon(row.geometry)
            cur.execute(
                """
                INSERT INTO prism_counties (county_fips, state_fips, county_name, geom, area_sq_km)
                VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                ON CONFLICT (county_fips) DO UPDATE
                  SET county_name = EXCLUDED.county_name,
                      geom = EXCLUDED.geom,
                      area_sq_km = EXCLUDED.area_sq_km
                """,
                (
                    row["GEOID"],
                    row["STATEFP"],
                    row["NAME"],
                    geom.wkt,
                    float(row.geometry.area) * 111.0 * 111.0,
                ),
            )
        conn.commit()
    logger.info("Loaded %d counties", len(gdf))
    return len(gdf)


def load_districts(fips_set: set[str]) -> int:
    shp = _download_and_extract("cd")
    gdf = gpd.read_file(shp).to_crs("EPSG:4326")
    state_col = "STATEFP" if "STATEFP" in gdf.columns else "STATEFP20"
    cd_col = next((c for c in ("CD119FP", "CDFP", "CDSESSN") if c in gdf.columns), None)
    if cd_col is None:
        logger.error("Could not find CD column; available: %s", list(gdf.columns))
        return 0
    gdf = gdf[gdf[state_col].isin(fips_set)].copy()
    if gdf.empty:
        logger.warning("No district rows matched FIPS %s", fips_set)
        return 0

    with pg_conn() as conn, conn.cursor() as cur:
        for _, row in gdf.iterrows():
            geom = _ensure_multipolygon(row.geometry)
            district_id = f"{row[state_col]}-{row[cd_col]}"
            cur.execute(
                """
                INSERT INTO prism_districts (district_id, state_fips, district_number, congress, geom, area_sq_km)
                VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                ON CONFLICT (district_id) DO UPDATE
                  SET district_number = EXCLUDED.district_number,
                      congress = EXCLUDED.congress,
                      geom = EXCLUDED.geom,
                      area_sq_km = EXCLUDED.area_sq_km
                """,
                (
                    district_id,
                    row[state_col],
                    row[cd_col],
                    CONGRESS,
                    geom.wkt,
                    float(row.geometry.area) * 111.0 * 111.0,
                ),
            )
        conn.commit()
    logger.info("Loaded %d districts", len(gdf))
    return len(gdf)


def _resolve_fips(state_abbrs: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for a in state_abbrs:
        fips = STATE_FIPS_BY_ABBR.get(a.upper())
        if not fips:
            raise click.BadParameter(f"Unknown state abbreviation: {a}")
        out.add(fips)
    return out


@click.command()
@click.option(
    "--states",
    default=lambda: os.environ.get("PRISM_PILOT_STATES", "VT,NV"),
    help="Comma-separated state abbreviations to load (default: VT,NV).",
)
@click.option("--download-only", is_flag=True, help="Cache shapefiles, skip DB load.")
def cli(states: str, download_only: bool) -> None:
    abbrs = [s.strip().upper() for s in states.split(",") if s.strip()]
    fips_set = _resolve_fips(abbrs)
    logger.info("TIGER load: states=%s fips=%s", abbrs, sorted(fips_set))

    if download_only:
        for kind in ("state", "county", "cd"):
            _download_and_extract(kind)
        return

    s = load_states(fips_set)
    c = load_counties(fips_set)
    d = load_districts(fips_set)
    db_log(
        layer_id=None,
        action="seed",
        status="ok",
        features_processed=s + c + d,
        message=f"TIGER {TIGER_YEAR}: {s} states, {c} counties, {d} districts ({abbrs})",
        payload={"states": abbrs, "counts": {"states": s, "counties": c, "districts": d}},
    )


if __name__ == "__main__":
    sys.exit(cli(standalone_mode=False) or 0)
