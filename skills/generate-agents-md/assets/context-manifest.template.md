# Context Workset {{RUN_ID}}

- Run ID: {{RUN_ID}}
- Baseline artifact: {{BASELINE_ARTIFACT_PATH}}
- Baseline version: {{BASELINE_VERSION}}
- Baseline SHA-256: {{BASELINE_SHA256}}
- Code version: {{CODE_VERSION}}
- Build ID: {{BUILD_ID}}
- Risk / expansion reason: {{RISK_LEVEL}}; {{RISK_REASON}}; {{WORKSET_EXPANSION_REASON}}
- Requirement IDs: {{AFFECTED_REQUIREMENT_IDS}}
- Modules: {{AFFECTED_MODULES}}
- Module changed files: {{MODULE_EQUALS_COMMA_SEPARATED_CHANGED_FILES_SEMICOLON_DELIMITED}}
- Changed files: {{CHANGED_FILE_PATHS}}
- Configuration files: {{CONFIGURATION_FILE_PATHS_OR_NA_REASON}}
- Input files: {{INPUT_FILE_PATHS_OR_NA_REASON}}
- Direct dependency boundaries: {{CALLERS_CALLEES_INTERFACES_CONFIG_AND_DATA_BOUNDARIES}}
- Required commands: {{REQUIRED_COMMANDS}}
- Effective AGENTS files: {{SORTED_EFFECTIVE_AGENTS_PATHS}}
- Effective AGENTS fingerprint: {{EFFECTIVE_AGENTS_CHAIN_SHA256}}
- Command manifest: {{PROJECT_COMMAND_MANIFEST_PATH}}
- Command manifest fingerprint: {{PROJECT_COMMAND_MANIFEST_SHA256}}
- Code fingerprint: {{CODE_SHA256}}
- Command fingerprint: {{COMMAND_SHA256}}
- Configuration fingerprint: {{CONFIGURATION_SHA256}}
- Environment ID: {{ENVIRONMENT_ID}}
- Input fingerprint: {{INPUT_SHA256}}
- Evidence fingerprint: {{EVIDENCE_SHA256}}
- Evidence cache key: {{EVIDENCE_CACHE_KEY}}
- Reuse decision: {{RERUN_OR_REUSE_RUN_ID}}
- Reuse record: {{REUSE_RECORD_JSON_OR_NA_REASON}}
- Evidence paths: {{EVIDENCE_PATHS_OR_NA_REASON}}

Compute each file-set fingerprint from sorted project-relative regular-file paths and file SHA-256 values. `Requirement IDs` must be unique. `Effective AGENTS files` must exactly list every existing regular non-symlink `AGENTS.md` from the project root through each changed/configuration/input file's parent directory; a symlinked AGENTS file, symlinked workset parent, or symlinked workset leaf fails closed. Compute the command fingerprint from the exact Required commands text, and bind both the effective AGENTS chain and command manifest by their complete bytes. Canonicalize the module map as modules sorted by key, each written `module=comma-sorted-paths`, joined by semicolons; module file sets must be non-overlapping and must exactly cover Changed files. Compute `Evidence cache key` as SHA-256 over the NUL-separated baseline artifact path, baseline version, baseline SHA-256, normalized sorted Requirement IDs, canonical module map, risk/expansion reason, direct dependency boundaries, code version, build ID, code fingerprint, command fingerprint, effective-AGENTS fingerprint, command-manifest fingerprint, configuration fingerprint, environment ID, input fingerprint, and evidence fingerprint in that order. Use `rerun` with an `N/A:` reuse-record reason unless every value matches a successful reusable evidence record. A singular source-run record may be reused only for a one-module workset; multi-module worksets must rerun. Otherwise use `reuse: <prior_run_id>` and bind `Reuse record` to `assets/reuse-evidence.template.json`, including the exact module and distinct immutable completed source-run record path/hash. Read only these linked artifacts by default. Update and validate this manifest before expanding context or reusing evidence.
