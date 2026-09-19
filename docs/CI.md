# sekkei in CI

Three checks keep the design and the code from drifting apart. Each is one command, exits
non-zero on failure, and needs only Python 3.11+ and this package.

```yaml
# .github/workflows/design.yml
name: design
on: [pull_request]
jobs:
  design:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install git+https://github.com/yui9696/sekkei
      - name: the design is well-formed
        run: sekkei lint -d design/design.json
      - name: the code matches the design (paths, operations, dependency direction)
        run: sekkei check -d design/design.json --root .
      - name: a design change names the packages it invalidates
        run: |
          git show origin/${{ github.base_ref }}:design/design.json > /tmp/base.json 2>/dev/null || exit 0
          sekkei diff /tmp/base.json design/design.json || echo "::warning::design changed; re-issue the briefs listed above"
```

`sekkei check` reads Python today (imports between components, missing paths and
operations, parameter mismatches); for other languages it verifies paths only and says so
(`not_checkable`). `sekkei diff` exits 1 when the designs differ, which is the intended
signal for a review comment, not a failure — hence the `|| echo`.

## From a specification to a tracker

```sh
sekkei deliver spec.md -o design/            # design.json + the hand-over package
sekkei issues -d design/design.json -o .     # issues/WP-n.md, create_issues.sh, issues.csv
sh issues/create_issues.sh --milestone "M1"  # GitHub CLI, dependency order
sekkei openapi -d design/design.json -o openapi.json
```

Re-running `sekkei deliver` after the specification changes rewrites the package; the
issue bodies say which design version they came from, and `sekkei diff` says which work
packages changed.
