# Releasing the Python implementation

The rules are the same for the whole organization:
[RELEASING.md](https://github.com/home-mandate/.github/blob/main/RELEASING.md). This page says
only what is particular to this repository.

## What is published

A version is a GitHub release with the conformance report of its commit, attested by GitHub.
A tag runs `.github/workflows/release.yml`, which creates both, and only if the conformance
run passes. Publishing on PyPI as `home-mandate-spec` is not set up yet.

## Before a tag

- A pull request has set the version in `pyproject.toml`; the tag must match it.
- `src/home_mandate_spec/harness.py` exists; without it there is nothing to release.

```sh
git switch main && git pull   # for a patch: release/X.Y
git tag -a v0.1.0-rc.1 -m "home-mandate-spec v0.1.0-rc.1"
git push origin v0.1.0-rc.1
```

The text of the release is generated and can be edited afterwards.
