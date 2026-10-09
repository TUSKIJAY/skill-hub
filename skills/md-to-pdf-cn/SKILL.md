---
name: md-to-pdf-cn
description: Convert Markdown reports into polished Chinese-reading PDFs with reliable rendering for Chinese typography, Markdown tables, local SVG charts, local/external images, hyperlinks, appendices, and page-break quality. Use when Codex needs to turn .md files into external-facing Chinese PDF reports, optionally preserving an HTML intermediate and rendering PNG previews for visual QA.
---

# Markdown To Chinese PDF

## Overview

Use this skill to convert Markdown reports into A4 PDF documents suitable for Chinese reading and external presentation. Prefer the bundled script, which follows the stable route: Markdown -> Pandoc HTML -> Chrome/Edge headless PDF -> PyMuPDF PNG checks.

## Quick Start

Run from the skill folder or point to the script directly:

```bash
python scripts/md_to_pdf_cn.py input.md --output output.pdf --render-check --keep-html
```

Useful options:

```bash
python scripts/md_to_pdf_cn.py input.md ^
  --output output.pdf ^
  --image-profile normal ^
  --font-cn 宋体 ^
  --render-check ^
  --keep-html
```

## Workflow

1. Inspect the Markdown for local images/SVGs, external URLs, Markdown tables, long appendix tables, and link-heavy source sections.
2. Run `scripts/md_to_pdf_cn.py` with `--render-check` for any deliverable PDF.
3. Review the generated PNG previews with multimodal vision before delivery. Do not rely only on XML, extracted text, PDF metadata, or DOM inspection. At minimum visually inspect:
   - the first page
   - pages with many images
   - pages with SVG charts
   - pages with long tables or appendices
   - the final two pages
4. If pagination still has obvious orphan lines, awkward blank areas, or oversized media, adjust only the PDF-dedicated source/intermediate or CSS first. Do not alter the user's canonical Markdown unless they allow it.

## Mandatory Visual QA

Treat rendered-page visual review as part of the deliverable, not as an optional polish pass. After `--render-check` creates PNG previews, open the relevant pages with the available image/multimodal viewer and check what a human reader would see:

- Chinese font rendering, title hierarchy, paragraph indentation, and line spacing.
- Browser header/footer absence.
- SVG charts and local/remote images are visible, centered, and not oversized.
- Tables are centered, wrapped cleanly, and allowed to continue across pages without pushing whole appendices forward.
- No obvious large blank areas, clipped content, overlapping text, broken paths, or orphaned single lines.

Use XML/HTML/PDF text inspection only to diagnose specific issues after the visual pass finds a problem. A PDF is not accepted until the rendered pages have been visually checked.

## Rendering Rules

Use the default bundled CSS unless the user asks for a different house style:

- A4 page with controlled margins.
- Chinese body font: Songti/SimSun by default; English inherits or falls back to Times New Roman.
- Body text around 12pt with roughly 1.5 line height.
- H1 centered or visually prominent; H2 separated with a subtle rule.
- Chinese paragraphs use first-line indent of 2 characters.
- Tables are centered, single-line bordered, header light gray, wrapping enabled.
- Long tables may cross pages. Do not apply `break-inside: avoid` to the whole table.
- Prefer `tr { break-inside: avoid; }` so individual rows try not to split.
- Keep hyperlinks clickable through the HTML -> PDF route.
- Do not use browser default print headers/footers.

## Important Pitfalls

- If the HTML intermediate is not written beside the Markdown file, relative local SVG/image paths can break. Convert local Markdown image paths and HTML `<img src>` paths to absolute `file:///` URIs before Pandoc/Chrome.
- Chrome/Edge headless PDF printing should include:
  - `--no-pdf-header-footer`
  - `--virtual-time-budget=12000`
  - `--run-all-compositor-stages-before-draw`
- Do not set `break-inside: avoid` on normal paragraphs. Chinese paragraphs can be pushed wholesale to the next page, creating large blank regions.
- Do not set `break-inside: avoid` on entire tables. Long appendix/source tables may be pushed to the next page as one block.
- Size ordinary external/product images more compactly than SVG charts. Defaults:
  - compact raster: `max-width: 64%; max-height: 70mm`
  - normal raster: `max-width: 70%; max-height: 76mm`
  - large raster: `max-width: 75%; max-height: 86mm`
  - SVG charts: `max-width: 86%; max-height: 112mm`

## Alternative Routes

Keep Pandoc + Chrome/Edge headless as the default because it preserves modern HTML/CSS rendering, clickable links, SVG, remote images, and Markdown tables with relatively few dependencies. Consider alternatives only when the task has a specific need:

- **Pandoc + XeLaTeX/LuaLaTeX**: best when the user needs TeX-grade typography, strict academic templates, citations, or LaTeX math. It is less forgiving with complex HTML, remote images, and arbitrary SVG; Chinese font setup must be handled carefully.
- **WeasyPrint**: good for pure HTML/CSS pipelines and server-side automation. CSS paged-media support is strong, but browser-specific rendering, JavaScript-rendered content, and some SVG/CSS edge cases may differ from Chrome.
- **wkhtmltopdf**: useful on older systems, but based on an old WebKit engine. Avoid it for modern CSS, complex SVG, and precise Chinese report layout unless compatibility is already proven.
- **Typst**: strong for clean technical documents and programmable layouts. Use when the Markdown can be converted or rewritten into Typst structure; not ideal as a drop-in renderer for arbitrary Markdown with mixed HTML/image conventions.
- **Paged.js**: useful when CSS paged-media control is central and a browser preview loop is desired. It adds another transformation layer and should be tested carefully for tables and local assets.
- **PrinceXML/Antenna House**: best quality for enterprise publishing and complex paged media, but commercial. Use when available and the document requires production publishing controls.

## Script Notes

The bundled script:

- checks the input file exists
- creates a PDF-dedicated Markdown copy with local image/SVG paths rewritten to `file:///` URIs
- builds HTML using `pandoc --from gfm --to html5 --standalone`
- prints PDF using Chrome/Edge headless
- optionally renders page PNG previews using PyMuPDF
- prints the final PDF, HTML, and render-check paths

If Pandoc, Chrome/Edge, or PyMuPDF is unavailable, install or point to the missing tool. Use `--chrome-path` for a non-standard browser path and `--css` to append a custom CSS override.
