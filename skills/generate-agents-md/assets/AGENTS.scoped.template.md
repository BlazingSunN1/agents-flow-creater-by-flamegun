# Scoped Agent Instructions

<!--
PUBLIC TEMPLATE: place this file in {{SCOPED_DIRECTORY}}/AGENTS.md.
Only include rules that differ from the parent AGENTS.md.
-->

## Scope

These instructions apply to `{{SCOPED_DIRECTORY}}/**`.

## Local Constraints

- {{DIRECTORY_SPECIFIC_ARCHITECTURE_OR_STYLE_RULE}}
- {{GENERATED_OR_THIRD_PARTY_CODE_RULE}}

## Local Verification

```bash
{{DIRECTORY_TARGETED_TEST_COMMAND}}
{{DIRECTORY_FORMAT_OR_BUILD_COMMAND}}
```

## Local Frontend Verification

- When this scope contains Web frontend code, inherit the parent desktop PC click-through gate and run `{{DIRECTORY_PLAYWRIGHT_OR_CYPRESS_COMMAND}}` for the affected flow. Inherit a mobile browser gate only when the approved requirement, supported environment, or affected scope explicitly includes mobile Web, touch, or responsive browser behavior. Native mobile inherits the registered native test command instead.

## Local Change Boundaries

- {{DIRECTORY_SPECIFIC_COMPATIBILITY_OR_DEPLOYMENT_RULE}}
- Inherit the parent requirement IDs and risk level. Map every local code and test change to the affected `REQ-*`, `FEAT-*`, `MOD-*`, and applicable `UT-*`, `AT-*`, or `BB-*` identifiers; do not create an untracked local requirement.

## Local Execution Log

- Use the stable module key `{{MODULE_LOG_KEY}}` for this scope and write each run to `{{SCOPED_MODULE_EXECUTION_LOG_DIRECTORY}}/run-<run_id>.md`.
- After verification, update this module's `latest.md`; rely on the parent instructions for the compact index, required fields, version separation, and selective history reads.

## Local Swimlane Diagram

- At a stage/task milestone completion, synchronize this scope's module swimlane at `{{SCOPED_MODULE_SWIMLANE_PATH}}` and record evidence in the parent progress record. Before the milestone, update immediately only when the change alters a flow, entry point, handoff, branch, external dependency, persistence, async/recovery behavior, or final output; flow-neutral edits do not trigger redraws.
- If the change alters an entry point, cross-module handoff, system boundary, external dependency, persistence, asynchronous event, or final output, update the root system overview before this module diagram.
- Do not mark the scoped stage or task milestone complete until the synchronized interactive diagram has been opened in a browser and its affected module flow clicked through successfully.
