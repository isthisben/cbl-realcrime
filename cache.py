"""
Tiny on-disk cache for the expensive startup parses.

The dashboard assembles its data by reading several large Home Office
ODS / XLSX files with odfpy / openpyxl, which takes ~3 minutes cold. Those
inputs only change when a new release is dropped into `data/raw/`, so the
assembled results are pickled to disk and reused until a source file changes.

    cached(name, signature, build)  ->  build()'s result, served from disk
                                        when the stored signature matches,
                                        otherwise freshly built and written.

`signature` is any pickleable value that captures every input the result
depends on — typically `file_signature(...)` of the source files plus a
version int. The cache entry is keyed by `name`; bumping the version or
touching any source file invalidates it.

Stored with pickle, so the assembled DataFrame (whose `crime_profile` /
`crime_counts` columns hold plain dicts) round-trips exactly — parquet would
need pyarrow and would not preserve the dict columns.
Reads and writes are best-effort: a corrupt file, a pandas-version-skewed
pickle, or an unwritable directory degrades to a rebuild rather than raising,
so a stale cache can never wedge the dashboard.

The cache directory (`data/cache/`) is gitignored — it is a local performance
artefact regenerated from the raw files on demand, not a source of truth.
"""

from __future__ import annotations

import pathlib
import pickle
from typing import Any, Callable


CACHE_DIR = pathlib.Path(__file__).parent / "data" / "cache"


def file_signature(*paths: pathlib.Path) -> list | None:
    """`[name, size, mtime_ns]` per path, in order. Returns None if any path
    is missing: a missing input means "don't trust or write a cache", so the
    caller rebuilds and the loader surfaces its own FileNotFoundError."""
    sig: list[list] = []
    for p in paths:
        try:
            st = p.stat()
        except OSError:
            return None
        sig.append([p.name, st.st_size, st.st_mtime_ns])
    return sig


def _path(name: str) -> pathlib.Path:
    return CACHE_DIR / f"{name}.pkl"


def load(name: str, signature: Any) -> Any | None:
    """Return the cached value for `name` if present and its stored signature
    equals `signature`, else None. Any read/unpickle failure is a miss."""
    path = _path(name)
    if not path.exists():
        return None
    try:
        with path.open("rb") as fh:
            blob = pickle.load(fh)
        if blob.get("signature") == signature:
            return blob["value"]
    except Exception:
        pass  # corrupt / version-skewed / unreadable -> treat as a miss
    return None


def store(name: str, signature: Any, value: Any) -> None:
    """Write `value` under `name` with `signature`. Best-effort: a write
    failure is swallowed so caching can never break the build. The write is
    atomic (temp file + replace) so an interrupted write can't leave a
    half-written cache that would later fail to unpickle."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _path(name)
        tmp = path.with_suffix(".pkl.tmp")
        with tmp.open("wb") as fh:
            pickle.dump({"signature": signature, "value": value}, fh,
                        protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)  # atomic on the same filesystem
    except Exception:
        pass


def cached(name: str, signature: Any, build: Callable[[], Any],
           *, refresh: bool = False) -> Any:
    """build()'s result, served from disk when the stored signature matches.

    Rebuilds (and re-caches) on a miss or when `refresh=True`. If `signature`
    is None the cache is bypassed entirely — build() runs and nothing is
    written; callers pass None when a source file is missing so the loader's
    own error surfaces instead of a stale hit.
    """
    if signature is not None and not refresh:
        hit = load(name, signature)
        if hit is not None:
            return hit
    value = build()
    if signature is not None:
        store(name, signature, value)
    return value


def clear(name: str | None = None) -> None:
    """Delete one cache entry (`name`) or the whole cache directory (None)."""
    if name is not None:
        _path(name).unlink(missing_ok=True)
        return
    for p in CACHE_DIR.glob("*.pkl"):
        p.unlink(missing_ok=True)
