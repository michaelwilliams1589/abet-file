# Sync grade entries into the ABET File app

Colleagues enter de-identified scores in the private Google Sheet
[ABET Grade Entry 2026-2032](https://docs.google.com/spreadsheets/d/1l4mC0G79gxgYAUDLIt2pdAkCysvghoiehCBnRROwRAk/edit)
(in [03_Assessment_Hub/Data](https://drive.google.com/drive/folders/11ZFe8qPH4dtey6c-KfmlJitr_AIkYkte)).
This procedure pulls both the **Entry** tab (whole-class paste) and any **Form Responses** tab
(one-at-a-time form submissions, if a Form has been linked), validates the rows, updates
`tools/assessment-scores.csv` and `data.js`, and pushes to GitHub Pages only when something
changed.

Do not change Drive sharing. Do not copy student names or IDs into the repo.

A Google Form was **not** created automatically: the Google Drive connector has no Forms API
tools. If Michael later creates a Form and links its responses to this spreadsheet, add the
form URL to `tools/sheet-config.json` (`formUrl`) and to the Data tab buttons, then keep
following this same procedure. Google may name the destination tab `Form Responses 1`; the
pull script accepts any tab whose name starts with `Form Responses`.

## Scheduled run (executor / agent)

Config: `tools/sheet-config.json` (spreadsheet id and tab names).

1. **Read the live tabs** with the `user-Google-drive` MCP tool `sheets_read_range`:
   - spreadsheetId: `1l4mC0G79gxgYAUDLIt2pdAkCysvghoiehCBnRROwRAk`
   - ranges: `{sheet: "Entry", cells: "A1:H2000"}` and every tab whose title starts with
     `Form Responses` (use `sheets_get_spreadsheet` first if you need the current tab list).
   - Save each tab’s CSV to `tools/sheet-exports/` (gitignored). Suggested names:
     `entry.csv`, `form-responses.csv`, `form-responses-1.csv`, …
   - If MCP read is unavailable, `export_file` with `format: "csv"` only exports the **first**
     visible tab, so do not rely on it when Entry is not first. Prefer `sheets_read_range`.

2. **Validate and merge** (repo root `/workspace/abet-app` or a clone of
   `michaelwilliams1589/abet-file`):

   ```bash
   python3 tools/pull-sheet.py --dir tools/sheet-exports
   python3 tools/generate-data.py
   ```

   `pull-sheet.py` rejects rows with name-like or ID-like text in score fields, out-of-range
   scores, or missing required values. It never writes names, IDs, or `entered_by` into
   `tools/assessment-scores.csv`. A report is written to `tools/pull-sheet-report.json`
   (counts and reason codes only; also gitignored).

3. **Push only if the published files changed:**

   ```bash
   git add data.js tools/assessment-scores.csv
   git diff --cached --quiet || {
     git commit -m "Update assessment charts from grade entry sheet"
     git push origin main
   }
   ```

   If HTML/JS also changed, bump `?v=N` and `sw.js` `VERSION` as usual.

4. GitHub Pages updates in about a minute. Installed apps pick up the new `data.js` after a
   refresh (network-first for pages).

## Local check without pushing

```bash
python3 tools/pull-sheet.py --dir tools/sheet-exports
python3 tools/generate-data.py
```

## Adding a Form later

1. Michael creates the Form (see the Instructions tab of the Sheet) and links Responses to
   this existing spreadsheet.
2. He shares the form link (not the editor link) with colleagues and with Chief BOT.
3. Put that URL in `tools/sheet-config.json` as `formUrl`, add or enable the Data tab
   “Enter grades (Form)” button, commit, and push.
4. No other sync changes are required.

## Sharing (Michael does this)

- Sheet: share with colleagues as **Editors** (or share the link only with specific faculty
  accounts). Do not make it public if a file might contain names.
- Form (once created): share the **form** link so colleagues can submit without editing the
  Sheet.
