# Cirrus Workplace — versions and downloads

**Latest: Version 20**, branch **version-20**, tag **v20.0.0**. The default
`main` branch contains Version 20. Earlier release branches and tags remain
available. Sign into the private repository to open downloads. ZIPs contain
application code, never live databases or credentials. Read the matching upgrade
guide before replacing a running application.

| Application name | Canonical branch | Tag / ZIP | Upgrade guide |
|---|---|---|---|
| **Cirrus Workplace Version 20 — latest** | [version-20](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-20) | [Complete Version 20 app ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v20.0.0.zip) / `v20.0.0` | [Version 20](version-20-upgrade.md) |
| Cirrus Workplace Version 19 | [version-19](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-19) | [Complete Version 19 app ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v19.0.1.zip) / `v19.0.1` | [Version 19](version-19-upgrade.md) |
| Cirrus Workplace Version 18 | [version-18](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-18) | [Version 18 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/version-18.zip) / `v18.0.0` | [Version 18](version-18-upgrade.md) |
| Cirrus Workplace Version 17 | [version-17](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-17) | [Version 17 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/version-17.zip) / `v17.0.0` | [Version 17](version-17-upgrade.md) |
| Cirrus Workplace Version 16 — supplied VM baseline | [version-16](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-16) | [Baseline ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/version-16.zip) | [Source verification](version-17-upgrade.md#verified-source) |
| Cirrus Workplace Version 15 | [version-15](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-15) | [Latest Version 15 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/heads/version-15.zip) | [Version 15](version-15-upgrade.md) |
| Cirrus Workplace Version 14 | [version-14](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-14) | [v14.0.0 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v14.0.0.zip) | [Version 14](version-14-upgrade.md) |
| Cirrus Workplace Version 13 | [version-13](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-13) | [v13.0.0 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v13.0.0.zip) | [Version 13](version-13-upgrade.md) |
| Cirrus Workplace Version 12 | [version-12](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-12) | [v12.0.0 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v12.0.0.zip) | [Version 12](version-12-upgrade.md) |
| Cirrus Workplace Version 11 | [version-11](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-11) | [v11.0.0 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v11.0.0.zip) | [Version 11](version-11-upgrade.md) |
| Cirrus Workplace Version 10 | [version-10](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-10) | [v10.0.0 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v10.0.0.zip) | [Version 10](version-10-upgrade.md) |
| Cirrus Workplace Version 9 | [version-9](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-9) | [v9.0.0 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v9.0.0.zip) | [Version 9](version-9-upgrade.md) |
| Cirrus Workplace Version 8 | [version-8](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-8) | [v8.0.0 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v8.0.0.zip) | [Version 8](version-8-upgrade.md) |
| Cirrus Workplace Version 5 | [version-5](https://github.com/workjoseph1998-cyber/codex-test-lab/tree/version-5) | [v5.0.0 ZIP](https://github.com/workjoseph1998-cyber/codex-test-lab/archive/refs/tags/v5.0.0.zip) | [Version 5](v5-upgrade.md) |

The original `v19.0.0` tag remains unchanged; `v19.0.1` adds the approved quotation margin-controls layout.

## Historical identity and compatibility

Historical version refs preserve their recorded release commits. The `version-15` branch retains its tested patches; its original release tag remains immutable.
The `version-16` ref records the supplied ZIP baseline at `303e1e4`, whose internal
branding remains Version 15. This records the VM version name without inventing
different source changes. Version 17 uses schema 16 and its own release refs.
No old commits, product files, feature branches or existing download links are rewritten. In particular, Version 10 includes its later Windows setup/ensurepip fixes
(`7dfc1eb`), and Version 5 includes its reference-conflict fix (`33fed84`).

The earlier Joseph Workspace, quotation-editor, hosting-VM, team-upgrade and
commercial-tools branches were milestones without a consistently recorded version
number. They remain under their original names. This index does not invent a Version
6 or 7, or retroactively relabel historical application branding. The dated commit
history is retained in full. Existing `feature/cirrus-workplace-v8` through `-v15`
branches and the older document-workspace branch remain valid.

These are Git version refs, not a claim that GitHub Release objects were renamed.
GitHub's release-administration API was unavailable (Forbidden) in this environment;
existing Release-page titles could not be inspected or changed. The repository's
latest code, visible branding, default branch, canonical refs and this index identify
Version 20 clearly.
