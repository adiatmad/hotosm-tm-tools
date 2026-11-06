# HOTOSM Tasking Manager Tools — Engineering Constitution

## I. Geospatial correctness
Area-based splitting must use an appropriate equal-area CRS. The current workflow uses EPSG:6933. Never measure square-kilometre thresholds directly in longitude/latitude coordinates.

## II. Explicit input assumptions
Validate GeoJSON structure, geometry types, coordinate assumptions, empty inputs, and invalid geometries. Do not invent missing CRS information or silently reinterpret coordinates.

## III. Preserve geometry and properties
Geometry union, splitting, and export must not silently discard meaningful geometry parts, holes, feature properties, or source context. Any normalization must be explicit and tested.

## IV. Bounded, inspectable output
The configured target is 5,000 km². Recursive splitting must terminate safely and report failures clearly. Generated polygons are candidates for human inspection, not an automatic Tasking Manager approval.

## V. Test geometry behavior
Use representative fixtures for ordinary, multipart, invalid, empty, and boundary geometries. Verify area constraints, output validity, and property/provenance behavior.

## VI. Simple, task-focused UI
Every UI element must support upload, review, processing, or export. Preserve clear progress and error states; avoid decorative components and unsubstantiated success claims.

## VII. Honest delivery
Inspect the diff and run relevant checks. Distinguish synthetic fixture evidence from real project use and report all unverified assumptions.

## Governance
Amend this constitution only when the tool's geospatial or Tasking Manager output contract changes.
