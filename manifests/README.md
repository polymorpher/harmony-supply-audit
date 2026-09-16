# Manifests

- `dependencies.lock.json`: exact Go and optional protocol/native source
  revisions.
- `checkpoints/checkpoints.json`: canonical block, state-root, and historical
  range requirements.
- `results.sha256`: local identities for every dated compact result set during
  the embargo.
- `source.sha256`: public source-package identities.
- `releases/`: local large-evidence identities during the embargo.

`source.sha256` is regenerated with `make manifest`. Dated result indexes and
the combined local result manifest are regenerated with
`make private-manifest`.

The September 16 release manifest binds the large retained-address
non-issuance CSV. Large release assets are not downloaded automatically.
