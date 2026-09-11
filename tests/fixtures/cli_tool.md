# logtrim — a command-line tool

Developers must trim large JSON-lines log files down to the entries that matter before
sharing them.

Functional
- The user runs `logtrim FILE` with flags to keep only lines whose level is at or above a threshold and whose timestamp is inside a window.
- The tool can read from stdin and write to stdout so it composes with other commands.
- The tool prints a summary (lines read, lines kept, time span) to stderr and exits with code 0 on success and 2 on a malformed line unless `--lenient` is set.
- The user can save a named filter preset and reuse it later.

Non-functional
- Processes a 2 GB file in under 60 s on a laptop.
- Never loads the whole file into memory.

Constraints
- Python 3.12, standard library only, single binary distribution not required.
