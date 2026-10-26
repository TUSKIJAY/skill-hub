# Project adaptation

Keep the core invariant: intent, inputs, outputs, authoritative evidence, side-effect scope, resumable state. Software is one overlay, not the default ontology. `minimal` / `governed` selects governance, never domain or use/maintain mode.

Use existing materials to populate INSTRUCTIONS Use Contract. Do not create a separate workflow file unless an actual missing procedure requires one. `--project-type` is a description, not a new profile. `--workflow-entry` records an existing entrypoint; acceptance checks are repeatable free-text declarations, not executable shell.

| Domain | Typical existing entry | Suitable acceptance evidence |
| --- | --- | --- |
| Software | documented command or development guide | relevant tests/build, actual runtime result |
| Research | research brief, source index, research procedure | claims traced to sources, scope coverage, unknowns separated |
| Documents | template and editing/rendering procedure | output opens/renders, required content and source fidelity |
| Planning/operations | itinerary, SOP, input sheet | dates/totals/constraints checked, external receipt when authorized |

No executable verification inferred is a normal state. Use `--acceptance-check` for source comparison or human inspection. Do not invent npm/pytest/CI or require Git. Helper scripts are infrastructure, not evidence that the project is software. If no credible acceptance method is known, mark it unresolved; structural success is not completion.

Use mode may write outputs, update declared inputs/run parameters and record results; it cannot silently rewrite workflow definitions, policy or acceptance criteria. Maintenance mode may change those within user authorization and then exercise the workflow. Mode is not an account role: the same person can request both. For actual multi-user restrictions use existing filesystem/service permissions; a Markdown route alone cannot enforce access control.

When the user asks for a result but no usable workflow is wired yet, report that concrete missing entry; do not silently turn the request into a framework-building project. Directly completing the authorized result using available materials is still allowed when feasible.
