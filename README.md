# book-competition-data

Find competitions with relevant deliverables, judging and prize terms.

Status: **local source pilot**, version 0.1.0. Five manually invoked official
sources now use the shared local lake runtime; there is no published remote,
scheduler, hosted API, or consumer integration. The CLI still validates explicit
exports and searches synthetic examples. It never falls back from live data to
fixtures.

## Users and boundary

For people and small teams discovering competitions and prizes.
Ranked contests with judging; acceptance-based task rewards belong to bounty.

Subcategories: hackathon, innovation-challenge, creative-contest, data-science, entrepreneurship.

Domain-specific terms: `judging_criteria`, `team_allowed`, `submission_format`, `ip_terms`.
Each record represents one program/offer intake window. A repeat intake receives
a distinct source record ID. Cross-domain packages use `related_records` rather
than copying the same award into several products.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
book-competition-data contract
book-competition-data demo --open-only
book-competition-data demo --query "hackathon"
book-competition-data validate src/book_competition_data/demo.json
python -m unittest discover -s tests -v
python -m pip install -e ".[dev]"  # pytest + pinned ruff
ruff check . && python -m pytest -q
uv sync --frozen --all-extras && uv run mypy  # locked env (uv.lock) as CI installs it
```

CI (`.github/workflows/ci.yml`) runs `ruff check`, the offline test suite and a
CLI smoke test on Python 3.10 and 3.13. `tests/test_registry.py` keeps
`sources.json`, the packaged `source*.json` configs and the contract in sync.

With dependencies already available, use `PYTHONPATH=src python3 -m book_competition_data`.
`demo` uses the fixed synthetic clock 2026-09-07T00:00:00Z unless `--as-of` is
provided. `--open-only` excludes closed, unknown-deadline, expired, stale (72h
default), and future-checked records. This is an availability filter; it does
not assert personal eligibility, selection probability, or a guaranteed payout.

Contract: `src/book_competition_data/schema.json` (`competition.v1`).
Unknown amounts, currencies, eligibility and deadlines remain unknown. Cash,
credit, discount, in-kind benefits and access are different value kinds. Never
sum them as cash income. Queries and validation are read-only and do not persist
provided files. The `live` label requires captured lineage, but validation alone
does not verify that referenced lake objects exist or prove source truth.

## Data ownership and source policy

Owner: bookchaowalit. Public program metadata only; no applications, personal
screening answers, financial credentials, cookies, or private transcripts.
See `sources.json`, `src/book_competition_data/source-nasa-space-apps-2026.json`
and `src/book_competition_data/source-cassini-challenges-2026.json`. The NASA
directory and EUSPA CASSINI pages are reviewed for public read access and are
captured only for bounded program metadata. `source.json` (the registry
`policy_file` and the default when `--source-id` is omitted) must stay
byte-identical to `source-nasa-space-apps-2026.json`; `tests/test_registry.py`
fails if the two drift, so edit both together. No spending, account creation or
messaging.

Implemented flow: approved source pull → immutable landing bytes and checksum →
Bronze Parquet and manifest through the shared lake runtime → versioned read-only
contract → consumer pull. Each product owns its source adapter and lake prefix.
Producers never write into another app's database, CRM, tasks, application
tracker, or notification system.

## Official source pilots

The five enabled sources are listed in `sources.json` and
`src/book_competition_data/source*.json`. They include [NASA Prizes, Challenges, and Crowdsourcing](https://www.nasa.gov/prizes-challenges-and-crowdsourcing/), [EUSPA CASSINI Challenges](https://www.euspa.europa.eu/cassinichallenges), [Creative Europe calls](https://culture.ec.europa.eu/calls), and [DrivenData competitions](https://www.drivendata.org/competitions/).
The page lists the **2026 NASA Space Apps Challenge** and its November 14–15,
2026 event window. It does not publish a fixed submission deadline or prize
amount on the captured directory page, so those fields remain unknown rather
than being inferred. The exact source configuration lives at
`src/book_competition_data/source-nasa-space-apps-2026.json`.

Source: [EUSPA CASSINI Challenges 2026](https://www.euspa.europa.eu/cassinichallenges).
The page publishes a September–October 2026 application window, 12 winners with
a €100,000 award each, and MVP thresholds of TRL 5 and CRL 4. It does not expose
an exact submission timestamp in the captured page, so the deadline remains
unknown and the current Rules of contest must be checked before applying. The
exact source configuration lives at
`src/book_competition_data/source-cassini-challenges-2026.json`.

Run with the existing data-lake Python environment:

```bash
export SOLO_DATA_LAKE_ROOT=/path/to/solo-data-lake
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_competition_data.capture acquire --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_competition_data.capture records --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_competition_data.capture --source-id cassini-challenges-2026 acquire --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_competition_data.capture --source-id cassini-challenges-2026 records --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
```

The lane depends on the explicit local `discovery.capture_runtime` v1. Capture
is manual, rate-limited to one check per six hours, and rejects sensitive source
markers before archival. A failed latest fetch has no fixture fallback; parser
failures leave a quarantined capture reference.

## Next implementation gates

1. Keep the five source adapters fresh and add parser fixtures when a provider changes its public contract.
2. Add live source tests, retention/access controls and runtime monitoring.
3. Connect a read-only consumer. Personal eligibility, ranking, deadlines and
   application workflow belong to consumers with separate private storage.

No runtime port is reserved. The former `opportunity.v1` is archival; `job.v1` remains a separate job-data contract.
Breaking contract changes require a new version and a consumer migration.
There is no production deployment to roll back; discard demo output or restore
the previous contract version locally. Source permission, live availability,
lake replay and real eligibility are **unverified**, not passing gates.
