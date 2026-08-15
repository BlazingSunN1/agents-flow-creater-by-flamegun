# Delivery Traceability Matrix

## Requirement Baseline

- Baseline artifact: `{{BASELINE_ARTIFACT_PATH}}`
- Baseline version: `{{BASELINE_VERSION}}`
- Baseline SHA-256: `{{BASELINE_SHA256}}`
- Code version: `{{CODE_VERSION}}`
- Build ID: `{{BUILD_ID}}`
- Acceptance environment: {{ACCEPTANCE_ENVIRONMENT}}
- Verified at: `{{VERIFIED_AT_ISO8601}}`
- Risk level: `{{RISK_LEVEL}}`
- Risk reason: {{RISK_REASON}}
- Change surfaces: {{CHANGE_SURFACES}}
- Implementation run ID: `{{IMPLEMENTATION_RUN_ID}}`

Allowed change surfaces are `internal`, `behavior-change`, `user-visible`, `ui`, `api`, `mobile`, `touch`, `responsive`, `public-api`, `auth`, `security`, `privacy`, `migration`, `persistence`, `async`, `cross-module`, and `data-schema`. `mobile`, `touch`, and `responsive` are recorded only when the approved scope explicitly includes them; they do not make mobile adaptation globally mandatory. Any `public-api`, `auth`, `security`, `privacy`, `migration`, `persistence`, `async`, `cross-module`, or `data-schema` change is `high-risk`; any `behavior-change`, `user-visible`, `ui`, or `api` change is at least `standard`. Unknown impact is `high-risk` until disproved.

## Traceability

| Requirement | Flow | Feature | UI/UX | Unit tests | Acceptance cases | Code module | Black-box result | Status |
|---|---|---|---|---|---|---|---|---|
| [REQ-001]({{REQUIREMENT_ARTIFACT_PATH}}) | [FLOW-001]({{FLOW_ARTIFACT_PATH}}) | [FEAT-001]({{FEATURE_ARTIFACT_PATH}}) | [UI-001]({{UI_ARTIFACT_PATH}}) | [UT-001]({{UNIT_TEST_PATH}}) | [AT-001]({{ACCEPTANCE_CASE_PATH}}) | [MOD-001]({{CODE_MODULE_PATH}}) | [BB-001]({{BLACK_BOX_RESULT_PATH}}) | pending |

Use one row per requirement and put multiple unique links in a cell when needed. Only UI/UX may use `N/A: verified reason`, and never for a `ui` or `user-visible` change. Do not mark a row `completed` until every required path exists, all required independent gates pass against the current baseline/code/build, and Open Findings has no `open` row.

## Independent Gate Evidence

| Gate | Applicability | Agent run ID | Input baseline version | Input baseline SHA-256 | Code version | Build ID | Input manifest | Output evidence | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| UI_UX | {{UI_UX_APPLICABILITY}} | {{UI_UX_AGENT_RUN_ID}} | {{BASELINE_VERSION}} | {{BASELINE_SHA256}} | N/A: pre-implementation | N/A: pre-implementation | [CTX-UI-001]({{UI_UX_INPUT_MANIFEST_PATH}}) | [UI-REVIEW-001]({{UI_UX_REVIEW_PATH}}) | pending |
| ACCEPTANCE_CASES | required | {{ACCEPTANCE_AGENT_RUN_ID}} | {{BASELINE_VERSION}} | {{BASELINE_SHA256}} | N/A: pre-implementation | N/A: pre-implementation | [CTX-AT-001]({{ACCEPTANCE_INPUT_MANIFEST_PATH}}) | [AT-REVIEW-001]({{ACCEPTANCE_REVIEW_PATH}}) | pending |
| BLACK_BOX | required | {{BLACK_BOX_AGENT_RUN_ID}} | {{BASELINE_VERSION}} | {{BASELINE_SHA256}} | {{CODE_VERSION}} | {{BUILD_ID}} | [CTX-BB-001]({{BLACK_BOX_INPUT_MANIFEST_PATH}}) | [BB-REVIEW-001]({{BLACK_BOX_REVIEW_PATH}}) | pending |

Use `required` for applicable gates. For a non-UI, non-user-visible change, UI_UX may use `N/A: verified reason`, a blank Agent run ID, and `not_applicable`; UI or user-visible work cannot do so. Every applicable Agent run ID must be distinct and different from the implementation run ID. Input manifests must contain only the approved baseline version and the minimum affected IDs and paths needed by that role; the black-box manifest must not include implementation self-reports.

## Open Findings

- None

When findings exist, replace `None` with this exact table:

| Finding | Class | Status | Route | Evidence |
|---|---|---|---|---|
| DEF-001 | implementation_defect | open | implementation | [EVID-001]({{FINDING_EVIDENCE_PATH}}) |

Allowed class-to-route mappings are `implementation_defect → implementation`, `requirement_ambiguity → requirement-baseline`, `acceptance_case_defect → acceptance-cases`, `environment_blocker → blocked`, and `approved_requirement_change → new-baseline`. Never change the requirement baseline merely to make an implementation defect pass.
