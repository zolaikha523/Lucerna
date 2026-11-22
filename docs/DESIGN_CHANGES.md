# Design transformation: changes, acceptance results and limitations (22 Nov 2026)

Base: v3.1.0-alpha (git tag `v3.1.0-alpha`). The backup of the original is `Lucerna_backup_before_design_2026-11-22.zip`.
The version string stays `3.1.0-alpha`, because `lucerna/__init__.py` is in the protected file set. This release is
labelled "design transformation" in the package name.

## Engine protection
- Before any change, these were recorded in `docs/design_baseline/`: 88 protected files with their SHA-256, 70 passing
  tests, the project structure, and the configuration.
- **After all changes: 0 of 88 protected files changed, 0 removed, 0 added.** See
  `docs/test_evidence/protected_hashes_verify_2026-11-22.txt`. To re-check:
  `python tools/protected_hashes.py verify docs/design_baseline/protected_hashes.json`.
- The protected set covers all of `lucerna/` except `lucerna/ui/`. That includes:
  - ingestion, profiling, cleaning, statistics, KPIs, the engine, domain recognition, explanations and charts
  - AI and Ollama, qualitative analysis and quote verification
  - the database and migrations, security, reports and exports, and `app/*.py`
  - `requirements*.txt`, the `.bat` files, `.env.example`, and the original engine tests
- No protected file had to be changed, so there was nothing to stop and report.

## Modified files (presentation layer only)
**Changed:**
- `.streamlit/config.toml`: native dark navy theme, Inter font faces, chart colours
- `lucerna/ui/theme.py`: central tokens, motion, sign-in, sidebar, cards, light-interface layer, loader and skeletons
- `lucerna/ui/app.py`: sign-in layout with stacked logo, branded loading screen, page title and favicon
- `lucerna/ui/dash_theme.py`: dashboard canvas CSS built from the brand × theme tokens
- `lucerna/ui/pages/viewer.py`:
  - brand header (organisation logo, name, tagline, data-check indicator)
  - Design popover (theme and background)
  - KPI variants, readable titles, restyled charts
  - per-domain composition, skeletons
- `lucerna/ui/pages/studio.py`: *3 · Organisation branding* panel, and a *Branding* button on each dashboard
- `lucerna/ui/viz.py`, `lucerna/ui/pages/dashboards.py`: app charts use the same restyling and readable titles
- `assets/brand/*`, `app/static/*.svg|png`: the new Lucerna logo set
- `docs/BRAND_GUIDE.md`

**New:**
- `lucerna/ui/brand/` (`color.py`, `extract.py`, `svg_safe.py`, `design.py`, `store.py`)
- `lucerna/ui/brand_panel.py`, `lucerna/ui/viz_style.py`, `lucerna/ui/titles.py`, `lucerna/ui/composition.py`
- `tools/build_brand.py`, `tools/rasterize_brand.js`, `tools/protected_hashes.py`
- `tests/test_brand_design.py`, plus `tests/fixtures/logos/` (3 fictional logos and 1 malicious SVG, all marked SYNTHETIC)
- `docs/DESIGN_SYSTEM.md`, `docs/DESIGN_CHANGES.md`, `docs/design_baseline/`, and `docs/test_evidence/*2026-11-22*`

## Test results (run on 22 Nov 2026)
- Full suite: **91 passed**. That is the 70 original tests, unchanged and passing, plus 21 new tests with 32 subtests.
- The new tests cover:
  - extraction for 3 logos (green/orange PNG, blue/red JPEG, purple/gold SVG)
  - transparent, white and black pixels ignored
  - unsupported or oversized files rejected
  - malicious SVG cleaned, DOCTYPE and entities rejected
  - accessibility checks for every logo × theme
  - logos giving different identities, and the logo colour not used for everything
  - custom colour override and the monochrome fallback
  - readable titles for every visual type, with the technical title kept
  - restyling changes colours only, not trace data
  - composition shows every visual once in balanced rows, and domains get different layouts
  - two dashboards keep independent brands
  - the brand survives theme change, rename and duplicate
- Original workflows (quantitative, AI with the fake model, qualitative, quote verification, import and export) are
  covered by the unchanged original 70 tests, which pass.

## Browser acceptance (Playwright + Chromium against the running app)
- **A. App branding:**
  - new sign-in, sidebar logo, favicon, page title, loading screen, home and all pages
  - all hub sections opened with no exception (Data, Intelligence ×5, Studio ×3, Qualitative ×4, Mixed, Reports, Settings ×6)
  - light interface checked too
- **B. Organisation branding:** three dashboards were generated in Studio by uploading three different logos, with names
  and taglines, on three datasets: WASH with a green/orange PNG, displacement with a blue/red JPEG, food security with a
  purple/gold SVG.
  - Each shows its own logo, header gradient, tabs, KPI accents and chart palette.
  - A theme switch (Executive Dark → Corporate Light → back) kept the logo and the organisation name.
- **C. Rendering:** charts have transparent backgrounds, brand colours, readable titles with subtitles and bases, legends
  and tooltips. Presentation mode works, and so does a 430 px mobile width.
- **D. Motion:** entrance, hover and indicator animations run normally. Under `prefers-reduced-motion: reduce`, the
  measured animation duration is 0.000001 s.
- **E.** The original tests pass and the hash comparison is clean (see above).
- **Screenshots:** before/after pairs in the package folder `screenshots/` (login, home, Studio, Data Intelligence, and
  7 dashboards).

## Limitations
- **Exports:**
  - PDF, Word and PNG exports still use the engine's own chart palettes, because `static_charts` and the exporters are
    protected. Exports carry the organisation logo for PNG/JPEG logos, but not for SVG logos (screen only).
  - Workaround: upload a PNG version of the logo if it must appear in exports.
- **Colour fidelity:**
  - Brand colours are moved in lightness where needed for contrast or colour-vision safety. A bright logo colour can
    look darker in charts on light themes (for example, orange shown as burnt orange next to green). This is deliberate:
    readability wins over exact hex matching. The logo itself is never altered.
  - Two brands with similar primary hues (navy and deep purple) are told apart mainly by their secondary colours.
- **Titles:** they are rephrased from the specification and codebook labels only. A column name cut short in the source
  file (for example `q2_teaching_staff_were_appr`) is shown with "…", not completed.
- **No KPI trend arrows:** the engine's KPIs carry no comparison period. Trends are shown in the time-series charts instead.
- **defusedxml:** used when installed, but not added to `requirements.txt` (protected). The fallback is safe because
  DOCTYPE and ENTITY are rejected before parsing.
- **Light interface:** on top of the native dark theme, a few rarely used native widgets may keep dark details in light
  mode. Dark is the designed default.
- **Accessibility scope:** contrast and colour-vision checks are computed (WCAG 2.x formulas, Viénot/Brettel simulation).
  This is not a formal accessibility certification.
- **Trademark:** no trademark search was made for the Lucerna name or symbol.
