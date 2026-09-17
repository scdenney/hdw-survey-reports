# hdw-survey-reports

Reads the in-class Qualtrics surveys of the Data module of *Humanities in a
Digital World* (Leiden University) and renders a short report for the
teaching team: a count table per closed item and the free-text answers
verbatim, in random order.

Two front ends share one script, `report.py`:

- `app.py`, a small Streamlit site behind a password at
  https://hdw-reports.streamlit.app, one button per survey, with a Class view
  (counts only, projectable) and an Instructor view (plus free text).
- `.github/workflows/report.yml`, a manual GitHub Actions run with the same
  choices (module, cohort, survey); the report appears on the run page and as
  a seven-day artifact.

## Privacy

The export asks Qualtrics only for the content questions. Identity columns
(first name, last name, student number) are never requested, and the script
drops and flags any that arrive. Consent items are not reported. Nothing
response-level is stored: the site renders in memory, the workflow writes
only to the run page and a short-lived artifact, and no report is ever
committed here.

## Configuration

`surveys.json` maps `module/cohort/kind` to a Qualtrics survey ID and its
items. Credentials are never in the repository: the site reads
`APP_PASSWORD`, `QUALTRICS_API_TOKEN` and `QUALTRICS_DATACENTER` from its
secrets, and the workflow reads the last two from repository secrets.

## Local use

```
python3 report.py --module 2 --cohort en --kind opener \
  --input-csv tests/fixture_export.csv --output /tmp/report.md
python3 -m unittest discover -s tests
```

`--dry-run` prints what a live run would request, without a network call.
The fixture is synthetic.
