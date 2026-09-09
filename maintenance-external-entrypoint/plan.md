Objective: Allow explicitly declared canonical external Python tool entries with SHA-256 binding while preserving project write boundaries.
Scope: command validator and live fingerprint chain; native pytest report parsing; regression/mutation anchors and usage instructions; official plugin reinstall after independent pass. Public template remains project-local.
Ordered steps: failing regression; minimal repair; targeted checks; independent review; freeze/full; official cachebuster/reinstall/distribution.
Verification: undeclared entries, drift, aliases and invalid binding fail; declared exact entry passes; existing tests and doctor pass.
Known risks: trust binds entry bytes only, not imported dependency tree or OS execution isolation.
Status: in_progress
swimlane_applicable=false; flow_impact=none (Skill command validation only).
