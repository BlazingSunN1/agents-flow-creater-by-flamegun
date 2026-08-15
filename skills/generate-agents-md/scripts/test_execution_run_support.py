from __future__ import annotations


def reusable_execution_run(
    run_id: str, cache_key: str, evidence_path: str, *, baseline_sha: str = "0" * 64,
    risk_reason: str = "standard; verified reuse; no expansion", code_version: str = "code-v1",
    changed_files: str = "src/module.py", requirement_ids: str = "REQ-001",
    module: str = "module", build_id: str = "build-1", environment_id: str = "local-test",
    source_context_path: str = "docs/module_execution_log_directory/module/context-prior-run.md",
) -> str:
    return f"""# Run {run_id}

- Run ID: {run_id}
- Module: {module}
- Status: completed
- Code version: {code_version}
- Context cache key: {cache_key}
- Baseline version and SHA-256: req-v1 / {baseline_sha}
- Build ID and acceptance environment: {build_id} / {environment_id}
- Risk level and reason: {risk_reason}
- Traceability IDs: {requirement_ids}
- Changed files: {changed_files}
- Delivered result: verified prior result
- Context workset manifest and reused evidence fingerprints: {source_context_path} / {cache_key}
- Automated review evidence: evidence/review.json
- Independent review evidence: evidence/independent.json
- Swimlane evidence: evidence/swimlane.json
- Frontend evidence: N/A: no frontend
- Classified findings and routes: none
- Verification evidence: {evidence_path}
- Frontend interaction evidence: N/A: no frontend
- Swimlane diagrams and validated evidence: evidence/swimlane.json
- Remaining risks: none
"""
