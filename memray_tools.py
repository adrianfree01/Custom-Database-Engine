from datetime import datetime
from pathlib import Path
import os
import subprocess
import sys
import time

import psutil
import tracemalloc
import memray

tracemalloc.start()

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "profiles"
PROFILE_DIR.mkdir(exist_ok=True)
FLAMEGRAPH_DIR = PROFILE_DIR / "flamegraphs"
FLAMEGRAPH_DIR.mkdir(exist_ok=True)


def get_live_memory():
    process = psutil.Process(os.getpid())
    mem = process.memory_info()
    current, peak = tracemalloc.get_traced_memory()

    return {
        "rssBytes": mem.rss,
        "vmsBytes": mem.vms,
        "pythonCurrentBytes": current,
        "pythonPeakBytes": peak
    }


def _new_profile_path(prefix="profile"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return PROFILE_DIR / f"{prefix}_{timestamp}.bin"


def _to_profile_metadata(profile_path, duration_seconds):
    stat = profile_path.stat()
    return {
        "profilePath": str(profile_path),
        "profileFile": profile_path.name,
        "sizeBytes": stat.st_size,
        "createdAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "durationMs": round(duration_seconds * 1000, 2)
    }


def _to_flamegraph_metadata(flamegraph_path):
    stat = flamegraph_path.stat()
    return {
        "flamegraphPath": str(flamegraph_path),
        "flamegraphFile": flamegraph_path.name,
        "urlPath": f"/flamegraphs/{flamegraph_path.name}",
        "sizeBytes": stat.st_size,
        "createdAt": datetime.fromtimestamp(stat.st_mtime).isoformat()
    }


def _generate_flamegraph(profile_path):
    flamegraph_file = FLAMEGRAPH_DIR / f"{profile_path.stem}.html"

    command = [
        sys.executable,
        "-m",
        "memray",
        "flamegraph",
        str(profile_path),
        "-o",
        str(flamegraph_file)
    ]
    completed = subprocess.run(command, capture_output=True, text=True)

    if completed.returncode != 0:
        return {
            "ok": False,
            "error": completed.stderr.strip() or completed.stdout.strip() or "Failed to create flamegraph."
        }

    return {
        "ok": True,
        "flamegraph": _to_flamegraph_metadata(flamegraph_file)
    }


def profile_function(function_to_run, *args, profile_prefix="profile", **kwargs):
    output_file = _new_profile_path(profile_prefix)
    started = time.perf_counter()

    with memray.Tracker(str(output_file)):
        result = function_to_run(*args, **kwargs)
    duration = time.perf_counter() - started

    profile = _to_profile_metadata(output_file, duration)
    flamegraph_result = _generate_flamegraph(output_file)
    if flamegraph_result["ok"]:
        profile["flamegraph"] = flamegraph_result["flamegraph"]
    else:
        profile["flamegraphError"] = flamegraph_result["error"]

    return {
        "result": result,
        "profile": profile
    }


def list_profiles(limit=20):
    files = sorted(
        PROFILE_DIR.glob("*.bin"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )
    listed = files[:limit]

    return {
        "count": len(files),
        "profiles": [_to_profile_metadata(path, 0) for path in listed]
    }


def list_flamegraphs(limit=20):
    files = sorted(
        FLAMEGRAPH_DIR.glob("*.html"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )
    listed = files[:limit]

    return {
        "count": len(files),
        "flamegraphs": [_to_flamegraph_metadata(path) for path in listed]
    }


def clear_profiles():
    removed = 0
    for path in PROFILE_DIR.glob("*.bin"):
        path.unlink()
        removed += 1

    removed_flamegraphs = 0
    for path in FLAMEGRAPH_DIR.glob("*.html"):
        path.unlink()
        removed_flamegraphs += 1

    return {
        "removedCount": removed,
        "removedFlamegraphCount": removed_flamegraphs
    }
