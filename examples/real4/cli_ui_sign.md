# repo-audit — a developer command-line tool

## Requirements
- A developer runs `repo-audit scan <path>` in the terminal; it prints findings to stdout and exits with code 1 when a critical finding exists.
- `repo-audit fix` rewrites files in place and prints a diff; `--dry-run` shows the diff without writing.
- The tool reads its rules from a YAML file and caches parsed rules on disk between runs.
- Findings can be exported as SARIF for GitHub code scanning.
- A local terminal UI (`repo-audit tui`) lists findings and lets the developer open a file at the line.

## Constraints
- Go 1.22, single static binary, no network access at runtime. Team: 2 engineers.
