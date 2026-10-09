---
name: research-report-builder
description: Build general-purpose research reports from Deep Research material packages into source-grounded Markdown reports with semantic SVG visuals and curated image references. Use when Codex needs to create 通用调研报告, industry research, company research, technology research, policy research, competitor research, market-entry research, thematic analysis, research report prompts, Deep Research material collection prompts, or Markdown-only report assembly with charts/images. For broad requests like "调研一下某行业/公司", first align direction, scope, reader, depth, and report angle before generating the Deep Research prompt. Do not use for stock/security investment decisions, portfolio/position reviews, or document format conversion.
---

# Research Report Builder

## Core Stance

Use this skill as a **general research report production workflow**. It is distinct from investment/security research skills: it does not make trading decisions, portfolio decisions, position reviews, or K-line judgments.

Separate the work into three layers:

1. **Deep Research material layer**: collect facts, source-linked claims, data, disagreements, unknowns, image leads, and visualization opportunities.
2. **Agent synthesis layer**: decide the report structure, evidence weighting, conclusions, caveats, and final narrative.
3. **Markdown assembly layer**: produce one Markdown report that references generated SVG files and curated images when useful.

Deep Research is the material collector. The agent is the author, analyst, and final decision maker for the report.

## Hard Boundaries

- Output only Markdown as the final report format.
- Do not include or perform HTML, PDF, Word, PPT, or image-to-document conversion.
- Do not add conversion scripts to this skill.
- If the user asks for another output format, finish the Markdown report first and hand off conversion to an appropriate document/presentation/PDF skill.
- Do not fabricate data, images, citations, or visual evidence.
- Do not treat Deep Research output as final judgment. Treat it as an evidence package.
- Do not use this skill for listed-asset buy/sell/hold decisions; use the target/security research workflow instead.
- Do not accept SVGs based only on XML/path checks. Render generated SVGs and perform multimodal visual QA before inserting them into the final Markdown.

## Default Stage Gates

Default to a stage-gated workflow unless the user explicitly provides both the research materials and asks for final assembly.

0. For broad or underspecified requests, first run a short scope-alignment dialogue.
1. First deliverable: produce an intent card and a copy-ready Deep Research prompt.
2. Stop after the prompt by default and ask the user to return the Deep Research output.
3. Continue only when the user provides research materials, asks Codex to run the external research itself, or explicitly asks to skip the Deep Research pass.
4. Final deliverable: one Markdown report plus any referenced local assets such as `charts/*.svg`, `images/*`, and `assets/*-manifest.md`.

## Workflow

### 0. Align Scope

When the user only says something broad such as "调研一下 X 行业", "研究一下 X 公司", or "做一份 X 主题报告", do not immediately generate the Deep Research prompt.

First give a brief understanding of the likely report direction, then ask only the smallest useful set of questions. Prefer these dimensions:

- purpose: what decision or understanding the report should support;
- target reader: founder, investor, product team, sales team, policy team, general reader, or other;
- scope: geography, timeframe, sub-sector, company/product boundary, or competitors;
- depth: quick brief, standard report, or deep report;
- angle: market size, competitive landscape, technology route, policy, business model, risks, opportunities, or custom angle.

Ask at most five concise questions. If the user says to proceed with defaults, state the assumptions and continue to the intent card and Deep Research prompt.

Skip scope alignment when the user already provides clear scope or explicitly asks for the prompt/report directly.

### 1. Recognize Intent

Classify the request before writing prompts or reports:

- `industry_research`
- `company_research`
- `technology_research`
- `policy_research`
- `competitor_research`
- `market_entry_research`
- `thematic_analysis`
- `custom_research_report`

Capture an intent card with:

- `report_type`
- `topic`
- `target_reader`
- `research_scope`
- `geography`
- `time_horizon`
- `required_depth`
- `known_constraints`
- `output_language`
- `final_format: Markdown only`

Ask only for information that is truly necessary. If the user wants to proceed with unknowns, mark them explicitly.

### 2. Generate Deep Research Prompt

Use `assets/deep-research-prompt-template.md` as the base when producing the copy-ready prompt.

The prompt must instruct Deep Research to:

