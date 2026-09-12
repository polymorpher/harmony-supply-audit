# Security

This repository contains read-only blockchain audit tools. It does not need
validator keys, wallet keys, cloud credentials, or production node
configuration.

Do not provide secrets when reporting a problem. Report a security issue
privately to the Harmony security contact before opening a public issue.

## Database safety

- Stop Harmony before opening its LevelDB, or scan a consistent cold snapshot.
- Never copy a live LevelDB file by file.
- Keep audit outputs outside the source database.
- Run the tools as an unprivileged user.
- Review every command before using an archived `repro/` template.

The maintained toolkit opens source databases read-only. Some utilities create
new output databases when explicitly given an output path.
