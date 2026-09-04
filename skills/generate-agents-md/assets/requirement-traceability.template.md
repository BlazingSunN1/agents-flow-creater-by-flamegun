# Delivery Traceability Matrix

## Requirement Baseline

- Baseline artifact: `{{BASELINE_ARTIFACT_PATH}}`
- Baseline version: `{{BASELINE_VERSION}}`
- Baseline SHA-256: `{{BASELINE_SHA256}}`
- Authority matrix locator: `AGENTS.md#machine-enforced-authority-matrix`
- Authority matrix SHA-256: `aff241a02c51ebcf2b085602f122d7a677a41ea7cb2fa0d3db778a6886b6e643`
- Code version: `{{CODE_VERSION}}`
- Build ID: `{{BUILD_ID}}`
- Acceptance environment: {{ACCEPTANCE_ENVIRONMENT}}
- Verified at: `{{VERIFIED_AT_ISO8601}}`
- Risk level: `{{RISK_LEVEL}}`
- Risk reason: {{RISK_REASON}}
- Change surfaces: {{CHANGE_SURFACES}}
- Implementation run ID: `{{IMPLEMENTATION_RUN_ID}}`

Allowed change surfaces are `internal`, `behavior-change`, `user-visible`, `ui`, `api`, `mobile`, `mobile-web`, `native-mobile`, `touch`, `responsive`, `public-api`, `auth`, `security`, `privacy`, `migration`, `persistence`, `async`, `cross-module`, and `data-schema`. `mobile-web`, `touch`, and `responsive` use browser/E2E validation; `native-mobile` uses the registered native test command; legacy `mobile` is disambiguated by `frontend_applicable`. They are recorded only when the approved scope explicitly includes them and do not make mobile adaptation globally mandatory. Any `public-api`, `auth`, `security`, `privacy`, `migration`, `persistence`, `async`, `cross-module`, or `data-schema` change is `high-risk`; any `behavior-change`, `user-visible`, `ui`, `api`, `mobile`, `mobile-web`, `native-mobile`, `touch`, or `responsive` change is at least `standard`. Unknown impact is `high-risk` until disproved.

## Traceability

| Requirement | Flow | Feature | UI/UX | Unit tests | Acceptance cases | Code module | Black-box result | Status |
|---|---|---|---|---|---|---|---|---|
| [REQ-001]({{REQUIREMENT_ARTIFACT_PATH}}) | [FLOW-001]({{FLOW_ARTIFACT_PATH}}) | [FEAT-001]({{FEATURE_ARTIFACT_PATH}}) | [UI-001]({{UI_ARTIFACT_PATH}}) | [UT-001]({{UNIT_TEST_PATH}}) | [AT-001]({{ACCEPTANCE_CASE_PATH}}) | [MOD-001]({{CODE_MODULE_PATH}}) | [BB-001]({{BLACK_BOX_RESULT_PATH}}) | pending |

Use one row per requirement and put multiple unique links in a cell when needed. Only UI/UX may use `N/A: verified reason`, and never when the actual `ui` surface applies; plain user-visible text alone does not require a UI/UX artifact. Do not mark a row `completed` until every required path exists, all required independent gates pass against the current baseline/code/build, and Open Findings has no `open` row.

## Independent Gate Evidence

| Gate | Applicability | Agent run ID | Input baseline version | Input baseline SHA-256 | Code version | Build ID | Input manifest | Output evidence | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| UI_UX | {{UI_UX_APPLICABILITY}} | {{UI_UX_AGENT_RUN_ID}} | {{BASELINE_VERSION}} | {{BASELINE_SHA256}} | N/A: pre-implementation | N/A: pre-implementation | [CTX-UI-001]({{UI_UX_INPUT_MANIFEST_PATH}}) | [UI-REVIEW-001]({{UI_UX_REVIEW_PATH}}) | pending |
| ACCEPTANCE_CASES | {{ACCEPTANCE_CASES_APPLICABILITY}} | {{ACCEPTANCE_AGENT_RUN_ID}} | {{BASELINE_VERSION}} | {{BASELINE_SHA256}} | N/A: pre-implementation | N/A: pre-implementation | [CTX-AT-001]({{ACCEPTANCE_INPUT_MANIFEST_PATH}}) | [AT-REVIEW-001]({{ACCEPTANCE_REVIEW_PATH}}) | pending |
| BLACK_BOX | {{BLACK_BOX_APPLICABILITY}} | {{BLACK_BOX_AGENT_RUN_ID}} | {{BASELINE_VERSION}} | {{BASELINE_SHA256}} | {{CODE_VERSION}} | {{BUILD_ID}} | [CTX-BB-001]({{BLACK_BOX_INPUT_MANIFEST_PATH}}) | [BB-REVIEW-001]({{BLACK_BOX_REVIEW_PATH}}) | pending |

Resolve every applicability from the generated gate plan: use `required` only for a listed role; otherwise use `N/A: gate plan did not select role`, a blank Agent run ID/input/output, and `not_applicable`. Standard closure/completion uses only `BLACK_BOX`; high-risk adds separately mapped roles, and `UI_UX` requires the actual `ui` surface rather than plain user-visible text. Every applicable Agent run ID must be distinct and different from the implementation run ID. Input manifests must contain only the approved baseline version and the minimum affected IDs and paths needed by that role; the black-box manifest must not include implementation self-reports.

## Open Findings

- None

When findings exist, replace `None` with this exact table:

| Finding | Class | Status | Route | Evidence |
|---|---|---|---|---|
| DEF-001 | implementation_defect | open | implementation | [EVID-001]({{FINDING_EVIDENCE_PATH}}) |

Allowed class-to-route mappings are `implementation_defect → implementation`, `requirement_ambiguity → requirement-baseline`, `acceptance_case_defect → acceptance-cases`, `environment_blocker → blocked`, and `approved_requirement_change → new-baseline`. Never change the requirement baseline merely to make an implementation defect pass.

Requirement ambiguities must also be recorded in the machine-validated question list created from `assets/requirement-questions.template.json`. Every `NOT_PROVIDED` item remains `delivery_disposition=NON_BLOCKING_P2`, including `legal`, `security`, `irreversible-destruction`, and `missing-required-permission` risks. Those risks change only the safe action: do not perform an unapproved, unsafe, or destructive operation; record that action as unverified while the remaining safe scope continues with an explicit reversible default and fallback. `ANSWERED` requires a corrected requirement/objective baseline and completed reruns for the full affected scope.
