# Lucerna Design System and Brand-Aware Dashboards (design transformation, 22 Nov 2026)

This release changes only how Lucerna looks. The analytical engine was protected by file hashes before work started, and
those hashes were compared again at the end. Result: **0 of 88 protected files changed** (`docs/design_baseline/`).

## 1. Three independent systems
| System | What it controls | Where |
|---|---|---|
| **A. Lucerna application theme** | sign-in, sidebar, navigation, every app page, forms, tables, dialogs, loading | `.streamlit/config.toml`, `lucerna/ui/theme.py` |
| **B. Organisation brand (per dashboard)** | logo, organisation name, tagline, colours read from the logo, background choice | `lucerna/ui/brand/`, saved in each dashboard's `branding_json` |
| **C. Visualization theme (per dashboard)** | light or dark base, background family, radius and density | the dashboard's theme (Corporate Light, Executive Dark, Modern Vibrant, Research & Minimal) |

`brand.design.build(logo colours, theme, custom colours, background)` merges B and C into one token set. If you change the
theme, the logo and its colour system stay. If you change the logo, the theme stays. System A never leaks into a dashboard:
the dashboard canvas hides the app sidebar and header.

## 2. Application tokens (system A)
- **Colour roles:** navy background (#070D1C to #0B1530), glass surfaces (rgba 20,31,58,.62 with 10–14 px blur), ink #EEF3FB,
  secondary ink #C3CEDF, muted #8E9CB5, hairlines rgba(255,255,255,.08), azure #2F6BFF, teal #16C2B0, violet #8B6CFF,
  spark #FFC56B. A light interface is available from the account menu.
- **Type scale:** display 2.05rem · h1 1.6 · h2 1.32 · h3 1.05 · body .94 · small .82 · micro .72. The font is Inter, with
  Vazirmatn for Arabic script.
- **Spacing:** 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 px. **Radius:** 8 / 12 / 16 / 22 px and pill.
- **Elevation:** one soft shadow per mode, plus a 1 px inner highlight on dark surfaces.
- **Motion:** fast 120 ms, base 200 ms, slow 420 ms, easing cubic-bezier(.2,.7,.2,1).
- **Chart defaults:** transparent paper and plot, a recessive grid, Inter 12 px, tooltips on a solid surface.

## 3. Organisation brand intelligence (system B)
1. **Upload:** in Studio, under *3 · Organisation branding* (new dashboards) and *My dashboards › Branding* (existing ones).
   Accepted formats: PNG and JPEG (under 1 MB, stored through the existing logo service so PDF and Word exports keep them)
   and SVG (under 2 MB). The organisation name, tagline, title, subtitle, background and up to three custom colours are
   optional.
2. **Safety:** each file is identified by its signature bytes, not its file name.
   - Raster images are decoded by Pillow. Oversized images are rejected.
   - An SVG is parsed with defusedxml, so DTDs, entities and external references are forbidden. The following are removed:
     scripts, `foreignObject`, iframes, embeds, animation elements, `on*` handlers, external `href`s, CSS `url()` and
     `@import`.
   - Logos are shown only as `<img>` data URIs, where browsers never run scripts.
   - Only a random file name is stored, never a path. Files live in `data_dir/branding/`.
   - Background photos are re-encoded as metadata-free JPEG, at most 1920 px.
3. **Extraction (deterministic, no AI):** `brand/extract.py`.
   - Transparent pixels (alpha below 128) are ignored. Near-white, near-black and grey pixels (OKLCH chroma below 0.035)
     are counted as neutrals.
   - The remaining pixels are grouped by perceptual hue and lightness, and similar groups are merged (OKLab ΔE below 7).
   - Each colour's share of the coloured area is reported, along with a plain "visual character" (warm/cool, vivid/muted,
     single-hue/multicolour).
   - SVG colours come from fill, stroke and stop-color, weighted by shape size.
   - Results are cached. Colours are never guessed from an organisation's name.
