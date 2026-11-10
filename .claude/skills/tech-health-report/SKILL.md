---
name: tech-health-report
description: Build the in-depth Tech Health report for any one Venn customer account and open it. Use when asked to "build/run the tech health report for <account>", "refresh the <account> tech health" or "do the tech health demo". One command (scripts/build_indepth.py, bundled with this skill) runs the analysis scripts in order (fixed-line scoring of every user against other customers, five-week trend, free memory/apps/security, latency check and where users connect, Mac users), then you write the story from facts.json only, rebuild, and open the page. Asks for the account's PCG gateway list when it is missing or the build finds gateways not on it. Account-specific notes (display name, a focus app, context) live in accounts/<key>.json, never in the scripts. Needs Python, the az CLI signed in, and read access to the venn-apps Log Analytics workspace, so it runs in a local Claude Code session only.
---

# In-depth Tech Health report

Two folders:

- **Code**: `<skill>\scripts`, where `<skill>` is the folder this SKILL.md is in. Never edit or write there.
- **Data**: `<data>` = the `TH_HOME` environment variable if set, else `%USERPROFILE%\TechHealth`. The build creates it and keeps `runs\`, `cache\`, `accounts\` and one folder per account there. On first use it copies any notes shipped in `<skill>\accounts` into `<data>\accounts`, never over a file that exists. This copy of the skill ships no account notes: keep them in `<data>\accounts` on each computer.

Every number on the page comes from the run's files. You write only `story.json`, and only from `facts.json`.

The run may be screen-recorded uncut, so print nothing extra, don't explore or debug on screen, and if a step fails, stop and say which one in one line.

## 0. Before you start

- Python 3 (standard library only) and the az CLI. Azure sign-in: `az account show --query user.name -o tsv`. If it fails, the user runs `az login`. The account needs read access to the venn-apps Log Analytics workspace; without it the first query fails.
- Decide live or warm. A fully live run takes about 5 to 7 minutes. With a warm cache, the same run takes seconds and the page shows the live timings from the last live run. To warm it, run the build once the same day. The cache is per user and per machine, so someone's first run is always live.

## 1. Account key and notes

The key is the account as telemetry names it: the part after the dot in a user ID (`jane.doe` → no; `janedoe.acme` → `acme`). To check a new name, copy `<skill>\scripts\queries\acct_keys.kql` into `<data>`, edit the copy, and run `python -I "<skill>\scripts\queries\kq.py" "<data>\acct_keys.kql"`.

Account-specific notes go in `<data>\accounts\<key>.json` (format in `<skill>\accounts\README.md`): `display_name`, an optional `focus_app` to look at closely, `pcg_groups`, `context` and `files`. Without the file the build still runs, with no focus app. Never hardcode an account, app, gateway or person into the scripts; put it in the notes file. Keep people's names out of the notes.

**Ask for the PCG gateway list (skippable), before building.** If `<data>\accounts\<key>.json` has no `pcg_groups`, ask once with AskUserQuestion: "No PCG gateway list for <account>. Paste it from Admin Portal > Private Company Gateway?", options "Skip, use IP prefixes" (first) and "I'll paste it". Telemetry can't see group membership, so without the list gateways show as IP prefixes and a restricted group (one that limits its users to a single region) can't be named. If the user pastes it, save it as `pcg_groups` (groups in Admin Portal order, first = default; each region with its two IPs) plus `pcg_source` with the date, then build. If they skip, build anyway and say in the summary that gateways are named by IP prefix. Don't ask again in the same session for the same account.

**A saved list can still be incomplete.** After the build, if step 4 printed "PCG endpoints not on the <key> gateway list: <ip> (<n> users, <h> h), …", ask once with AskUserQuestion: "<key> users reached gateways not on the saved list: <ips with users>. Paste the current list from Admin Portal > Private Company Gateway to check the groups?", options "Keep the saved list" (first) and "I'll paste it". If they paste, replace `pcg_groups`, update `pcg_source`, and rerun the build (it reuses cached queries, so it takes seconds). If they keep it, say in the summary which endpoints are unnamed; they show on the page by IP prefix.

**Brazil gateway step: one account only.** `brazil_latency.py` checks one gateway move (Brazil, live 21 Sep 2026) with fixed windows; the gateway sites come from the account's `pcg_groups`. It runs only when the notes have `"brazil_gateway_step": true`, which only the notes of the account it was built for have. Never add it for another account.

## 2. Build

```
python -I "<skill>\scripts\build_indepth.py" --account <key>
```

The week defaults to the last full Monday-to-Sunday week, and the month is the 28 days ending that Sunday. Add `--no-cache` for an all-live run. It prints six steps:

1. Compare every user with other customers
2. Five-week trend
3. Memory at start
4. Gateway and latency (plus the Brazil before-and-after, one account only)
5. Mac users
6. Write the report

Output goes to `<data>\runs\indepth_<key>_<week>\`: `facts.json`, `manifest.json`, `account.json` (a copy of the notes, if any), the page, and every step's files.

## 3. Write the story (facts only)

Read `<data>\runs\indepth_<key>_<week>\facts.json` and write `story.json` beside it. `account.json` is background only: use it to choose what to look at, never as a source of numbers.

```json
{"display_name": "<Account Name>",
 "headline": "the one thing that matters most, with both rates",
 "paragraphs": ["swapping as a symptom: by laptop memory and free memory at start", "what else is above or below others", "which way it is moving"],
 "tech": "Amber", "trend": "Improving, still above",
 "actions": ["2-3 concrete steps a CSM or SA can take, none of them hardware"]}
