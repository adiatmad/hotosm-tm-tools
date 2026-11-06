# Agent instructions

Inspect the README, source code, tests, configuration, and current repository state before editing.

## Product and geospatial constraints

- This is a Streamlit utility for splitting GeoJSON geometry into polygons with a target maximum area of 5,000 km².
- Preserve the documented geometry pipeline: merge input geometries, reproject to equal-area EPSG:6933 for area-based splitting, split recursively, and export GeoJSON.
- Never calculate area in an unsuitable geographic CRS or silently assume an input CRS. Validate geometry and coordinate assumptions before processing.
- Do not silently discard features, properties, holes, or geometry parts. Preserve provenance and explain any intentional normalization.
- Output polygons are suggestions for a Tasking Manager workflow. The user must inspect them before use; do not claim that generated splits are automatically valid for upload.
- Keep uploaded data local to the processing workflow. Do not add telemetry or external uploads.

## Required engineering workflow

1. Inspect the current code path, dependencies, test fixtures, and existing behavior before editing.
2. For non-trivial changes, define the user outcome, scope, non-goals, constraints, risks, and testable acceptance criteria in a project spec.
3. Use vertical red-green-refactor slices. Test geometry behavior with representative fixtures, including multipart, invalid, empty, and boundary cases where relevant.
4. For bugs, reproduce with a minimal GeoJSON fixture, minimise the failing geometry, test falsifiable hypotheses, and add regression coverage at the correct public seam.
5. Prefer the smallest coherent change, explicit coordinate/area semantics, and minimal dependencies. Avoid speculative abstractions and generic UI.
6. Review separately for specification compliance, geometry correctness, property preservation, and export behavior.
7. Run relevant tests and inspect the final diff. Report exact commands/results; distinguish synthetic geometry tests from real project acceptance.

## Quality gates

- Apply the full Anti-Slop core in `antislop.md`.
- This is a Streamlit UI. Use UI/UX Pro Max when installed for substantive interface work, while preserving the task-focused workflow. Verify responsive layout, keyboard/focus, empty/loading/error states, and actual interactions.
- Model the geometry workflow as a dependency graph: validation → normalization → reprojection → splitting → output validation → export. Do not parallelise dependent geometry stages.
- Never weaken tests, invent CRS metadata, or suppress geometry warnings to make output appear successful.
