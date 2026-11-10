# tech-health-report v1.0.0 (scrubbed copy)

Tech Health v1 in-depth report skill (Claude Code). This copy has no customer data: account notes are not included.

- Source: the v1.0.0 package of 2026-11-10 (latest file change 2026-10-30). Bundled weekly script: tech-health-weekly 1.2.3.
- Removed: every `accounts/<key>.json` (customer names, context and gateway lists). Keep them in the data folder's `accounts/` on each computer; format in `accounts/README.md`.
- Changed from the package: `SKILL.md`, `accounts/README.md` and `scripts/queries/acct_keys.kql` no longer name accounts. `scripts/queries/brazil_latency.py` takes the account as a required argument and reads its gateway sites from the account notes' `pcg_groups` instead of a fixed list. Site names now come from the Admin Portal region names, so some differ from the package (for example "Hyderabad, India" for "Hyderabad"). This change has not been run against live data.
- Not included: the v2 work (skill_v2), which is still in review.
- Install: copy this folder to ~/.claude/skills/ so SKILL.md sits at ~/.claude/skills/tech-health-report/SKILL.md, then reload skills.
- Needs: Python 3, az CLI signed in, read access to the venn-apps Log Analytics workspace. Data goes to TH_HOME or %USERPROFILE%/TechHealth.
- Use: ask Claude Code to "build the tech health report for <account>".

## Files (sha256, first 12)

- `SKILL.md` ece7869d8f2b
- `accounts/README.md` ee9b92935203
- `scripts/build_indepth.py` fcf94c86a23c
- `scripts/build_indepth_page.py` 6ccbe215a983
- `scripts/indepth_style.css` 55093b02dd4b
- `scripts/queries/acct_keys.kql` 7811544777d9
- `scripts/queries/apps_by_band.py` 41df8176b1d6
- `scripts/queries/av_sets.kql` 11f9f7d7df33
- `scripts/queries/brazil_latency.py` 4880a8e01ba5
- `scripts/queries/build_summary.py` 0b5a2e3d4bf5
- `scripts/queries/free_ram_av.py` 68b82e439823
- `scripts/queries/gateway_by_location.py` c0bc7eea354e
- `scripts/queries/kq.py` 9276b42b6e8f
- `scripts/queries/latency_check.py` ddd9f921c0b1
- `scripts/queries/mac_health.py` 81bed3616499
- `scripts/queries/swap_by_band_weekly.py` 228b7e366c55
- `scripts/queries/thq.py` 2fdbcda46e38
- `scripts/queries/weekly.py` 03b1a8b79ebb
- `scripts/queries/weekly_trend.py` 2fd81d5d4f31
- `scripts/queries/why_8gb.py` 1a541501589c
- `scripts/tech_health_weekly.py` 4f4fcf9e2ef7
- `scripts/tour/tour.js` 0a8c75340810
