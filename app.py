"""Password-gated web front end for the HDW survey reports (Streamlit).

Deployed on Streamlit Community Cloud from this repository. Secrets are set in
the Streamlit UI, never in git: APP_PASSWORD, QUALTRICS_API_TOKEN,
QUALTRICS_DATACENTER. Every click fetches responses live through report.py;
nothing is stored on the server and identity columns are never requested.
"""

from __future__ import annotations

import hmac
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1

import classview
import report

LABELS = {
    ("1", "en", "opener"): "Module 1 – opener (EN)",
    ("1", "en", "application"): "Module 1 – in-class (EN)",
    ("2", "en", "opener"): "Module 2 – opener (EN)",
    ("2", "en", "application"): "Module 2 – in-class (EN)",
    ("3", "en", "opener"): "Module 3 – opener (EN)",
    ("3", "en", "application"): "Module 3 – in-class (EN)",
    ("1", "nl", "opener"): "Module 1 – opener (NL)",
    ("1", "nl", "application"): "Module 1 – in-class (NL)",
    ("2", "nl", "opener"): "Module 2 – opener (NL)",
    ("2", "nl", "application"): "Module 2 – in-class (NL)",
    ("3", "nl", "opener"): "Module 3 – opener (NL)",
    ("3", "nl", "application"): "Module 3 – in-class (NL)",
}


def build_report(module: str, cohort: str, kind: str, token: str, data_center: str,
                 input_csv: Path | None = None) -> tuple[str, int, str]:
    """Return (markdown, n_finished, class_html). Mirrors report.main's live path."""
    survey = report.select_survey(report.load_surveys(), module, cohort, kind)
    tags = report.content_tags(survey)
    identity = survey.get("identity_tags", [])
    embedded = [survey["condition_field"]] if survey.get("condition_field") else None
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if input_csv is not None:
        rows = report.drop_identity(
            report.finished_rows(report.response_rows(input_csv, set(tags))), identity)
        source = f"local file {input_csv.name}"
    else:
        client = report.QualtricsClient(token, data_center)
        qids = report.tag_to_qid(client.fetch_definition(survey["survey_id"]), tags)
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = report.fetch_export(client, survey["survey_id"], Path(tmp),
                                           list(qids.values()), embedded)
            rows = report.drop_identity(
                report.finished_rows(report.response_rows(csv_path, set(tags))), identity)
        source = f"Qualtrics {survey['survey_id']}"
    return (report.render_markdown(survey, rows, fetched_at, source), len(rows),
            classview.render_class_html(survey, rows, fetched_at))


def password_ok() -> bool:
    if st.session_state.get("authed"):
        return True
    st.title("HDW survey reports")
    entered = st.text_input("Password", type="password")
    if entered and hmac.compare_digest(entered, st.secrets["APP_PASSWORD"]):
        st.session_state["authed"] = True
        st.rerun()
    if entered:
        st.error("Wrong password.")
    return False


def main() -> None:
    st.set_page_config(page_title="HDW survey reports", page_icon="📋", layout="wide")
    if not password_ok():
        return
    st.title("HDW survey reports")
    st.caption("Teaching team only. Each button fetches the current responses from "
               "Qualtrics; nothing is stored here and names are never requested.")
    available = report.load_surveys()
    view = st.radio("View", ["Class", "Instructor"], horizontal=True,
                    help="Class: counts only, projectable, opens as a slide page. "
                         "Instructor: every item plus the free-text answers.")
    cols = st.columns(2)
    choice = None
    for i, cohort in enumerate(("en", "nl")):
        with cols[i]:
            st.subheader("English (Monday)" if cohort == "en" else "Dutch (Wednesday)")
            for module in ("1", "2", "3"):
                for kind in ("opener", "application"):
                    key = f"{module}/{cohort}/{kind}"
                    label = LABELS[(module, cohort, kind)]
                    if st.button(label, key=key, disabled=key not in available,
                                 use_container_width=True):
                        choice = (module, cohort, kind)
    if choice:
        with st.spinner("Fetching responses from Qualtrics…"):
            try:
                text, n, page = build_report(*choice, st.secrets["QUALTRICS_API_TOKEN"],
                                             st.secrets["QUALTRICS_DATACENTER"])
            except Exception as exc:  # shown to the teacher, not logged with content
                st.error(f"Could not build the report: {exc}")
                return
        st.success(f"{n} finished responses")
        if view == "Class":
            st.download_button("Open as full-screen page (download HTML, then open it)",
                               page, file_name="class-view.html", mime="text/html")
            st.components.v1.html(page, height=720, scrolling=False)
        else:
            st.download_button("Download as Markdown", text, file_name="report.md")
            st.markdown(text)

if __name__ == "__main__":
    main()
