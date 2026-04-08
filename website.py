from pathlib import Path
import os
import re
import time
import textwrap

from fastapi import FastAPI
from fastapi import Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import psutil

from database_engine import Database
from memray_tools import (
    FLAMEGRAPH_DIR,
    clear_profiles,
    get_live_memory,
    list_flamegraphs,
    list_profiles,
    profile_function
)

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
INDEX_FILE = ASSETS_DIR / "index.html"
DOC_FILES = {
    "README.md": BASE_DIR / "README.md",
    "MEMRAY_PACKAGE_REPORT.md": BASE_DIR / "MEMRAY_PACKAGE_REPORT.md"
}

app = FastAPI()
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/flamegraphs", StaticFiles(directory=str(FLAMEGRAPH_DIR)), name="flamegraphs")

db = Database(1, "AdrianDB")


class QueryRequest(BaseModel):
    query: str


class BulkQueryRequest(BaseModel):
    queries: str


@app.get("/", response_class=FileResponse)
def home():
    return FileResponse(INDEX_FILE)


@app.get("/stats")
def stats():
    return db.get_stats()


@app.get("/memory")
def memory():
    return get_live_memory()


@app.get("/profiles")
def profiles(limit: int = 20):
    return list_profiles(limit=max(1, min(limit, 100)))


@app.get("/flamegraphs-meta")
def flamegraphs_meta(limit: int = 20):
    return list_flamegraphs(limit=max(1, min(limit, 100)))


@app.get("/pi-stats")
def pi_stats():
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot_time = psutil.boot_time()
    uptime_seconds = max(0, int(time.time() - boot_time))

    cpu_temp_c = None
    temp_file = Path("/sys/class/thermal/thermal_zone0/temp")
    if temp_file.exists():
        try:
            raw = temp_file.read_text(encoding="utf-8").strip()
            cpu_temp_c = round(int(raw) / 1000.0, 1)
        except (ValueError, OSError):
            cpu_temp_c = None

    try:
        load1, load5, load15 = os.getloadavg()
    except OSError:
        load1, load5, load15 = 0.0, 0.0, 0.0

    return {
        "cpuPercent": psutil.cpu_percent(interval=None),
        "cpuCountLogical": psutil.cpu_count(logical=True),
        "cpuCountPhysical": psutil.cpu_count(logical=False),
        "cpuTempC": cpu_temp_c,
        "memoryTotalBytes": vm.total,
        "memoryUsedBytes": vm.used,
        "memoryPercent": vm.percent,
        "diskTotalBytes": disk.total,
        "diskUsedBytes": disk.used,
        "diskPercent": disk.percent,
        "loadAverage": {
            "one": round(load1, 2),
            "five": round(load5, 2),
            "fifteen": round(load15, 2)
        },
        "uptimeSeconds": uptime_seconds
    }


