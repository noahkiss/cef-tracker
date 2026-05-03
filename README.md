# cef-tracker

> A small Python project that pulls a monthly snapshot of closed-end fund (CEF) data from public sources, written two ways: as a single-file script and as a structured package.

The same problem, solved twice. Read both. Decide which style fits the next tool you build.

---

## Table of contents

- [What this is](#what-this-is)
- [Two ways to build the same thing](#two-ways-to-build-the-same-thing)
- [Quick start](#quick-start)
- [The problem domain](#the-problem-domain)
- [Data sources](#data-sources)
  - [CEFConnect (primary, free)](#cefconnect-primary-free)
  - [Alternative free sources](#alternative-free-sources)
  - [Morningstar (paid) — a primer](#morningstar-paid--a-primer)
- [Project layout](#project-layout)
- [Tooling: pip, uv, and what to use when](#tooling-pip-uv-and-what-to-use-when)
- [Learning resources](#learning-resources)
- [Why README.md? Why AGENTS.md?](#why-readmemd-why-agentsmd)
- [How this project came together](#how-this-project-came-together)
- [License](#license)

---

## What this is

Closed-end funds (CEFs) are exchange-traded investment funds that trade at a market price which can differ from their underlying net asset value (NAV). They are widely used for income strategies, often employ leverage, and pay distributions that may include return of capital. Anyone who follows them at scale ends up wanting a periodic snapshot of fields like leverage ratio, distribution rate, discount-to-NAV, UNII, and trailing total returns.

Most of those fields update on a monthly cadence as funds file 19a-1 distribution notices, N-PORT holdings reports, and shareholder letters with the SEC. Aggregators like CEFConnect normalize the data into a clean per-fund page, and their underlying JSON API makes a small Python tool a practical way to capture the snapshot programmatically.

This project does exactly that: given a list of tickers, it fetches the current values for a configured set of fields and writes them to a timestamped Excel + CSV file. Two implementations live in this repo so you can compare the trade-offs of each style.

---

## Two ways to build the same thing

This is the core idea of the repo. The same problem, two equally legitimate implementations.

### `script/` — single-file Python

A self-contained `cef_snapshot.py` you can read end-to-end in ten minutes. Top-down structure. Functions, not classes. Configuration is a plain text file of tickers. The "Automate the Boring Stuff" tradition: useful work delivered fast, all the logic in one head, easy to share, easy to modify by editing one file.

Right call when:

- You are the only user.
- The tool is small enough to fit in working memory.
- You expect to either keep it as-is or eventually rewrite it.
- The cost of an extra abstraction is higher than the cost of editing the script.

### `package/` — multi-module Python

The same job decomposed into models, sources, output writers, and a diff engine. Configuration lives in `config.toml`. Adding a new data source means writing a new file that conforms to a small interface; adding a new output format works the same way. Tests pin down the diff logic.

Right call when:

- Multiple people will touch it, now or later.
- You expect to add data sources, output formats, or alerting over time.
- The thing will live for years and you want change to be cheap.
- The cost of an extra abstraction is lower than the cost of every future edit being a careful read of the whole script.

### The honest comparison

| | `script/` | `package/` |
|---|---|---|
| Files | 1 Python file | ~10 Python files |
| Lines of code | ~150 | ~500 |
| Config format | plain text ticker list | TOML |
| Add a ticker | edit the text file | edit the TOML |
| Add a field | edit a constant in the script | edit the TOML |
| Add a new data source | rewrite the fetch function | add a new file conforming to `DataSource` |
| Add a new output format | add a function and call it from `main()` | add a new file conforming to `OutputWriter` |
| Detect month-over-month change | open two extracts side by side in Excel | `diff.py` runs automatically |
| Tests | none | targeted pytest suite |
| Time to first working version | one sitting | a day or two |
| Time to extend later | proportional to script length | proportional to the new feature, not to existing code |

Neither is "better engineering." The skill is choosing the right one for the situation, and recognizing when a tool has outgrown its current style and should migrate.

---

## Quick start

Pick a folder and follow its README:

- [`script/`](./script/README.md) — single file, fastest to understand
- [`package/`](./package/README.md) — structured, designed for change

Both versions write to a `extracts/` directory in their own folder, with filenames like `extract-202605030001.xlsx` and `extract-202605030001.csv`. Neither version writes into an existing workbook — every run produces a standalone file you open separately. This is intentional: a tool that automatically modifies a shared workbook is one bad assumption away from corrupting weeks of manual annotations.

Sample outputs from a real run against five tickers (BIT, BST, PDI, UTG, RFI) are committed to each folder's `sample-output/` directory so you can see the shape of the data without running anything.

---

## The problem domain

A short orientation for anyone who hasn't worked with CEF data before. Skip if you have.

Closed-end funds issue a fixed number of shares at IPO, then trade on an exchange like a stock. Because the share count is fixed, the market price floats independently of the underlying NAV. The difference is the **discount** (or **premium**) to NAV, and it is the central reason CEFs are interesting as an asset class — buying at a wide discount and holding for distribution income is a recognized strategy.

Several fields drive most analysis:

- **NAV and market price** — the spread is the discount/premium.
- **Leverage ratio and leverage cost** — many CEFs borrow to amplify returns. When short rates rise, leveraged funds get squeezed.
- **Distribution rate and ROC %** — how much of the headline yield is real income versus return of capital. A high yield that is mostly ROC is eroding NAV.
- **UNII (Undistributed Net Investment Income)** — whether the fund is earning enough to cover its distribution. Negative and trending down is a warning.
- **Trailing total returns** (1y / 3y / 5y / 10y) — performance over standard windows, calculated assuming distributions are reinvested at NAV.

These fields move on different cadences:

- Price, NAV, and discount: daily, from the exchange tape.
- Distribution rate and ROC: monthly-ish, from 19a-1 filings the fund issues with each distribution.
- Leverage cost, UNII, holdings: monthly to semi-annually, from N-PORT and N-CSR shareholder reports.
- Trailing returns: meaningful changes only on a monthly cadence at most.

A monthly snapshot is the right cadence for the slow-moving fundamentals; daily snapshots would be noise.

---

## Data sources

### CEFConnect (primary, free)

[CEFConnect](https://www.cefconnect.com) is a free aggregator owned by Nuveen. It normalizes data from SEC filings, the exchange tape, and Morningstar's calculated performance metrics into a clean per-fund page. The page hydrates from a small undocumented JSON API plus a server-rendered HTML metadata block, and both implementations in this repo combine the two transports.

Live JSON endpoints used by both versions:

| Endpoint | Returns |
|---|---|
| `https://www.cefconnect.com/api/v3/pricinghistory/{TICKER}/{range}` | Daily price, NAV, and computed discount per day (latest row gives current values) |
| `https://www.cefconnect.com/api/v3/performance/annualized/{TICKER}` | Trailing total returns: 3M / 6M / 1Y / 3Y / 5Y / 10Y, both price-based and NAV-based |
| `https://www.cefconnect.com/api/v3/distributionhistory/fund/{TICKER}/{from}/{to}` | Per-distribution rows with income vs. capital-return breakdown (used to compute distribution rate and ROC %) |
| `https://www.cefconnect.com/api/v3/search/tickers` | Full ticker list with each fund's name (one call per run, cached) |

The slow-moving fund metadata — sponsor, leverage %, leverage cost, UNII, expense ratio — is no longer exposed in the JSON API and lives in the server-rendered `https://www.cefconnect.com/fund/{TICKER}` HTML. Both implementations parse it with `beautifulsoup4`.

No authentication required. Response shapes can change without notice (the API is undocumented) — an earlier `funds/{TICKER}` JSON endpoint that returned everything in one call has already been removed once during this project's lifetime, which is why committed test fixtures are valuable. See [MAKING-OF.md](./MAKING-OF.md), Round 9, for the story.

### Alternative free sources

Worth knowing about even if this project does not use them:

| Source | Cadence | Notes |
|---|---|---|
| [SEC EDGAR](https://www.sec.gov/edgar) — 19a-1 distribution notices | As filed (~10 days after distribution) | Authoritative source for distribution amounts and ROC categorization, often a couple of weeks ahead of CEFConnect. RSS feeds available per CIK. The early-warning play if you want to detect distribution changes before aggregators reflect them. |
| SEC EDGAR — N-PORT holdings reports | Monthly, ~60 days lag | Authoritative source for portfolio composition. Useful if you want holdings-level analysis. XML format, requires parsing. |
| Fund sponsor fact sheets (Nuveen, BlackRock, PIMCO, Cohen & Steers, Eaton Vance) | Monthly, ~10 business days after month end | Often fresher than CEFConnect for that sponsor's own funds. PDF format, parseable with `pdfplumber` for known layouts. |
| [CEFA.com](https://www.cefadvisors.com) | Daily | Same Morningstar data pipe as CEFConnect. Largely redundant. |
| `yfinance` | Daily | Easy to use but Yahoo Finance's CEF coverage is thinner than CEFConnect. Useful for cross-validation of price and NAV. |

The package version of this project is structured so that adding any of these as additional data sources means writing a new file conforming to the `DataSource` interface. The script version would require rewriting the fetch logic.

### Morningstar (paid) — a primer

If your firm has Morningstar access, there are three flavors:

1. **Excel add-in** — most advisors use this. Cell functions like `=MStarData("FUND_ID", "Field")` pull data directly into a worksheet. No code required, but limited automation. Worth checking with your firm's IT whether the add-in is licensed for your seat.
2. **Direct Web Services API** (REST, JSON) — Bearer-token authentication, ~3000 data points per fund, field codes like `LeverageRatio` and `OneYearTotalReturn`. Requires a contract amendment with Morningstar. Once enabled, integrating it into the package version of this project is roughly a 50-line `MorningstarSource(DataSource)` implementation.
3. **Bulk SFTP delivery** — institutional only. CSV or parquet files dropped on a schedule. Unlikely for small practices.

The shape of Morningstar data is similar enough to CEFConnect's that the same internal `FundSnapshot` model works for both with field-mapping translation. This is one of the things the `DataSource` abstraction in the package version is designed to make easy.

---

## Project layout

```
cef-tracker/
├── README.md                ← this file
├── AGENTS.md                ← orientation for AI coding agents
├── CLAUDE.md                ← @AGENTS.md (Claude Code convention)
├── LICENSE                  ← MIT
├── .gitignore
│
├── script/                  ← single-file implementation
│   ├── README.md            ← walkthrough
│   ├── cef_snapshot.py
│   ├── tickers.txt
│   ├── requirements.txt
│   └── sample-output/
│
└── package/                 ← multi-module implementation
    ├── README.md            ← design walkthrough
    ├── pyproject.toml
    ├── config.toml
    ├── cef_tracker/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── models.py
    │   ├── sources/
    │   ├── output/
    │   ├── diff.py
    │   └── main.py
    ├── tests/
    │   ├── test_diff.py
    │   ├── test_cefconnect.py
    │   └── fixtures/
    └── sample-output/
```

---

## Tooling: pip, uv, and what to use when

### pip

`pip` is the default Python package installer; it ships with every Python install. The setup instructions in each folder use `pip install -r requirements.txt`. This is the path of least resistance and works on any machine that has Python.

### uv

[uv](https://github.com/astral-sh/uv) is a much faster modern alternative written in Rust. It installs and resolves dependencies in seconds rather than minutes, manages virtual environments, and can pin a Python version per project. It is becoming the default for new Python projects in 2026.

Installation requires no admin rights and lands in your user directory:

- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Both install to `~/.local/bin/` (or `%USERPROFILE%\.local\bin\` on Windows). Useful on locked-down corporate machines where you do not have administrator rights.

Equivalent commands:

| pip | uv |
|---|---|
| `python -m venv .venv` then `pip install -r requirements.txt` | `uv venv && uv pip install -r requirements.txt` |
| `pip install requests` | `uv pip install requests` |
| `python script.py` | `uv run script.py` |

This project documents the pip-based path because it works for everyone. uv works identically for those who prefer it.

---

## Learning resources

The resources below are organized by which version of the project they relate to, not by difficulty.

### Useful regardless of which folder you read

- [Automate the Boring Stuff with Python](https://automatetheboringstuff.com) by Al Sweigart — the canonical free book on script-style Python. Highly recommended for anyone using Python to solve real problems.
- [Real Python](https://realpython.com) — high-quality articles at every level, searchable by topic.
- [Python documentation](https://docs.python.org/3/) — the standard library reference. Worth bookmarking; it is unusually well-written for an official language reference.

### For the `script/` style

- [Automate the Boring Stuff](https://automatetheboringstuff.com) again — chapters 1–8 cover the full vocabulary used in `script/cef_snapshot.py`. Chapter 12 ("Web Scraping") covers `requests` + `beautifulsoup4`, which is exactly the pattern the script uses to pull the metadata fields CEFConnect no longer exposes via JSON (sponsor, leverage, UNII, expense ratio). If a `find()`/`select()` call in the script looks unfamiliar, that chapter is the right reference.
- [Beautiful Soup documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) — the canonical reference. The "Searching the tree" and "CSS selectors" sections cover ~95% of what most scrapers need.
- [pandas user guide](https://pandas.pydata.org/docs/user_guide/index.html) — DataFrames, the `read_*` and `to_*` functions, and basic indexing.
- [requests quickstart](https://requests.readthedocs.io/en/latest/user/quickstart/) — five minutes of reading covers everything you need.

### For the `package/` style

- [Cosmic Python](https://www.cosmicpython.com) (Percival & Gregory, free online) — a book-length treatment of why you would structure a Python project the way `package/` is structured.
- [Fluent Python](https://www.fluentpython.com) (Luciano Ramalho) — the book to graduate to once you are comfortable. Covers dataclasses, abstract base classes, descriptors, and the rest of the modern Python toolbox in depth.
- Python stdlib modules used by the package version, all worth a 10-minute read of their docs:
  - [`dataclasses`](https://docs.python.org/3/library/dataclasses.html) — what `@dataclass` does and why
  - [`abc`](https://docs.python.org/3/library/abc.html) — abstract base classes, the basis of the source/output interfaces
  - [`pathlib`](https://docs.python.org/3/library/pathlib.html) — modern file path handling
  - [`tomllib`](https://docs.python.org/3/library/tomllib.html) — parsing TOML config in the standard library
- [pytest documentation](https://docs.pytest.org/) — the testing framework used in `package/tests/`.

---

## Why README.md? Why AGENTS.md?

A short tangent worth reading once.

**README.md** is a convention with a long history. The earliest documented `README` files come from PDP-10 and early Unix software distributions in the 1970s, when shipping someone a tape of source code without a note explaining what was inside was considered rude. The all-caps filename is deliberate: in ASCII, uppercase letters sort before lowercase, so `README` appears at the top of `ls` output. The convention was formalized in the GNU coding standards in the 1980s, and the `.md` (Markdown) suffix became standard around 2008 when GitHub started rendering READMEs as formatted HTML on the project page.

Fifty years on, every project has one for the same reason: the next person opening the directory needs a hand finding their way around. That person is sometimes you, six months later, having forgotten what you wrote.

**AGENTS.md** is the 2026 update. Large language models that read codebases — Claude Code, Cursor, Aider, GitHub Copilot, OpenAI Codex — do not automatically read README.md. They look for a small set of dedicated files that contain instructions written for them: how the project is organized, what conventions to follow, what to avoid. `AGENTS.md` has emerged as the vendor-neutral convention for this purpose, and most major coding-agent tools now read it on session start. Claude Code additionally reads `CLAUDE.md`, which in this project is just a one-line pointer to `AGENTS.md` so both audiences get the same content.

Same idea as the 1970s convention, extended to a new kind of reader.

---

## How this project came together

For a narrative of the design conversation that produced this repo — the iterations, the reframings, the trade-offs that got considered and rejected, and reflections on what working with a coding agent actually looks like in practice — see [MAKING-OF.md](./MAKING-OF.md).

It exists because there is a popular but inaccurate model of agentic coding that goes "type a request, walk away." The actual process is iterative and judgment-driven, and that process is hard to see from the outside if all you ever look at is the finished code.

## License

MIT. See [LICENSE](./LICENSE).
