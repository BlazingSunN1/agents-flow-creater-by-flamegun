Status: prepared; not installed or committed.
Candidate: generate-agents-md SHA-256 594a936a1c13d8678b08e0b6316ccfad494f2917d40b6e8327478eedd6ed5469.
Source: /Users/kinglone/plugins/agents-flow-creater-by-flamegun; Codex CLI confirms personal marketplace resolves to this exact source.

1. Require independent same-candidate pass and successful frozen full receipt.
2. Run official /Users/kinglone/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py on the exact source root. It changes only .codex-plugin/plugin.json, outside the Skill candidate digest. Record before/after manifest hashes and validate_plugin.py; verify the Skill digest unchanged.
3. Parent confirmed necessary reversible local commit is within current authorized repair/reinstall scope. Commit only nine changed Skill files, manifest, and this task's compact evidence directory (currently about 40 KB, including original red logs and diff). No push and no project changes. All existing source was clean before this task.
4. Run codex plugin add agents-flow-creater-by-flamegun@personal. Do not hand-edit marketplace or cached plugin files.
5. Only /Users/kinglone/.codex/skills/generate-agents-md differs from source. Copy the complete verified Skill to a sibling temporary install directory; compare its complete candidate digest; retain the previous directory in a timestamped backup and atomically rename the staged directory into place. Restore the backup if replacement fails. This is complete local installation from verified source, not patching the installed files.
6. Compare all existing direct paths: /Users/kinglone/.codex/skills/generate-agents-md, /Users/kinglone/.codex/skills/native-gpt-review-loop, /Users/kinglone/.codex/skills/multi-model-review-loop, /Users/kinglone/.codex/skills/strict-delivery-security. The latter three already match and need no mutation.
7. Run flowctl.py doctor --full --distribution --require-direct-skills. The verified full is reused; only distribution runs. Source must be clean HEAD, active cache and direct contents must match. Keep post-commit command output in tool transcript and official receipt location to avoid making source dirty during distribution.

Limits: local directory replacement is reversible installation, not an OS write sandbox. External-entry hash covers the Python entry bytes, not imported dependencies. Installation changes do not broaden project ownership. A new task is the safe Codex discovery boundary for the updated plugin.

Cachebuster completed via official helper: version 0.2.0+codex.20260905095718 -> 0.2.0+codex.20260908235823. Manifest SHA-256 6583815b6bc8593f4c16e41390fd420166f46ff187b36dad59540d5410e06085 -> 6dd14c272ca560da4da6195ee0a098c60c2def90088c830a886bfd330ac02afa. validate_plugin passed; Skill digest unchanged.
