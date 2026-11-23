# Releasing the Python implementation

The rules are the same for the whole organization:
[RELEASING.md](https://github.com/home-mandate/.github/blob/main/RELEASING.md). This page says
only what is particular to this repository.

## What is published

A version is a GitHub release with the conformance report of its commit, attested by GitHub.
A tag runs `.github/workflows/release.yml`, which creates both, and only if the conformance
run passes. A published release is immutable. Publishing on PyPI as `home-mandate-spec` is not
set up yet.

## Steps

`pyproject.toml` carries the version without a suffix. For a release candidate the workflow
takes `X.Y.Z-rc.N` from the tag and passes it to `mandate-conformance`, so a release candidate
needs no pull request, and the version is the commit of a release candidate.

1. A pull request sets `version` in `pyproject.toml` to `X.Y.Z`, and `spec` in
   `[tool.home-mandate]` if the specification changed. `src/home_mandate_spec/harness.py` must
   exist; without it there is nothing to release. `release/X.Y` starts from its commit.
2. Tag the release candidate on `release/X.Y` and push the tag. `release.yml` checks the tag
   with [`release-verify`](https://github.com/home-mandate/.github/tree/main/actions/release-verify)
   (where it stands, that the pull request's checks passed, that the release doesn't exist),
   that it matches `version`, and publishes the release with the attested report.
3. The release gate follows: every target in `tests/fuzz` with the profile `long`, starting
   from the examples the scheduled runs have kept. The job `Release gate` succeeds only if the
   release was published and the fuzzing passed. Until `tests/fuzz` has targets, the gate has
   nothing to run and passes.
4. Tag the version on the commit of a release candidate whose gate passed.

While the specification itself is a release candidate, `spec` may name that release candidate
and this implementation publishes release candidates against it. A version must name a
version: when the specification's version is out, a pull request moves `spec` to it, a new
release candidate follows, and the version goes on its commit. `release.yml` refuses a version
that names a release candidate of the specification.

When a run fails before the release is published, nothing is published, but the tag can't be
used again: the next attempt is `-rc.N+1`. The dry run finds most of that before the tag.

```sh
# the release candidate, on the release branch
gh workflow run release.yml --ref release/0.2 -f tag=v0.2.0-rc.1   # dry run, publishes nothing
git switch release/0.2 && git pull
git tag -a v0.2.0-rc.1 -m "home-mandate-spec v0.2.0-rc.1"
git push origin v0.2.0-rc.1

# the version, on the commit of the release candidate, after its gate
gh workflow run release.yml --ref release/0.2 -f tag=v0.2.0
git tag -a v0.2.0 -m "home-mandate-spec v0.2.0" v0.2.0-rc.1^{commit}
git push origin v0.2.0
```
