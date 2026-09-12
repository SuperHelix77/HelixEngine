# Release build and verification

This process builds only the package artifacts. It does not run a model,
benchmark a model, publish to GitHub, change Codex configuration, or copy a
research ledger or private raw logs into a release.

## Build

Install the build frontend in the maintainer environment, then run:

    python3 -m pip install --upgrade build setuptools wheel pytest
    SOURCE_DATE_EPOCH=315532800 python3 scripts/build_release.py

On Windows PowerShell:

    py -3 -m pip install --upgrade build setuptools wheel pytest
    $env:SOURCE_DATE_EPOCH = "315532800"
    py -3 scripts/build_release.py

The script emits a wheel, an sdist, dist/manifest.json, and
dist/SHA256SUMS. The manifest records package version, artifact sizes, and
SHA-256 digests. The checksum file covers both artifacts and the manifest.
Only expected release files in dist are touched.

## Verify

Run:

    python3 scripts/verify_release.py

The verifier checks the manifest schema, package version, byte sizes,
SHA-256 values, checksum coverage, and archive member paths. It rejects
absolute or parent paths and rejects research/private-log directories.

Install the wheel from a local wheelhouse and run:

    python3 -m pip install --no-index --find-links wheelhouse --force-reinstall dist/helixengine-0.1.0-py3-none-any.whl
    python3 scripts/test_installed.py

The wheelhouse must contain certifi for an offline install unless certifi is
already installed in the selected environment. The runtime package has no
other dependency.

Browser smoke uses a separate development dependency. The Ubuntu browser job installs
Playwright and Chromium separately; Playwright is not a runtime dependency.

The supported runtime boundary is explicit foreground routing. The `run`
operation does not launch detached daemons or claim coverage of every
workflow or source-output path. POSIX managed process groups receive forced
cleanup after parent observation. Windows is not a Job Object or process
sandbox claim; unmanaged background descendants can outlive the parent or
keep descriptors open, so captured streams are not guaranteed complete for
those descendants.

## Evidence boundary

Release artifacts contain application code, web assets, public
hash-bound evidence capsules, documentation, and packaging metadata. They
do not contain the research ledger, raw private logs, or absolute developer
paths. Public capsules retain rejected outcomes and qualification limits.
No artifact establishes universal parity, automatic Codex interception,
pre-inference interception, provider attestation, included quota, or total
effective cost.

The source is available for authorized publication. The source repository
has no selected license at this time, so release materials make no license
grant or third-party rights claim.