```

Rules:
- Every percentage says "of whom", and every gap names both rates ("24% of <account> users, against 14% at other customers").
- Swapping is a symptom: the laptop is short of memory, and it is the measure that best points to a slower experience. Don't build a "why it swaps" argument (apps, explained-gap percentages). Highlight it, show it by laptop memory and free memory at start, and move on.
- Lead with the biggest gap to other customers, whichever measure it is (frozen apps, drops, swapping), not swapping by default.
- No hardware upgrades in the story, actions or slides: never "recommend 16 GB", "upgrade RAM", "replace laptops" or "buy new laptops". Venn's value is BYOD, so the actions are things a user, CSM, SA or Venn config can change (close apps before starting Blue Border, start with the do-first list, review security software, gateway choice). Showing swapping by laptop memory is fine as a description. Device replacement is a reserved, last-resort tier owned by `venn-client-health-investigation` (a seat confirmed under 8 GB), never a report action.
- No causal claims beyond "goes with" or "explains about". Sentences under 25 words, plain words.
- Tech chip: Amber if any measure is 3+ points above other customers, Green if none. Red only if the user says so.
- Trend chip: "Improving, still above", "Steady, above", "Worsening" or "Level with others", read from the weekly series. When measures move in different directions, pick the one for the headline measure and say the other in a paragraph.

Then rebuild the page:

```
python -I "<skill>\scripts\build_indepth.py" --account <key> --render-only
```

## 4. Open

```
start "" msedge --start-fullscreen "<data>\runs\indepth_<key>_<week>\tech-health-indepth-<key>.html"
```

It names users, so it is internal only. Publish it as an Artifact only if the user asks (title "<display name> Tech Health", icon "chart").

## 5. Tour (optional, only if asked)

Walk the page only when the user asks for a tour or a demo. Page order:

1. The story and rating.
2. Last full week: each measure against the 4 weeks before and against other customers, with confidence.
3. What to do.
4. Free memory when Blue Border starts, by laptop memory.
5. Apps in use by memory group, with the focus app if the notes name one and the account uses it.
6. Security software (collapsed).
7. Monthly detail: all ten measures, this month against last.
8. Latency details (collapsed): bands, same country, accuracy check.
9. Connectivity.
10. Brazil gateway before and after (one account only, if 5 or more users moved).
11. Mac users, if any.
12. Named users.
13. How this report was built: the steps, scripts, queries, rows and live times.
