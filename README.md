# Agents Flow Creater by FlameGun

An evidence-backed Codex plugin for generating, reviewing, and enforcing stable `AGENTS.md` delivery workflows.

## What it provides

- Requirement traceability and risk-based delivery gates
- Development plans, progress records, and module execution logs
- Automated review and independent acceptance evidence
- Browser click-through plus Playwright/Cypress frontend verification
- System and module swimlane diagrams generated from documentation and code review
- Stage-based swimlane updates to avoid unnecessary redraws and token usage
- A bounded Kimi → DeepSeek → Codex GPT review loop without replacing native Codex authority

## Skill

Invoke the bundled skills as:

```text
$generate-agents-md
$multi-model-review-loop
```

The first Skill builds and audits stable project rules. The second runs an isolated Kimi → official DeepSeek V4 external sub-Agent → Codex GPT review loop. Internal Skill identifiers remain unchanged for compatibility with existing workflows.

## Repository layout

```text
.codex-plugin/plugin.json
skills/generate-agents-md/
skills/multi-model-review-loop/
```

## Validation

Run the bundled validation gate from the Skill directory:

```bash
cd skills/generate-agents-md
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_skill.py --json
```

The gate checks the Skill package, code structure, public CLIs, regression tests, mutation tests, and swimlane JavaScript syntax.

Validate the isolated multi-model loop separately:

```bash
cd skills/multi-model-review-loop
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py' -q
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Security boundary

Do not commit real passwords, tokens, private keys, or personal data. External-model review is advisory and isolated; Codex retains edit authority and final acceptance responsibility.
