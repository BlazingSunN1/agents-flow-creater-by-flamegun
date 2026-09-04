# Role-specific local receipt schema v2

Use schema v2 for new local-coordination evidence. Schema v1 remains accepted only as the legacy contract. All JSON objects are strict and closed: duplicate, missing, or extra fields fail.

Every implementation and independent-gate spawn receipt contains exactly the common identity fields plus `read_only`, `authority_matrix_sha256`, `owned_paths`, `baseline_sha256`, `code_version`, `build_id`, and `candidate_sha256`. Hashes are lowercase 64-character SHA-256 strings. `owned_paths` is the exact, non-empty, duplicate-free project-relative ownership row in declared order.

An implementation spawn additionally contains exactly one `active_write_lease` object with `lease_id`, canonical project-relative `path`, and lowercase `sha256`. The locator must resolve without symlinks inside the project and match its bytes. A new candidate or lease requires a new implementation spawn receipt; path, inode, content, Agent ID, or run ID reuse fails closed.

Every gate spawn and output is `read_only=true`, repeats the same authority, owned paths, baseline, code, build, and candidate, and must not contain `active_write_lease`. Output additionally binds the role input/output hashes, baseline version, and verdict. Gate receipts, Agent IDs, and run IDs are unique and cannot reuse another role's evidence.

The schema-v2 multi-Agent outer object is the only expected-value source and therefore contains `authority_matrix_sha256`, `owned_paths`, and `active_write_lease`; validators do not infer them from current files. System bundles select actor receipt v2 explicitly with `runtime_receipt_schema_version=2` and provide dispatcher/aggregation owned paths plus baseline and candidate hashes. Omission preserves legacy actor receipt v1.

Default `delivery-first-local-coordination` validates these closed local receipts without a host verifier. `strict-security` runs the same complete local validation first and only then adds trusted-host attestation; it never replaces or weakens the local checks.
