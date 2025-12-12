# Historic Documents Archive

This folder contains deprecated or superseded documentation and drafts from the project history. The purpose is to retain a historic record of previous implementations and drafts for reference and audits.

Folder layout:
- historic/
  - mcp/       - historic KB-MCP docs (old drafts, archives)
  - dispatcher/ - historic dispatcher docs (old drafts, test results)
  - general/   - historic general docs (old specs, original long docs)

Guidelines:
- Files in this folder are not actively maintained.
- If a file needs to be restored to "main" documentation, copy it out of this folder and publish or update accordingly.
- Avoid modifying historic files unless fixing typos or adding notes; prefer creating a new doc in the corresponding module if content needs updating.

Moved files (initial):
- dispatcher/guides/Multi_Dimensional_Algorithm_Implementation_Guide.md (superseded by FINAL)
- dispatcher/reports/fire_test_results.md (archived; keep final)
- dispatcher/reports/fire_test_results_2.md (archived; intermediate)
- general/specifications/Feature Specification - Dynamic Context-Aware Anomaly Detection.md (original long spec; replaced by Revised)
- general/plans/Implementation_Gap_Analysis_and_Remediation_Plan.md (claimed legacy removal but code still contains fallbacks; archived for audit)
