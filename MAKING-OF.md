# MAKING-OF.md

A narrative of how this project came together, written for anyone curious about how a small tool gets designed in collaboration with a coding agent (in this case, Claude).

This file exists because there is a popular but inaccurate model of "agentic coding" that goes: type a request, walk away, come back to a finished product. That is not what happened here, and it is not what should happen for any project where the result needs to be useful, maintainable, and trustworthy. What actually happened was a back-and-forth conversation in which a human held the design judgment and the agent did the legwork and surfaced options. The conversation was the engineering work; the code is just what fell out of it.

If you read the rest of the repo and wonder *why* it ended up shaped the way it did, this file is for you.

---

## Table of contents

- [The seed](#the-seed)
- [Round 1 — understanding the actual problem](#round-1--understanding-the-actual-problem)
- [Round 2 — understanding the data landscape](#round-2--understanding-the-data-landscape)
- [Round 3 — the constraints that scope the design](#round-3--the-constraints-that-scope-the-design)
- [Round 4 — what to actually build](#round-4--what-to-actually-build)
- [Round 5 — two implementations as the teaching artifact](#round-5--two-implementations-as-the-teaching-artifact)
- [Round 6 — iterating on names and conventions](#round-6--iterating-on-names-and-conventions)
- [Round 7 — adding a real second source](#round-7--adding-a-real-second-source)
- [Round 8 — capturing history without overcomplicating it](#round-8--capturing-history-without-overcomplicating-it)
- [Round 9 — the API moved on us](#round-9--the-api-moved-on-us)
- [What this process required](#what-this-process-required)
- [What an LLM brought, and what it did not](#what-an-llm-brought-and-what-it-did-not)
- [The takeaway](#the-takeaway)

---

## The seed

The starting point was a real workflow: pulling fund data from cefconnect.com for ~66 closed-end funds every month and reconciling the values into a spreadsheet used for portfolio decisions. The first attempt at automating it parsed PDF fact sheets with pandas — it worked, but it was slow, brittle, and a lot of code. The website was actually powered by a clean undocumented JSON API that returned the same data in a fraction of the lines.

The repo is the worked example that fell out of building a small reference tool against that workflow. Everything else in this file is the design conversation that produced it.

---

## Round 1 — understanding the actual problem

The first thing the conversation had to do was ignore the surface request ("automate the data pull") and figure out the real one.

Questions that had to be answered before any code made sense:

- Which fields actually matter? (Leverage metrics were named first; trailing total returns came up later. The list was implicit, scattered across the website's per-fund page.)
- What's the spreadsheet *for*, after reconciliation? (Most likely the artifact itself, used for team huddles and watchlist decisions on a CEF income sleeve.)
- How fresh does the data need to be? (Monthly. Anything more is noise, because the underlying SEC filings that drive the slow-moving fields update on a monthly-or-slower cadence.)

This step is where most agent-coding workflows go wrong. If you skip it and ask an agent to "build a CEF tracker," you get something that fetches data and writes it to a file — technically correct, almost certainly not useful. The shape of what to build follows from understanding the actual workflow it slots into.

---

## Round 2 — understanding the data landscape

A surprising amount of time went to mapping the data ecosystem. It mattered because the right tool depends on what data is actually available, where it comes from, and what costs money.

What the conversation surfaced:

- **CEFConnect** is owned by Nuveen. It's an aggregator, not a primary source.
- **Morningstar** is the upstream source for CEFConnect's calculated performance fields (annualized total returns, etc.). Morningstar has paid offerings (Excel add-in, REST API, SFTP delivery) that an advisory firm may already license through their custodian.
- **The funds themselves** are the source for distributions, leverage, and holdings, via SEC filings (19a-1 distribution notices, N-PORT monthly holdings reports, N-CSR semi-annual shareholder reports).
- **SEC EDGAR** publishes those filings within days of being filed — sometimes ahead of when CEFConnect reflects the data. That makes EDGAR a meaningful "early warning" source for distribution changes.
- **Other free aggregators** (CEFA.com, fund sponsor fact sheets, yfinance) add varying value: redundant, occasionally fresher, or thinner.

This mapping is what informed the architectural decision later in Round 7 to include EDGAR as a real second data source rather than just documenting it. The cost of integrating it is low (a small file conforming to the source interface), and it demonstrates exactly the kind of extension the architecture is designed for.

It also informed the README's Morningstar primer, which gives a roadmap for what integrating paid Morningstar access would look like — without doing it now, because the cost is uncertain and the licensing is a per-firm question.

---

## Round 3 — the constraints that scope the design

Several non-functional constraints emerged that shaped the design as much as the functional requirements did:

- **Locked-down corporate hardware.** Microsoft 365 shop. Pip installs are fine; admin-required installs are not. This pushed toward stdlib plus a tiny set of broadly-available dependencies, and away from anything that requires admin rights.
- **Compliance umbrella.** Operating under a broker-dealer's compliance and supervision framework. Hitting public market data is fine; touching client account data, paid-feed entitlements, or external storage is not. This set a clear bright line for what the tool could and could not do, and informed a section of the README's data-sources discussion.
- **Audience: two weeks into Python.** Code needed to reward careful reading. That meant readable names, type hints, sparse comments where the WHY was non-obvious, and an explicit choice not to use exotic patterns where pedestrian ones would do.

Constraints like these usually don't get articulated unless someone asks. Asking is part of the work.

---

## Round 4 — what to actually build

With the problem and constraints clear, the question became: what's the smallest thing that delivers real value?

The first sketch was straightforward: a single Python script that reads a list of tickers, hits the CEFConnect JSON API, and writes the result to an Excel file. Maybe 150 lines.

Then a second, parallel sketch: the same job, but structured as a multi-module Python package with explicit interfaces between data sources, output formats, and diff logic. Maybe 500 lines across ten files.

The two sketches were not "before and after" or "good and bad." They were two equally legitimate ways of approaching the same problem, with different trade-offs:

- The single-file version is faster to write, easier to read end-to-end, easier to share, and more than sufficient for personal automation. The "Automate the Boring Stuff" tradition.
- The multi-module version pays a structural cost up front in exchange for lower marginal cost on every future change — adding a data source, adding an output format, adding alerting.

Which one is "right" depends on time horizon, rate of change, and who else will touch the code. That's an engineering judgment, not a rule.

This is the moment the "two implementations" idea crystallized. Showing both, side by side, makes the trade-off concrete in a way that explaining it never quite does.

---

## Round 5 — two implementations as the teaching artifact

Once the two-implementations frame was on the table, the design effort shifted to making the comparison honest.

A few things had to be true:

1. **Neither version could be a strawman.** The single-file version had to be *good* idiomatic Python — top-down, well-named, type-hinted, the kind of code an experienced Python author would actually write for a one-off tool. Otherwise the comparison would be unfair and the lesson would be lost.
2. **The multi-module version had to *earn* its complexity.** Every additional file needed a reason. ABCs only where polymorphism would actually be exercised. Configuration only where things would actually change. No cargo-cult patterns.
3. **The contrast had to be presented as a choice, not a hierarchy.** The script version is not "the easy way" or "the shortcut." It's the right tool for some jobs. Framing it otherwise would teach the wrong lesson.

This last point required iteration. An early draft of the README used `easy/` and `engineered/` as folder names. That framing was wrong — it implied that one was "real engineering" and the other was a shortcut. Renaming them to `script/` and `package/` (real Python terms of art with no value judgment attached) fixed it. Small naming choice; large effect on what the repo communicates.

---

## Round 6 — iterating on names and conventions

A handful of conventions in the repo started as one thing and became another after a round of pushback:

- **Output filenames.** Initial thought: write to a fixed `latest.xlsx` and archive prior runs. Pushback: that pattern gets weird when two versions are open at once, and "latest" goes stale silently. Final convention: every run writes `extract-YYYYMMDDHHMM.xlsx` and `extract-YYYYMMDDHHMM.csv`. There is no "standard" filename. This sounds trivial; it eliminates an entire class of "wait, which one is the new one?" bugs.

- **Writing to existing workbooks.** Initial thought: the package version could append a dated tab to the user's main Excel workbook so all snapshots accumulate in one place. Pushback: a tool that automatically modifies a shared workbook is one bad assumption away from corrupting weeks of manual annotations. Final convention: every run produces standalone files. If the user wants the data in their main workbook, they copy-paste from the extract — explicit, intentional, no automation surprises. The cost of the "ergonomic" version is high if it goes wrong; the cost of the "explicit" version is low and bounded.

- **Including `AGENTS.md` and `CLAUDE.md`.** Initial draft assumed the README was sufficient documentation. Pushback: LLM coding agents do not automatically read README.md; they look for dedicated files like AGENTS.md and CLAUDE.md. If a future agent is going to work in this repo without rediscovering the conventions, those files have to exist. Final version includes both, and the README explains why in its "Why README.md? Why AGENTS.md?" section.

- **Test depth.** Initial draft mentioned "include some tests." Pushback: agentic test suites tend toward truthy fluff (assertions that always pass, tests of trivia). Final version specifies the exact tests to write — each pinning down logic that can actually break, none testing trivia. Specificity in the plan is what prevents the wrong kind of tests from showing up.

Each of these is small. Together they are most of what makes the repo trustworthy.

---

## Round 7 — adding a real second source

A late-stage iteration: the original plan documented EDGAR (and other free sources) in the README but did not implement any of them, deferring all of that to "future work."

That was wrong, and the pushback was sharp. The architectural payoff of the multi-module version is exactly the ability to add a second data source cleanly — and the fastest way to demonstrate that payoff is to actually do it. Documenting an extension point that nobody has ever extended is unconvincing. Documenting an extension point that already has two extensions is self-evident.

So `sources/edgar.py` is now a real implementation in the package version. It hits SEC EDGAR's full-text search API, finds 497-series filings (the form CEFs use to file 19a-1 distribution notices) within the last 60 days for each ticker, and returns a sparse `FundSnapshot` whose only populated field is `recent_distribution_filings`. The orchestrator merges that with the CEFConnect snapshot for the same ticker (first non-None wins, in source-priority order from `config.toml`). The diff engine has a corresponding flag rule for "new 19a-1 detected since prior run."

Sponsor fact sheets stayed in the docs-only category — PDF parsing per-sponsor-layout is genuinely hard and out of scope for v1. The README explains this so a future contributor knows exactly what's in scope to add and what isn't.

---

## Round 8 — capturing history without overcomplicating it

The last design question was: how should historical data be captured?

The simple approach (and the one originally specified) was per-run extract directories. Every run lands in `extracts/YYYYMMDDHHMM/` with its own `extract-*.xlsx`, `extract-*.csv`, and `run.log`. The diff engine compares the current run against the most recent prior directory. This works, and it is good for "what was in the run on 2026-05-03?" questions.

But it doesn't answer "how has BIT's distribution rate trended over the last twelve months?" without reading and concatenating dozens of extract files.

The pushback: capturing longitudinal history *well* is often where small tools get hard, because it's tempting to either (a) build a database, which is overkill, or (b) do nothing, which is what most people do, and they regret it the first time they want a time series.

The middle path adopted here: an append-only `history.csv` at the top level, written to (in addition to the per-run extract files) on every run. One row per ticker per run. Wide format. Gitignored, because the data is yours, not the project's.

Why CSV and not parquet or SQLite: the audience can open it in Excel, in pandas, in DuckDB, in any text editor. There is no round-trip cost between "I want to look at the data" and "the data is open in front of me." For a single user with a 66-row monthly snapshot, the file will stay small enough that performance is irrelevant for years.

Why append-only and not rewrite: it is *much* harder to corrupt an append-only file than one that gets rewritten. Power loss, an interrupted run, or a bug in the writer can damage a rewritten file but is unlikely to damage an append. Same logic that makes log files append-only.

Two artifacts for two questions: per-run dirs for "what was in this run", `history.csv` for "how has this moved over time." Both cheap to maintain. Keep both.

---

## Round 9 — the API moved on us

This round happened during the implementation pass, not the design pass, and it is the most useful one in this file if you are evaluating what agentic coding actually feels like in practice.

The plan named `https://www.cefconnect.com/api/v3/funds/{TICKER}` as the primary data source. That endpoint was real and well-shaped when the design conversation was happening — the entire architecture leaned on it returning a single fat JSON blob with sponsor / leverage / UNII / NAV / distributions / returns all together.

When the implementing agent went to set up the script's first fetch, the endpoint returned a 404. So did every plausible variation (`Funds/`, `FundDetail/`, `funds/{TICKER}/snapshot`, etc.). The undocumented JSON API the entire plan referenced no longer had a fund-detail endpoint at all.

This is exactly the failure mode the README's "Response shapes can change without notice" line warned about, and exactly the failure mode `AGENTS.md`'s "If during implementation you find a genuine reason to deviate from this plan, write it in `STATUS.local.md` and stop for human review" instruction was written to handle. The agent stopped, wrote up the blocker, and surfaced four options (HTML scrape, chart-only fields, switch aggregator, make EDGAR primary) with a recommendation. The human did the next thing that mattered: opened a real browser via Playwright and watched what the live page actually fires.

The network panel told a more interesting story than the 404s did. The page now hydrates from a fan of smaller endpoints — `pricinghistory/{TICKER}/{range}`, `performance/annualized/{TICKER}`, `distributionhistory/fund/{TICKER}/{from}/{to}`, `distributioncharter/fund/{TICKER}/{range}`, `assetallocation/{TICKER}`, `creditquality/{TICKER}`, and a few more. Together they cover NAV, market price, discount, total returns 1Y/3Y/5Y/10Y, and the distribution stream in JSON. What they don't cover is the slow-moving metadata block: sponsor, leverage %, leverage cost, UNII, expense ratio. Those four still live in server-rendered HTML on `/fund/{TICKER}`.

So the redesign was: keep CEFConnect as the primary source, but let it talk to four JSON endpoints plus one HTML page internally, and merge the result inside the source module. From the rest of the application's perspective nothing changes — `CEFConnectSource.fetch(ticker)` still returns one `FundSnapshot`. The cost is one new dependency (`beautifulsoup4`) and a small HTML parser that locates fields by surrounding `<strong>` text rather than by the brittle ASP.NET IDs.

A few things were preserved by handling it this way:

- **The architecture didn't need to bend.** Multi-source merging at the orchestrator level is for cross-aggregator merging (CEFConnect + EDGAR). Within-CEFConnect quirks belong inside `CEFConnectSource`. Keeping that boundary clean meant the only file that knew about the API change was the one that should know.
- **The teaching point got stronger.** "Undocumented APIs can disappear" was an abstract caution in the original README. It is now a concrete event in the repo's history, with the recovery written into the source code as a worked example. A reader who hits the same kind of failure later will have a precedent.
- **The plan stayed honest.** Rather than silently coding against the new reality, both `PLAN.md` and `AGENTS.md` were updated to reflect the actual endpoint inventory before any implementation code was written. Future agents reading those files will not be misled by stale references to a dead endpoint.

The friction here was small — maybe twenty minutes of probing and document updates — but the choice point was real. An agent left to its own devices in this situation could plausibly have done one of several wrong things: silently switched to HTML scraping without flagging it, given up and reported "blocked," or invented a fake endpoint based on what the plan said *should* exist and produced code that ran but returned garbage. The "stop and surface" pattern in `AGENTS.md` is what forced the right path. The browser inspection — which the human directed and the agent executed — is what produced the redesign.

Worth saying explicitly: agentic coding works best when this kind of pivot is treated as normal rather than exceptional. Plans drift; APIs move; assumptions break. The right reflex is "stop, surface, redirect" rather than "push through to whatever ships." The thirty-minute interruption to do that costs less than a week of debugging code that was built against a fiction.

---

## What this process required

Looking back, the design conversation depended on a handful of things the agent could not have done alone:

- **Asking questions and accepting half-answers.** A lot of the early conversation was sourcing facts about the actual workflow and feeding them back to the agent. The agent's job was to surface what it would *want* to know; deciding what was important was the human's.
- **Pushing back on bad framings.** "easy/engineered" was a bad framing for the two folders. Renaming to "script/package" was a small move with a large effect on what the repo communicates. Catching framings like that requires having seen them work and not work in other contexts. Taste, in other words.
- **Knowing what to leave out.** The README does not include sponsor fact sheet parsing because PDF-per-layout is hard. The package version does not include scheduling because that's a separate problem with its own constraints. The script version does not include diff because diff is what makes the package version pay for itself. Every "no" in the plan is a decision.
- **Knowing the landscape.** That EDGAR has an EFTS search endpoint, that Morningstar has three flavors of paid access, that uv has a user-level installer, that small advisory practices typically operate under a broker-dealer's compliance framework — none of that is novel research. It's just having been around the relevant ecosystems before. The agent surfaced details on demand; recognizing which details mattered was the human's call.
- **Iterating until the artifact felt right.** The first draft of any document is usually wrong in ways you only see when you read it back. Writing, reading, pushing back, rewriting — that cycle is what produced the version you're reading.

---

## What an LLM brought, and what it did not

What it brought, and brought well:

- **Speed of iteration.** Rewriting a README section, restructuring a plan, regenerating a configuration file — each takes seconds. This makes "let's try it the other way" cheap, which makes the conversation more honest because no version is precious.
- **Breadth of recall.** API endpoints, library names, conventions, idioms across many ecosystems. The kind of thing a human would have to look up; the agent surfaces it inline.
- **Willingness to be redirected.** When a framing was wrong, redirecting it cost a sentence. The agent does not get attached to its earlier suggestions, which removes a friction that often slows down human collaborators.
- **Carrying the boring details.** Writing the gitignore, drafting the LICENSE, formatting the tables, generating the file tree — the agent handled all of it without complaint or error. That preserved the human's attention for the design decisions that mattered.

What it did not bring:

- **Judgment about what to build.** The agent could (and did) generate plausible features the project did not need. Cutting them was the human's job. Asked for more, the agent will give you more; deciding when "more" is wrong is yours.
- **Understanding the audience.** The agent did not know that the audience is two weeks into Python, that they live in Excel, that the laptop is locked down. Each of those facts had to be supplied. Once supplied, the agent integrated them well; supplying them was up to the human.
- **A working sense of when to stop.** Every section the agent writes can be expanded. Every architecture can be made more general. Every plan can be more thorough. Knowing when "good enough" has been reached — and resisting the temptation to go further — is the human's responsibility. The agent will keep building if you keep asking.

---

## The takeaway

If there is a generalizable point to extract from this, it is this: **agentic coding works best when the human treats the agent as a collaborator, not as a vending machine.**

A vending machine takes input and produces output. A collaborator participates in a conversation, surfaces options, takes pushback gracefully, and makes the human's judgment more effective by handling the parts that would otherwise drain attention.

The conversation that produced this repo was not "tell agent what to build, walk away." It was several hours of back-and-forth across two sessions, with workflow questions getting sourced and answered along the way, and with the agent writing-and-rewriting in response to redirection. The repo is small. The process was not.

That process is hard to see from the outside if all you ever look at is the finished code. This file is here to make it visible.

---

If you are a software engineer reading this and thinking "this is just normal collaborative design with extra steps" — yes, exactly. That's the point. Agentic coding does not change what good engineering looks like. It changes who handles which parts. Held well, it makes you faster. Held badly, it produces things you can't trust.

The repo is what fell out of the conversation. The conversation was the work.