4. **Design system from the logo:** `brand/design.py`. The rules are written in the module docstring:
   - **Roles:** the dominant colour is the primary. The secondary is the next colour at least 25° away in hue. The accent
     is at least 40° from both. A missing role is derived: an analogous colour, or a split-complement placed away from the
     secondary. A monochrome logo gets a restrained slate-and-blue system instead of invented colours.
   - **Not applied blindly:**
     - Logo colours give the identity (header gradient, tabs, highlights, the first series in each chart).
     - Backgrounds are deep or near-white neutrals, only tinted toward the brand hue.
     - Chart colours keep each brand hue but are moved into a lightness and chroma band that reads well on the chosen
       background. Further series use the hues farthest from the brand hues.
   - **Checks on every palette:** these are shown in the Studio under *Accessibility checks* and tested for all 3 test
     logos × 4 themes:
     - main text contrast at least 7:1
     - secondary text at least 4.5:1
     - muted text and controls at least 3:1
     - every chart colour at least 3:1 against its card
     - neighbouring chart colours at least ΔE 14
     - the same pair at least ΔE 8 under simulated protanopia, deuteranopia and tritanopia
   - **Outputs:** primary, secondary, accent, background, surface, text (three levels), borders, grid, status (good,
     warning, negative), and categorical (8), sequential (7) and diverging (7) chart palettes.
5. **Where the brand appears:**
   - header (logo chip, organisation, title, tagline) and its gradient
   - tabs, filter focus rings and tags
   - KPI cards (accent lines, rings, meters, icons)
   - every chart's colours, legends and tooltips
   - insight cards and quality indicator
   - background glows and the page background
6. **Persistence:** everything is stored in the dashboard's existing `branding_json`, so no schema change was needed. The
   brand therefore survives save, reopen, rename, duplicate (Duplicate copies branding), theme change, presentation mode
   and refresh. Each dashboard has its own brand. Tests: `tests/test_brand_design.py`.

## 4. Dashboard rendering (presentation only)
- **Charts:** `ui/viz_style.py` post-processes the figure from the protected `charts.figure`.
  - It swaps each engine palette colour, slot for slot, for the brand palette.
  - It makes paper and plot transparent, applies a subtle grid, brand tooltips and a donut hole, and puts a soft area
    under single trend lines.
  - It makes axis titles readable.
  - Data, categories, order, scales and hover values are unchanged. A test compares the trace data before and after.
- **Titles:** `ui/titles.py`.
  - Each chart gets a question-style title from its own specification and the codebook labels, plus a subtitle that
    explains the measure, the denominator and how to read the chart.
  - Cut-off column names are shown with "…", never completed by guessing.
  - The engine's title is kept under *Insights, method & limitations › Source & methodology*.
  - The computed, verified finding from `explain` appears under the title. A claim only appears with its evidence.
- **Composition:** `ui/composition.py`. Each domain gets a layout profile:

  | Domain | Layout | KPI style |
  |---|---|---|
  | Displacement | flow-led | KPI strip |
  | WASH | service-coverage | ring gauges for percentages |
  | Food security | distribution-led | meters, findings below |
  | Cash/MPCA | delivery-and-outcome | — |
  | PDM | satisfaction-led | — |
  | Market | trend-led | — |
  | Research | evidence-led | inline figures, findings below |
  | Protection / needs | needs-led | — |

  The profile picks the lead ("hero") chart, the reading order and balanced row widths. Every visual in the page spec is
  shown exactly once, and no empty section is created. Trend arrows are not shown on KPI cards, because KPIs carry no
  comparison period. Trend information stays in the time-series charts, where the comparison is valid.
- **Backgrounds:**
  - executive dark navy
  - deep blue-teal
  - violet-blue
  - subtly branded (from the logo)
  - premium light neutral
  - quiet paper
  - your own photo, behind a readability veil

## 5. Motion
CSS only. There is no JavaScript animation, timer or extra rerun.
- **Entrances:** cards and KPIs rise in with a short stagger, and charts fade in.
- **Hover and press:** lift, border glow and press scale.
- **Navigation and tabs:** an indicator and a fade.
- **Other:** dialogs rise, filter tags pop in, KPI rings and meters fill once, and the header gradient drifts slowly.
- **Loading:** a branded loader (the symbol's light pulses) and skeleton placeholders. Skeletons appear only while a
  visual is really being computed, not on every rerun.
- **Reduced motion:** `prefers-reduced-motion: reduce` switches all of it off. This was verified in the browser: animation
  durations become 0.000001 s.

## 6. Requirements
No new required dependencies. Pillow and Plotly were already required. defusedxml is used for SVG parsing when it is
installed. It is not added to `requirements.txt`, because that file is in the protected set. Without it, the
standard-library parser is used, and this is still safe because DOCTYPE and ENTITY declarations are rejected before
parsing (tested both ways). Fonts are bundled. Nothing calls a paid API,
and Ollama is untouched. Everything works offline on Windows.
