# OSUIT ABET File

A home-screen web app for the OSUIT Instrumentation & Automation ABET cycle **2026–2032**. It works like the Sports dashboard: open the link, then add it to your phone’s home screen.

**Live site:** https://michaelwilliams1589.github.io/abet-file/

## Privacy

This GitHub Pages site is public, but it is an **index only**. Meeting notes, rubrics, self-study files, and other accreditation documents are **not** in this repository. Every document link opens the file in your **private Google Drive**, and it only opens when you are signed in to the account that already has access.

Do not upload accreditation documents or named gradebooks here. De-identified score rows may be stored in `tools/assessment-aggregates.json` or `tools/assessment-scores.csv` (no names or IDs). The site includes `<meta name="robots" content="noindex, nofollow">` and a `robots.txt` that disallows all crawlers.

## Pages

- [Overview](index.html) — cycle status, quick links, open items, deadlines, recent log entries
- [Meetings](meetings.html) — notes by year (Y1–Y6), each card linking Drive notes and evidence
- [Assessment](assessment.html) — Assessment Hub latest and previous versions
- [Data](data.html) — de-identified grades, graphs, and student-outcome attainment
- [Self-study & review](self-study.html) — this cycle’s self-study, Year 3 interim review, outcomes / HLC
- [Running log](log.html) — append-only file log
- [Previous cycle](previous.html) — last cycle’s archived final files (the ETAC Self-Study is confidential and opens from Drive only)

## Install on your phone

**iPhone (Safari only)**

1. Open https://michaelwilliams1589.github.io/abet-file/ in **Safari**.
2. Tap the **Share** button (square with an up arrow).
3. Scroll down and tap **Add to Home Screen**, then **Add**.

**Android (Chrome)**

1. Open the site in **Chrome**.
2. Tap the **⋮** menu, then **Install app** (or **Add to Home screen**).

It then launches full screen from your home screen with its own icon. Drive links still need an internet connection and a signed-in Google account.

## Updating the index

When new material is added to the cycle folder and synced to Google Drive:

```bash
# From the repo root
# 1. Add new paths and Drive file IDs to tools/drive-map.json
#    (use each file’s webViewLink / id; do not change Drive sharing)
# 2. Update tools/meta.json if meetings, deadlines, or open items changed
# 3. For grades, add de-identified rows (no names or IDs) to
#    tools/assessment-aggregates.json or tools/assessment-scores.csv.
#    Keep any named gradebook only in the private Drive folder
#    03_Assessment_Hub/Data.
python3 tools/generate-data.py
git add data.js tools/drive-map.json tools/meta.json tools/log-snapshot.json tools/assessment-aggregates.json
git commit -m "Update ABET file index"
git push
```

`tools/generate-data.py` reads the local cycle folder (default `/workspace/abet/OSUIT_ABET_Cycle_2026-2032`) and the previous-cycle archive, joins them with `tools/drive-map.json` and `tools/assessment-aggregates.json`, and writes `data.js`. It never copies document files or student names into the site. Course/term sections with fewer than 5 assessed students are reduced to aggregates only (no score lists or histograms).

If you change HTML, CSS, or JS, bump `?v=N` on asset links in every HTML file, and bump `VERSION` / the `?v=N` entries in `sw.js`.

Run locally: `python3 -m http.server 8000` and open http://localhost:8000.

## Assessment data

The Data tab charts only anonymized scores. Send results as `course,term,assessment,outcome,score,max` rows. There are no attainment results in the current source files (outcome mapping, rubric, or previous-cycle Assessment Hub V30), so the tab starts empty until grades are sent.

Program criteria shown on the tab (70% individual threshold, 75% program target) come from the ETDE 3213 outcome mapping and are labeled as criteria, not measured results.

Raw files belong in the private Drive folder [03_Assessment_Hub/Data](https://drive.google.com/drive/folders/11ZFe8qPH4dtey6c-KfmlJitr_AIkYkte).

## Limitations

This is a web app, not an App Store or Play Store app. The public repo may be viewed by anyone with the link, so keep document content in Drive.