- collect facts, data, source-linked claims, timelines, key entities, and viewpoints;
- cite sources with publication dates and retrieval dates where possible;
- distinguish facts, estimates, assumptions, third-party opinions, and unknowns;
- identify disagreements and evidence quality;
- collect image leads and visualization opportunities;
- avoid final conclusions, recommendations, investment language, or decisive strategic choices.

After returning the prompt, stop and ask the user to run it in their Deep Research tool and bring back the output.

### 3. Intake Research Materials

Proceed only after materials are available or the user explicitly skips the external pass.

Extract a structured evidence package using `assets/evidence-pack-template.md`:

- facts and claims;
- data points and tables;
- source quality and freshness;
- stakeholders and entities;
- timelines;
- supporting and opposing views;
- uncertainties and missing data;
- image leads;
- visualization candidates.

Reject unsupported claims or move them to `未证实信息`. Preserve source links.

### 4. Synthesize The Report

Use the evidence package to build the final argument. The agent must make the final choices:

- core thesis and framing;
- chapter order;
- which evidence matters most;
- what conclusions are justified;
- what remains uncertain;
- which visuals/images belong in the report.

Use `assets/report-template.md` as the default structure, adapting headings to the report type.

The report voice should be analytical, source-grounded, and readable. Avoid process-log language such as repeated mentions of "Deep Research" in the main body; keep provenance details in the appendix.

### 5. Plan Visuals And Images

Use `assets/visual-plan-template.md` before creating or inserting visual assets.

SVG visuals should clarify the argument, not decorate the page. Prefer:

- industry chain maps;
- technology route maps;
- competitive landscape diagrams;
- timelines;
- business model diagrams;
- policy impact paths;
- risk matrices;
- data comparison charts when source data exists.

Rules:

- Data charts require traceable data.
- Conceptual SVGs must be labeled as agent synthesis based on cited materials.
- If evidence is insufficient, write the missing data under `缺失数据` instead of inventing a visual.
- Save generated SVGs under `charts/` and reference them with relative Markdown links.

For images:

- Prefer official, user-provided, public-domain, licensed, or clearly attributable sources.
- Save only images the user has rights to use or that are appropriate for local report drafting.
- When rights are unclear, reference the source URL in the image manifest and note the usage risk.
- Every image must have a caption, source, insertion point, and reason for inclusion.
- Use `assets/image-manifest-template.md` for tracking.

### 6. Validate SVGs Multimodally

Before inserting any generated SVG into the report, render or open it as an actual visual artifact and inspect it with multimodal vision. XML validity is necessary but not sufficient.

Validate each SVG for:

- nonblank rendering;
- correct framing and viewport;
- readable Chinese and English text;
- no overlapping labels, clipped nodes, or hidden arrows;
- visual hierarchy that matches the report argument;
- source/data labels present where required;
- accurate semantic mapping to the evidence and caption;
- acceptable appearance in Markdown context.

If a rendered SVG fails visual QA, revise and re-render it until it passes. Temporary screenshots or render artifacts may be created for validation only; do not treat them as report deliverables or format exports.

If the environment cannot render or visually inspect SVGs, state that limitation clearly and do not claim multimodal validation was completed.

### 7. Assemble The Markdown Report

Create the final report as `<topic-slug>-research-report-<YYYY-MM-DD>.md` unless the user provides a name.

The Markdown report may reference:

- `charts/*.svg`
- `images/*`
- `assets/evidence-pack.md`
- `assets/visual-plan.md`
- `assets/image-manifest.md`

Do not create HTML/PDF/Word/PPT exports.

Every final report should include:

- title and date;
- executive summary;
- key conclusions with confidence/caveats;
- structured analysis chapters;
- embedded SVGs/images where they help understanding;
- risks, uncertainties, and missing data;
- source and evidence appendix;
- note that the report is research-process support, not a substitute for professional advice where applicable.

## Resources

- `references/workflow.md`: detailed workflow contracts and quality checklist.
- `assets/deep-research-prompt-template.md`: copy-ready material collection prompt template.
- `assets/evidence-pack-template.md`: structure for turning research output into evidence.
- `assets/report-template.md`: Markdown-only final report template.
- `assets/visual-plan-template.md`: SVG and image planning template.
- `assets/image-manifest-template.md`: image source and usage tracking template.
