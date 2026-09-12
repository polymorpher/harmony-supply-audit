# Manifests

- `dependencies.lock.json`: exact Go and optional protocol/native source
  revisions.
- `checkpoints/checkpoints.json`: canonical block, state-root, and historical
  range requirements.
- `results.sha256`: local compact result identities during the embargo.
- `source.sha256`: public source-package identities.
- `releases/`: local large-evidence identities during the embargo.

`source.sha256` is regenerated with `make manifest`. Local result and release
manifests are regenerated with `make private-manifest`. Large release assets
are not downloaded automatically.
