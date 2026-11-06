# MKV Episode Manager

A personal Windows 11 desktop application to organise MakeMKV movie and television rips using a careful, review-before-copy workflow.

**Current repository status:** v0.4 test build is being preserved on a release-candidate branch. The `main` branch remains the owner's approval gate for stable releases.

## v0.4 (manual identification foundation)
- PySide6 dark desktop GUI and three import modes
- Read-only MKV import and FFprobe technical inspection
- Optional FFmpeg scene thumbnails and playback preview
- Manual movie / episode assignment and proposed filename review
- Save and resume projects; duplicate-file hash detection; basic episode numbering gaps
- Explicit per-row approval and SHA-256 verified, non-overwriting copy export
- Diagnostic JSON reports

**Not yet included in v0.4:** automatic TMDB metadata, visual episode matching or dialogue-based episode identification.

See [v0.4 testing notes](docs/V0.4_TEST_NOTES.md) and [installation guide](docs/V0.4_INSTALL.md).

## Version policy
Development commits go to dedicated branches. A stable release or merge to `main` requires explicit approval from the repository owner.
