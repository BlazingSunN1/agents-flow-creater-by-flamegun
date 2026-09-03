# Agents Flow Creater by FlameGun

An evidence-backed Codex plugin for generating, reviewing, and enforcing stable `AGENTS.md` delivery workflows.

## What it provides

- Requirement traceability and risk-based delivery gates
- Development plans, progress records, and module execution logs
- Automated review and independent acceptance evidence
- Browser click-through plus Playwright/Cypress frontend verification
- System and module swimlane diagrams generated from documentation and code review
- Stage-based swimlane updates to avoid unnecessary redraws and token usage
- Conditional major-module maintenance: qualifying modules receive one registered long-term maintenance Agent and an independently accepted closure; every maintainer and gate run is a distinct Codex-native `gpt-5.6-sol` Agent/run
- A bounded native `gpt-5.6-sol` solution-author → black-box-reviewer → read-only coordinator-adjudicator loop
- A hard-paused legacy Kimi/DeepSeek integration retained only for compatibility and offline inspection

## Skill

Invoke the bundled skills as:

```text
$generate-agents-md
$native-gpt-review-loop
$multi-model-review-loop
```

The first Skill builds and audits stable project rules. Main, parent, and child placement grants no inherent write authority. When major-module or multi-Agent criteria are met, each qualifying module receives exactly one registered maintenance/implementation Agent/run that may write only while holding the matching unique active module write lease; small tasks do not create this topology. Dispatcher and coordinator/adjudicator roles are always read-only. Delivery-first mode uses closed local coordination receipts; strict-security mode optionally adds host attestation. The governed updater enforces shared-record writes, while arbitrary same-user shell writes require OS or worktree isolation if technical prevention is needed. Cross-module delivery requires every module closure plus a separate `SYSTEM_AGGREGATION` Sol writer. The active review Skill uses two read-only Codex-native `gpt-5.6-sol` children and a separate read-only adjudicator. External Kimi/DeepSeek execution remains disabled.

## Repository layout

```text
.codex-plugin/plugin.json
skills/generate-agents-md/
skills/native-gpt-review-loop/
skills/multi-model-review-loop/
```

## Validation

Run the bundled validation gate from the Skill directory:

```bash
cd skills/generate-agents-md
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_skill.py --json
```

The gate checks the Skill package, code structure, public CLIs, regression tests, mutation tests, and swimlane JavaScript syntax.

After updating and reinstalling the local plugin, verify that the source tree, active plugin cache, and any direct Skill copies are identical:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_skill.py --full --distribution --require-direct-skills
```

Validate the native and paused legacy loops separately:

```bash
cd skills/multi-model-review-loop
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py' -q
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .

cd ../native-gpt-review-loop
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Security boundary

Do not commit real passwords, tokens, private keys, or personal data. Native review Agents are read-only advisers. The Dispatcher role remains read-only; only the registered maintenance/implementation Agent/run with the matching active module lease may edit its assigned paths, and it cannot self-certify independent acceptance. External providers remain disabled.
