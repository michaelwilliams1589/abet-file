# OSUIT ABET File

A home-screen web app for the OSUIT Instrumentation & Automation ABET cycle **2026–2032**. It works like the Sports dashboard: open the link, then add it to your phone’s home screen.

**Live site:** https://michaelwilliams1589.github.io/abet-file/

## Privacy

This GitHub Pages site is public, but it is an **index only**. Meeting notes, rubrics, self-study files, and other accreditation documents are **not** in this repository. Every document link opens the file in your **private Google Drive**, and it only opens when you are signed in to the account that already has access.

Do not upload `.docx`, `.pdf`, evidence `.html`, `.txt`, `.xlsx`, or `.csv` accreditation files here. The site includes `<meta name="robots" content="noindex, nofollow">` and a `robots.txt` that disallows all crawlers.

## Pages

- [Overview](index.html) — cycle status, quick links, open items, deadlines, recent log entries
- [Meetings](meetings.html) — notes by year (Y1–Y6), each card linking Drive notes and evidence
- [Assessment](assessment.html) — Assessment Hub latest and previous versions
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
python3 tools/generate-data.py
git add data.js tools/drive-map.json tools/meta.json tools/log-snapshot.json
git commit -m "Update ABET file index"
git push
```

`tools/generate-data.py` reads the local cycle folder (default `/workspace/abet/OSUIT_ABET_Cycle_2026-2032`) and the previous-cycle archive, joins them with `tools/drive-map.json`, and writes `data.js`. It never copies document files into the site.

If you change HTML, CSS, or JS, bump `?v=N` on asset links in every HTML file, and bump `VERSION` / the `?v=N` entries in `sw.js`.

Run locally: `python3 -m http.server 8000` and open http://localhost:8000.

## Limitations

This is a web app, not an App Store or Play Store app. The public repo may be viewed by anyone with the link, so keep document content in Drive.
