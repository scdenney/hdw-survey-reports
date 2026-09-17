#!/usr/bin/env python3
"""Render a teacher-only Markdown report for one HDW Data-module survey.

Selects a survey by module, cohort, and kind from surveys.json, exports only
the content and free-text questions from Qualtrics (identity columns are never
requested), and writes a Markdown report. Nothing response-level is committed
anywhere; the workflow shows the report on the run page and keeps an artifact
for seven days.

Offline modes: --input-csv renders an existing export; --dry-run prints what a
live run would request and exits without touching the network.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import tempfile
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:  # offline modes do not need it
    requests = None

HERE = Path(__file__).resolve().parent
SURVEYS_PATH = HERE / "surveys.json"


# ---- Qualtrics --------------------------------------------------------------

class QualtricsClient:
    def __init__(self, token: str, data_center: str):
        if not token:
            sys.exit("QUALTRICS_API_TOKEN is not set")
        if not data_center:
            sys.exit("QUALTRICS_DATACENTER is not set")
        self.base = f"https://{data_center}.qualtrics.com/API/v3"
        self.headers = {"X-API-TOKEN": token}

    def fetch_definition(self, survey_id: str) -> dict:
        r = requests.get(self.base + f"/survey-definitions/{survey_id}",
                         headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()


def tag_to_qid(definition: dict, tags: list[str]) -> dict[str, str]:
    """Map DataExportTags to QIDs. Fails closed: every tag must resolve."""
    questions = definition.get("result", {}).get("Questions", {}) or {}
    by_tag = {q.get("DataExportTag"): q_id for q_id, q in questions.items()}
    missing = [tag for tag in tags if tag not in by_tag]
    if missing:
        raise RuntimeError(
            f"No question with DataExportTag {missing}; refusing to fall back "
            "to a full export"
        )
    return {tag: by_tag[tag] for tag in tags}


def fetch_export(client: QualtricsClient, survey_id: str, destination: Path,
                 question_ids: list[str], embedded_ids: list[str] | None) -> Path:
    payload: dict = {"format": "csv", "useLabels": True, "questionIds": question_ids}
    if embedded_ids:
        payload["embeddedDataIds"] = embedded_ids
    response = requests.post(
        client.base + f"/surveys/{survey_id}/export-responses",
        headers={**client.headers, "Content-Type": "application/json"},
        data=json.dumps(payload), timeout=30,
    )
    response.raise_for_status()
    progress_id = response.json()["result"]["progressId"]

    file_id = None
    for _ in range(120):
        status = requests.get(
            client.base + f"/surveys/{survey_id}/export-responses/{progress_id}",
            headers=client.headers, timeout=30,
        )
        status.raise_for_status()
        result = status.json()["result"]
        if result.get("status") == "complete":
            file_id = result["fileId"]
            break
        if result.get("status") == "failed":
            raise RuntimeError(f"Qualtrics response export failed: {result}")
        time.sleep(1)
    if not file_id:
        raise TimeoutError("Qualtrics response export did not finish within two minutes")

    download = requests.get(
        client.base + f"/surveys/{survey_id}/export-responses/{file_id}/file",
        headers=client.headers, timeout=120,
    )
    download.raise_for_status()
    archive = destination / "responses.zip"
    archive.write_bytes(download.content)
    with zipfile.ZipFile(archive) as zipped:
        csv_names = [name for name in zipped.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RuntimeError(f"Expected one CSV in Qualtrics export, found {csv_names}")
        zipped.extract(csv_names[0], destination)
    return destination / csv_names[0]


# ---- Config -----------------------------------------------------------------

def load_surveys(path: Path = SURVEYS_PATH) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def select_survey(cfg: dict, module: str, cohort: str, kind: str) -> dict:
    key = f"{module}/{cohort}/{kind}"
    if key not in cfg:
        available = ", ".join(sorted(k for k in cfg if not k.startswith("_")))
        sys.exit(f"No survey configured for {key}. Available: {available}")
    return cfg[key]


def content_tags(survey: dict) -> list[str]:
    tags = [item["tag"] for item in survey.get("items", [])]
    for arm in survey.get("arms", []):
        tags.extend(arm["columns"].values())
    tags.extend(survey.get("free_text", []))
    return tags


# ---- Rows -------------------------------------------------------------------

def response_rows(csv_path: Path, required: set[str]) -> list[dict[str, str]]:
    """Return one dict per response, skipping Qualtrics's three-row header.

    Matrix and multi-select items export under prefixed column names, so a
    required tag matches either an exact column or a `tag_...` prefix.
    """
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        raw_rows = list(csv.reader(handle))

    def satisfied(row: list[str]) -> bool:
        cols = set(row)
        return all(
            tag in cols or any(col.startswith(tag + "_") for col in cols)
            for tag in required
        )

    header_index = next(
        (index for index, row in enumerate(raw_rows) if satisfied(row)), None
    )
    if header_index is None:
        raise RuntimeError(f"Could not find required export tags {sorted(required)}")
    header = raw_rows[header_index]
    rows = []
    for raw in raw_rows[header_index + 1:]:
        padded = raw + [""] * (len(header) - len(raw))
        row = dict(zip(header, padded))
        response_id = row.get("ResponseId") or row.get("ResponseID") or ""
        if not response_id.startswith("R_"):
            continue
        rows.append(row)
    return rows


def finished_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row for row in rows
        if (row.get("Finished") or "1").strip().lower() in {"1", "true", "yes"}
    ]


def drop_identity(rows: list[dict[str, str]], identity_tags: list[str]) -> list[dict[str, str]]:
    """Remove identity columns if they somehow arrived; warn on stderr."""
    present = sorted({col for row in rows for col in row if col in identity_tags})
    if present:
        print(f"warning: identity columns {present} were present in the export "
              "and have been dropped", file=sys.stderr)
    return [{k: v for k, v in row.items() if k not in identity_tags} for row in rows]


# ---- Tables -----------------------------------------------------------------

def _values(rows: list[dict[str, str]], tag: str, multi: bool = False) -> list[str]:
    out = []
    for row in rows:
        cell = (row.get(tag) or "").strip()
        if not cell:
            continue
        if multi:
            out.extend(part.strip() for part in cell.split(",") if part.strip())
        else:
            out.append(cell)
    return out


def count_table(rows: list[dict[str, str]], tag: str, labels: list[str],
                multi: bool = False) -> list[tuple[str, int, float]]:
    counts = Counter(_values(rows, tag, multi))
    total = sum(counts.values())
    ordered = list(labels) + [f"{label} (unlisted)" for label in counts if label not in labels]
    table = []
    for label in ordered:
        raw = label[:-len(" (unlisted)")] if label.endswith(" (unlisted)") else label
        n = counts.get(raw, 0)
        table.append((label, n, (100.0 * n / total) if total else 0.0))
    return table


def matrix_columns(rows: list[dict[str, str]], tag: str) -> list[str]:
    cols = sorted({col for row in rows for col in row if col.startswith(tag + "_")},
                  key=lambda c: (len(c), c))
    return cols


def arm_table(rows: list[dict[str, str]], arm: dict, field: str
              ) -> list[tuple[str, dict[str, tuple[int, float]]]]:
    per_arm: dict[str, Counter] = {}
    for condition, tag in arm["columns"].items():
        subset = [row for row in rows if (row.get(field) or "").strip() == condition]
        per_arm[condition] = Counter(_values(subset, tag))
    labels = list(arm["labels"])
    for counter in per_arm.values():
        labels.extend(l for l in counter if l not in labels)
    table = []
    for label in labels:
        cells = {}
        for condition, counter in per_arm.items():
            total = sum(counter.values())
            n = counter.get(label, 0)
            cells[condition] = (n, (100.0 * n / total) if total else 0.0)
        table.append((label, cells))
    return table


def free_text(rows: list[dict[str, str]], tag: str) -> list[str]:
    texts = [t for t in ((row.get(tag) or "").strip() for row in rows) if t]
    random.SystemRandom().shuffle(texts)
    return texts


# ---- Markdown ---------------------------------------------------------------

def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(survey: dict, rows: list[dict[str, str]], fetched_at: str,
                    source: str) -> str:
    lines = [f"# {survey['title']}", ""]
    lines.append(f"Finished responses: {len(rows)}  ")
    lines.append(f"Fetched: {fetched_at}  ")
    lines.append(f"Source: {source}")
    lines.append("")

    for item in survey.get("items", []):
        tag, title = item["tag"], item.get("title", item["tag"])
        lines.append(f"## {title}")
        lines.append("")
        if item.get("matrix"):
            cols = matrix_columns(rows, tag)
            if not cols:
                lines.append("_No columns found for this item._")
                lines.append("")
                continue
            row_labels = item.get("rows", [])
            col_labels = item.get("labels", [])
            lines.append("| Statement | " + " | ".join(_md_escape(c) for c in col_labels) + " |")
            lines.append("|---|" + "---:|" * len(col_labels))
            for index, col in enumerate(cols):
                statement = row_labels[index] if index < len(row_labels) else col
                counter = Counter(_values(rows, col))
                total = sum(counter.values())
                cells = []
                for label in col_labels:
                    n = counter.get(label, 0)
                    pct = (100.0 * n / total) if total else 0.0
                    cells.append(f"{n} ({pct:.0f}%)")
                unlisted = [l for l in counter if l not in col_labels]
                extra = f" – unlisted: {', '.join(unlisted)}" if unlisted else ""
                lines.append(f"| {_md_escape(statement)}{extra} | " + " | ".join(cells) + " |")
            lines.append("")
            continue
        table = count_table(rows, tag, item.get("labels", []), multi=item.get("multi", False))
        lines.append("| Answer | n | % |")
        lines.append("|---|---:|---:|")
        for label, n, pct in table:
            lines.append(f"| {_md_escape(label)} | {n} | {pct:.0f} |")
        if item.get("labels_pending"):
            lines.append("")
            lines.append("_Labels for this item are provisional; unlisted answers are appended._")
        lines.append("")

    field = survey.get("condition_field")
    for arm in survey.get("arms", []):
        lines.append(f"## {arm['title']} – by condition")
        lines.append("")
        conditions = list(arm["columns"].keys())
        lines.append("| Answer | " + " | ".join(conditions) + " |")
        lines.append("|---|" + "---:|" * len(conditions))
        for label, cells in arm_table(rows, arm, field):
            parts = [f"{cells[c][0]} ({cells[c][1]:.0f}%)" for c in conditions]
            lines.append(f"| {_md_escape(label)} | " + " | ".join(parts) + " |")
        lines.append("")

    for tag in survey.get("free_text", []):
        title = survey.get("free_text_titles", {}).get(tag, tag)
        texts = free_text(rows, tag)
        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"{len(texts)} answers, in random order.")
        lines.append("")
        for text in texts:
            lines.append(f"- {text.replace(chr(10), ' ')}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_outputs(text: str, output: Path, summary_path: str | None) -> None:
    output.write_text(text, encoding="utf-8")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(text)


# ---- Main -------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--module", required=True, choices=["1", "2", "3"])
    parser.add_argument("--cohort", required=True, choices=["en", "nl"])
    parser.add_argument("--kind", required=True, choices=["opener", "application"])
    parser.add_argument("--input-csv", type=Path, help="render an existing export; no network")
    parser.add_argument("--output", type=Path, default=Path("report.md"))
    parser.add_argument("--dry-run", action="store_true",
                        help="print what a live run would request and exit")
    parser.add_argument("--surveys", type=Path, default=SURVEYS_PATH)
    args = parser.parse_args(argv)

    survey = select_survey(load_surveys(args.surveys), args.module, args.cohort, args.kind)
    tags = content_tags(survey)
    identity = survey.get("identity_tags", [])
    embedded = [survey["condition_field"]] if survey.get("condition_field") else None
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if args.dry_run:
        print(f"survey: {survey['survey_id']} ({survey['title']})")
        print(f"would request tags: {', '.join(tags)}")
        print(f"embedded data: {embedded or 'none'}")
        print(f"identity tags never requested: {', '.join(identity) or 'none'}")
        return 0

    if args.input_csv:
        rows = drop_identity(finished_rows(response_rows(args.input_csv, set(tags))), identity)
        text = render_markdown(survey, rows, fetched_at, f"local file {args.input_csv.name}")
        write_outputs(text, args.output, os.environ.get("GITHUB_STEP_SUMMARY"))
        print(f"wrote {args.output} ({len(rows)} finished responses)")
        return 0

    if requests is None:
        sys.exit("requests is not installed; pip install -r requirements.txt")
    client = QualtricsClient(os.environ.get("QUALTRICS_API_TOKEN", ""),
                             os.environ.get("QUALTRICS_DATACENTER", ""))
    qids = tag_to_qid(client.fetch_definition(survey["survey_id"]), tags)
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = fetch_export(client, survey["survey_id"], Path(tmp),
                                list(qids.values()), embedded)
        rows = drop_identity(finished_rows(response_rows(csv_path, set(tags))), identity)
    text = render_markdown(survey, rows, fetched_at, f"Qualtrics {survey['survey_id']}")
    write_outputs(text, args.output, os.environ.get("GITHUB_STEP_SUMMARY"))
    print(f"wrote {args.output} ({len(rows)} finished responses)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
