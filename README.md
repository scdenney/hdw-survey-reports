# hdw-survey-reports

One-click reports on the in-class Qualtrics surveys of the HDW Data module
(Leiden University, Humanities in a Digital World). For the two teachers only.

## Run a report

1. Open the Actions tab and choose "Survey report".
2. Click "Run workflow" and pick the module (1, 2, 3), the cohort (en, nl)
   and the survey (opener, application).
3. Open the run once it finishes. The report is on the run page, under the
   job summary. The same file is attached as an artifact for seven days.

The report gives, for each closed item, a count table in the order the
survey shows the answers, and for each free-text item every answer verbatim
in random order. The Module 2 opener also shows its two randomised arms
side by side.

## Who sees what

The repository is private, so only its collaborators can run the workflow or
read a report. Runs use the Qualtrics token stored in the repository
secrets, whoever clicks the button.

Identity columns (first name, last name, student number) are never
requested from Qualtrics: the export asks only for the content and
free-text questions, and the script drops and reports any identity column
that arrives anyway. Consent items are neither requested nor shown.

There is no suppression of small counts, because the audience is the two
teachers and not the class. All finished responses are included regardless
of the aggregate-reuse choice, which governs what is kept after class, not
same-day teaching use. Nothing response-level is written to git; the report
exists only on the run page and in the artifact.

## Before the first live run

Two settings in the GitHub UI:

- Settings, Secrets and variables, Actions: add `QUALTRICS_API_TOKEN` and
  `QUALTRICS_DATACENTER` (value `fra1`).
- Settings, Actions, General: set artifact and log retention to 7 days, so
  the seven-day deletion rule for opener responses is enforced by the
  platform. The workflow also sets `retention-days: 7` on the artifact.

Add the co-teacher as a collaborator under Settings, Collaborators.

## Configuration

`surveys.json` maps `module/cohort/kind` to a survey ID and its items. Only
the English (`en`) surveys exist so far; the Dutch entries are added when
the `_nl` surveys are built. A survey rebuilt with `--rebuild` in the `hdw`
repository gets a new ID, which must be updated here by hand.

Module 1 application labels are marked `labels_pending` until the final
specs land; any answer not in the list is appended to the table as
"(unlisted)" rather than dropped.

## Local use

The script runs without the API against an existing export:

```
python3 report.py --module 2 --cohort en --kind opener \
  --input-csv tests/fixture_export.csv --output /tmp/report.md
```

`--dry-run` prints the survey and the tags a live run would request, with
no network call. `python3 -m unittest discover -s tests` checks the renderer
against the fixture, including that identity values never reach the output.
