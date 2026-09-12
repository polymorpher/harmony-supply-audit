# Reproduction provenance

`as-run/` contains sanitized versions of historical operational wrappers.

They preserve:

- command order;
- stop/restart traps;
- LevelDB lock checks;
- binary/input hash checks;
- `.partial` output and atomic rename behavior.

They replace private users and paths with environment variables. They are not
byte-identical to the original wrappers. `SOURCE-HASHES.json` records both
source and sanitized hashes.

Use `docs/reproduce.md` for a new run. Do not execute an archived wrapper
without reading and adapting it.
