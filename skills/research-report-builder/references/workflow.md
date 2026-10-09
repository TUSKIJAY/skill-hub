# Research Report Builder Workflow

## Purpose

Create source-grounded Markdown research reports from research materials. Keep the skill focused: collect materials, synthesize evidence, generate useful SVG visuals, curate images, and assemble a Markdown report. Do not convert the report into other document formats.

## Stage 0: Scope Alignment

Use this stage when the user gives only a broad topic, such as "调研一下机器人行业" or "研究一下某公司".

Ask a small number of questions before generating the Deep Research prompt. Keep the exchange light and decision-oriented:

- What should the report help decide or understand?
- Who is the target reader?
- What geography, timeframe, sub-sector, company boundary, or competitor set matters?
- Should this be a quick brief, standard report, or deep report?
- Which angle matters most: market, competition, technology, policy, business model, risks, opportunities, or something else?

If the user does not want to answer, proceed with explicit assumptions and mark missing inputs in the intent card.

## Stage 1: Intent Card

Use this shape before generating prompts or reports:

```yaml
report_type:
topic:
target_reader:
research_scope:
geography:
time_horizon:
required_depth:
known_constraints:
output_language:
final_format: Markdown only
missing_inputs:
```

## Stage 2: Deep Research Material Prompt

The first-stage prompt should produce a material package, not a report. Require:

- source-linked factual claims;
- data tables with source and period;
- timeline of relevant events;
- major stakeholders/entities;
- supporting and opposing viewpoints;
- evidence quality notes;
- unknowns and information gaps;
- image leads with URLs and captions;
- visualization opportunities.

Ban final recommendation language such as "therefore should", "best choice", "buy/sell", "enter/exit", or decisive strategic instructions. If a source expresses a recommendation, attribute it as a source opinion.

## Stage 3: Evidence Intake

Classify every important item into one of these buckets:

- verified fact;
- estimate/model output;
- source opinion;
- contested claim;
- unknown/missing data;
- obsolete or stale information;
- image lead;
- visualization candidate.

Prefer recency checks for topics that change quickly. Mark publication date and retrieval date when available.

## Stage 4: Synthesis

The agent owns the report. It should:

- identify the main question the report answers;
- choose the report structure;
- weigh evidence quality;
- reconcile conflicting sources;
- state confidence and caveats;
- separate conclusion from source opinion;
- keep unsupported material out of the main argument.

## Stage 5: Visual Assets

Use visuals only when they improve comprehension.

### SVG Types

- `data_chart`: requires explicit data source and date range.
- `concept_map`: agent synthesis from cited materials.
- `timeline`: events must have dates and sources.
- `matrix`: criteria and placement logic must be stated.
- `flow_diagram`: relationships must be supported by cited material or clearly labeled as synthesis.

### SVG Caption Rule

Every SVG caption should state:

1. what the reader should learn;
2. whether it is data-derived or synthesis-derived;
3. the data/source basis.

### Multimodal SVG Validation

Do not approve generated SVGs from XML, path, or Markdown syntax checks alone. Before inserting them into the final report:

1. Render/open the SVG as a visual artifact.
2. Inspect it with multimodal vision.
3. Check that it is nonblank, framed correctly, readable, unclipped, and free of label/arrow overlap.
4. Check that the visual structure matches the evidence and the caption.
5. Revise and re-render until it passes.

Temporary screenshots or rendered previews may be used for validation only. They are not report deliverables and do not count as HTML/PDF/Word/PPT conversion.

If visual rendering is unavailable, record the limitation and avoid claiming that the SVG passed multimodal QA.

## Stage 6: Images

Images are evidence or semantic aids, not decoration. For each image, track:

- local path or source URL;
- title/caption;
- source;
- rights/usage note;
- report insertion point;
- reason it belongs in the report.

If rights are unclear, keep the URL in the manifest and avoid embedding a downloaded local copy unless the user approves.

## Final Markdown Quality Checklist

- The final artifact is Markdown only.
- The report answers a clear research question.
- Major claims have sources or are labeled as synthesis.
- Source opinions are attributed.
- Uncertain information is not written as fact.
- SVGs have captions, are referenced with relative links, and passed rendered multimodal visual QA.
- Images have source/usage tracking.
- Missing data is explicit.
- No HTML/PDF/Word/PPT export is created.
