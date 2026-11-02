<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/home-mandate/.github/main/profile/assets/hm-lockup-dark.svg">
  <img src="https://raw.githubusercontent.com/home-mandate/.github/main/profile/assets/hm-lockup.svg" alt="Home-Mandate – AI is coming home. Decide what it may do." width="360">
</picture>

# Home-Mandate Specification: Python implementation

An independent Python implementation of the [Home-Mandate Specification](https://github.com/home-mandate/spec)
v0, written from the text of the specification and its conformance cases, not ported from
another implementation. What the specification is for, explained in plain words, and the
list of implementations are on [home-mandate.org](https://home-mandate.org/).

Status: **in development, nothing to use yet.** The first goal is the conformance class
`evaluator` (validation of mandates, digests and the evaluation rule) of the released
specification `v0.1.0`, whose v0 formats are frozen (SPEC-v0 section 14). The other
classes (`selection`, `signatures`, `audit`, `audit-anchored`) may follow.

Maintainer: [MuriloDPV](https://github.com/MuriloDPV). How the repositories of the
organization are run, and what every implementation keeps, is in
[GOVERNANCE.md](https://github.com/home-mandate/.github/blob/main/GOVERNANCE.md) and
[IMPLEMENTATIONS.md](https://github.com/home-mandate/.github/blob/main/IMPLEMENTATIONS.md).
The package will be published on PyPI as `home-mandate-spec` once there is something to
publish; until then, install from this repository.

## Conformance

Conformance is measured, not claimed: the specification's test tool `mandate-conformance`
runs the cases of the tag named in `pyproject.toml` (`[tool.home-mandate]`) against the
harness of this implementation on every pull request, and a report is attached to every
release, attested by GitHub. The README states the classes that pass once the first report
exists.

To run it yourself (Go and Python 3.12 or later):

```sh
pip install -e ".[dev]"
go install github.com/home-mandate/spec/cmd/mandate-conformance@v0.1.0
mandate-conformance -classes evaluator -exec python -m home_mandate_spec.harness
```

The harness speaks the process binding of the test interface (SPEC-v0 section 10): one
JSON request per line on stdin, one JSON response per line on stdout. Until
`src/home_mandate_spec/harness.py` exists, the conformance job of the integration workflow
has nothing to run and reports that.

## Development

```sh
pip install -e ".[dev]"
ruff check . && mypy && pytest
```

The checks of `ci.yml` run on every push to a branch, those of `integration.yml` on every
pull request against `main` (conformance and short fuzzing, required to merge),
`scheduled.yml` checks the dependencies every night and fuzzes for a long run on the 1st
and the 15th, and a tag `vX.Y.Z` or `vX.Y.Z-rc.N` on `main` publishes a release with its
conformance report (`release.yml`). The tools, the layout and everything else in this
repository are the maintainer's choice.

Code in this repository is written with the help of AI tools and checked against the text of
the specification and its conformance cases before it is merged.

## License

Apache License 2.0, see [LICENSE](LICENSE). The name Home-Mandate and the logo are not
covered by it ([TRADEMARKS.md](https://github.com/home-mandate/.github/blob/main/TRADEMARKS.md)).