def _escape_pdf_text(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _estimate_text_width(text, font_size):
    width = 0.0
    for char in text:
        if char == " ":
            width += font_size * 0.30
        elif char in "il.,:;!|":
            width += font_size * 0.24
        elif char in "MW@#%&":
            width += font_size * 0.74
        else:
            width += font_size * 0.56
    return width


def _split_inline_markdown(text, default_font):
    segments = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")
    last = 0

    for match in pattern.finditer(text):
        if match.start() > last:
            segments.append((default_font, text[last:match.start()]))

        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            segments.append(("F2", token[2:-2]))
        elif token.startswith("*") and token.endswith("*"):
            segments.append(("F4", token[1:-1]))
        else:
            segments.append((default_font, token))
        last = match.end()

    if last < len(text):
        segments.append((default_font, text[last:]))

    return segments if segments else [(default_font, text)]


def _markdown_to_styled_lines(markdown_text):
    styled = []
    in_code_block = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            styled.append(("code", line))
            continue

        if not line.strip():
            styled.append(("blank", ""))
            continue

        if line.startswith("### "):
            styled.append(("h3", line[4:].strip()))
            continue
        if line.startswith("## "):
            styled.append(("h2", line[3:].strip()))
            continue
        if line.startswith("# "):
            styled.append(("h1", line[2:].strip()))
            continue
        if line.startswith("> "):
            styled.append(("quote", line[2:].strip()))
            continue
        if re.match(r"^\d+\.\s+", line):
            styled.append(("list", line))
            continue
        if line.startswith("- "):
            styled.append(("list", line))
            continue

        styled.append(("body", line))

    return styled


def _build_pdf_from_markdown(markdown_text):
    page_width = 612
    page_height = 792
    margin_left = 48
    margin_top = 48
    margin_bottom = 48

    styles = {
        "h1": {"font": "F2", "size": 20, "leading": 28, "max_chars": 50, "x": margin_left},
        "h2": {"font": "F2", "size": 16, "leading": 24, "max_chars": 64, "x": margin_left},
        "h3": {"font": "F2", "size": 14, "leading": 20, "max_chars": 72, "x": margin_left},
        "body": {"font": "F1", "size": 11, "leading": 16, "max_chars": 94, "x": margin_left},
        "list": {"font": "F1", "size": 11, "leading": 16, "max_chars": 88, "x": margin_left + 8},
        "quote": {"font": "F4", "size": 11, "leading": 16, "max_chars": 88, "x": margin_left + 8},
        "code": {"font": "F3", "size": 9, "leading": 13, "max_chars": 104, "x": margin_left + 8}
    }

    pages = [[]]
    y = page_height - margin_top

    for style_name, text in _markdown_to_styled_lines(markdown_text):
        if style_name == "blank":
            y -= 10
            if y < margin_bottom:
                pages.append([])
                y = page_height - margin_top
            continue

        style = styles[style_name]
        wrapped = textwrap.wrap(text, width=style["max_chars"]) or [""]

        for line in wrapped:
            if y < margin_bottom + style["leading"]:
                pages.append([])
                y = page_height - margin_top

            pages[-1].append({
                "font": style["font"],
                "size": style["size"],
                "x": style["x"],
                "y": y,
                "style": style_name,
                "text": line
            })
            y -= style["leading"]

        y -= 2

    num_pages = len(pages)
    first_content_id = 5
    first_page_id = first_content_id + num_pages
    pages_id = first_page_id + num_pages
    catalog_id = pages_id + 1

    objects = {}
    objects[1] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objects[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"
    objects[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >>"

    for page_index, entries in enumerate(pages):
        commands = []
        for entry in entries:
            if entry["style"] in {"code", "h1", "h2", "h3"}:
                safe_text = _escape_pdf_text(entry["text"])
                commands.append(
                    f"BT /{entry['font']} {entry['size']} Tf {entry['x']} {entry['y']:.2f} Td ({safe_text}) Tj ET\n"
                )
            else:
                x_cursor = entry["x"]
                for font_name, segment_text in _split_inline_markdown(entry["text"], entry["font"]):
                    safe_text = _escape_pdf_text(segment_text)
                    commands.append(
                        f"BT /{font_name} {entry['size']} Tf {x_cursor:.2f} {entry['y']:.2f} Td ({safe_text}) Tj ET\n"
                    )
                    x_cursor += _estimate_text_width(segment_text, entry["size"])
        stream_bytes = "".join(commands).encode("latin-1", errors="replace")
        content_obj = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"endstream"
        )
        content_id = first_content_id + page_index
        objects[content_id] = content_obj

    for page_index in range(num_pages):
        page_id = first_page_id + page_index
        content_id = first_content_id + page_index
        page_obj = (
            f"<< /Type /Page /Parent {pages_id} 0 R "
            f"/MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 1 0 R /F2 2 0 R /F3 3 0 R /F4 4 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[page_id] = page_obj

    kid_refs = " ".join(f"{first_page_id + i} 0 R" for i in range(num_pages))
    objects[pages_id] = f"<< /Type /Pages /Kids [{kid_refs}] /Count {num_pages} >>".encode("ascii")
    objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii")

    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0] * (catalog_id + 1)

    for object_id in range(1, catalog_id + 1):
        offsets[object_id] = len(pdf)
        pdf += f"{object_id} 0 obj\n".encode("ascii")
        pdf += objects[object_id] + b"\n"
        pdf += b"endobj\n"

    xref_offset = len(pdf)
    pdf += f"xref\n0 {catalog_id + 1}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for object_id in range(1, catalog_id + 1):
        pdf += f"{offsets[object_id]:010} 00000 n \n".encode("ascii")

    pdf += (
        f"trailer\n<< /Size {catalog_id + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")

    return pdf


@app.get("/readme-pdf/{file_name}")
def get_readme_pdf(file_name: str):
    if file_name not in DOC_FILES:
        return Response(
            content="Unsupported file name.",
            media_type="text/plain",
            status_code=404
        )

    path = DOC_FILES[file_name]
    if not path.exists():
        return Response(
            content=f"File '{file_name}' not found.",
            media_type="text/plain",
            status_code=404
        )

    markdown_text = path.read_text(encoding="utf-8")
    pdf_bytes = _build_pdf_from_markdown(markdown_text)
    pdf_name = f"{path.stem}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{pdf_name}"'}
    )


@app.post("/profiles/clear")
def clear_profile_files():
    return clear_profiles()


@app.post("/query")
def query(request: QueryRequest):
    try:
        return db.run_query(request.query)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc)
        }


@app.post("/bulk-query")
def bulk_query(request: BulkQueryRequest):
    try:
        return db.run_bulk_queries(request.queries)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc)
        }


@app.post("/profile/query")
def profile_query(request: QueryRequest):
    def _safe_run_query(query_text):
        try:
            return db.run_query(query_text)
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc)
            }

    profiled = profile_function(_safe_run_query, request.query, profile_prefix="query")
    result = profiled["result"]

    return {
        "ok": result.get("ok", True),
        "result": result,
        "profile": profiled["profile"]
    }


@app.post("/profile/bulk-query")
def profile_bulk_query(request: BulkQueryRequest):
    def _safe_run_bulk(text):
        try:
            return db.run_bulk_queries(text)
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc)
            }

    profiled = profile_function(_safe_run_bulk, request.queries, profile_prefix="bulk")
    result = profiled["result"]

    return {
        "ok": result.get("ok", True),
        "result": result,
        "profile": profiled["profile"]
    }
