# Account notes

One optional file per account, `accounts/<key>.json`. The build works without one; everything here is account-specific and stays out of the scripts.

| Field | Used by | Meaning |
|---|---|---|
| `key` | – | The account key passed to `--account`. |
| `display_name` | page title, fallback when `story.json` has none | How the account is named on the page. |
| `focus_app` | `apps_by_band.py`, page "Apps in use" section | One app to look at closely: who runs it, when, and whether its users swap more than others in the same memory group. Leave out for no focus app. The box is skipped when no one at the account launched it. |
| `focus_app_why` | story writer | Why this app was asked about. |
| `context` | story writer | Facts known about the account from outside this run (gateway moves, offboarding, prior findings). Background only: the story still comes from `facts.json`. |
| `pcg_groups`, `pcg_source` | `gateway_by_location.py`, page "Where users connect" | The account's gateway list from Admin Portal > Private Company Gateway: `[{"group": "All Users", "regions": [{"region": "North America (US-East)", "ips": ["…", "…"]}]}]`. The first group is the default; other groups are labelled "…, <group> group". Without it, gateways show as IP prefixes. When the account reaches a gateway the list doesn't name, step 4 prints "PCG endpoints not on the … gateway list" and the run's `gateway_by_location.json` lists them under `unlisted_gateways`: check the Admin Portal and update the list. |
| `brazil_gateway_step` | `build_indepth.py` step 4, page "Brazil gateway" section | `true` runs `brazil_latency.py`, the before-and-after check for the Brazil gateway go-live on 21 Sep 2026. One account only; its windows are fixed in the script and its site list comes from `pcg_groups`, which it needs. Leave out for every other account. |
| `files` | story writer | Paths (from the app folder) to call notes, talk tracks and earlier analyses for this account. |

The build copies the file into the run folder as `account.json`, so each run keeps the notes it was built with.

Keep people's names out of the notes; say what was asked and when.
