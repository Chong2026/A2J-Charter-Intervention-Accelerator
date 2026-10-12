# A2J-Charter-Intervention-Accelerator
### A2AJ Project 2026-2027 (a2aj.ca)

An open-source toolkit mapping intervenor coalitions in Supreme Court of Canada
Charter litigation to advance access to justice.

Developed as part of the A2AJ Innovation Fellowship (2026–2027),
Osgoode Hall Law School, York University.

## What This Project Does

Third-party intervention shapes Canadian constitutional law — yet the ecosystem
of who intervenes, and who represents them, has never been systematically mapped.
This project scrapes and analyzes 402 SCC Charter cases (2011–2025) to visualize
the network of NGO intervenors and individual counsel, helping under-resourced
legal clinics find pro bono constitutional lawyers and vice versa.

## Current Tools

**Analysis of past cases (v1.0)**

- **Interactive Network Map** — bipartite graph of NGO-counsel relationships
  across 15 years of SCC Charter litigation (`visualizations/A2J_Counsel_NGO_Map.html`)
- **Jurisprudential Heatmap** — NGO intervention frequency by Charter section
- **Strategic Dashboards** — Top 10 NGOs and counsel across the 10 most
  litigated Charter sections

**Charter Intervention Monitor (in development)**

- Reads the SCC's public "Applications for Leave" JSON feed and finds newly
  granted leave applications.
- Flags likely Charter cases using the keywords on the SCC docket page. This is a
  heuristic and can miss constitutional cases that do not use Charter keywords.
- Tags each Charter case with the sections and doctrines it raises (for example
  `s. 2(a)`, `s. 11(b)`, `s. 7 – arbitrariness`), from explicit citations and the
  Registry's keyword phrases (`charter_tags.py`, a lawyer-editable table).
- Extracts the intervention deadlines from the Registrar's scheduling letter on
  the docket (motion for leave to intervene, responses, replies, factums).
- Publishes a public page of Charter appeals open for intervention, with a
  subscribable deadline calendar (`calendar.ics`) and open data (`cases.json`),
  built by `build_site.py` and hosted on GitHub Pages.
- Checks its own health each run: if the SCC feed or pages change in a way that
  could make it miss cases, it emails a warning and the run shows as failed.
- Runs weekly on GitHub Actions (`.github/workflows/weekly-monitor.yml`) and emails
  an alert for each new Charter case. Alerts currently go to the maintainer only;
  subscriber sign-up is planned.

## Planned Development (2026–2027)

- Ottawa agent matching layer
- Expansion to Ontario and BC Courts of Appeal
- Intervention application toolkit with LLM-assisted drafting

## Repository Layout

```
notebooks/       original analysis notebook (SCC Charter cases 2011–2025)
visualizations/  network map, heatmap and dashboards
data/            datasets, plus monitor.sqlite (state of the Monitor)
run_monitor.py   Monitor entry point: feed -> docket pages -> SQLite -> email
scc_parse.py     parsing of SCC decision pages, dockets and scheduling letters
alerts.py        alert email formatting and sending
run_weekly.ps1   optional local runner for Windows
scripts/         feed probes used during development
sql/             draft schema for the planned database migration
docs/            data-source and licensing log, scheduling notes
```

## Data

The core dataset covers 402 SCC Charter cases (2011–2025) scraped from official
SCC dockets, validated at 96.67% accuracy against manual verification. See
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for each source and its terms of use.

## How to Run

**Analysis notebook:** open `notebooks/Final_Code_Chong_Tan.ipynb` in Jupyter
Notebook. Required libraries: `pandas`, `networkx`, `pyvis`, `seaborn`,
`matplotlib`, `beautifulsoup4`.

```
pip install pandas networkx pyvis seaborn matplotlib beautifulsoup4
```

**Monitor (locally):** set a contact address for the User-Agent header, then run:

```
# PowerShell
$env:SCC_MONITOR_CONTACT = "you@example.com"
uv run --with requests --with beautifulsoup4 --with lxml python run_monitor.py
```

To send email alerts, also set `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`,
`ALERT_SMTP_USER`, `ALERT_SMTP_PASS` and `ALERT_TO` (see `secrets.example.ps1`).
Without them the Monitor still runs and simply skips the email.

To flag particular sections or doctrines, set `ALERT_SECTIONS`, e.g. `s. 7, s. 15`
(on GitHub: Settings > Secrets and variables > Actions > Variables). `s. 7` also
matches its doctrines such as `s. 7 – arbitrariness`; `s. 2` matches `s. 2(a)` to
`s. 2(d)`. By default (`ALERT_SECTIONS_MODE=extra`) matching cases get an extra
priority email and every Charter case still arrives in the usual alert; with
`ALERT_SECTIONS_MODE=only`, only matching cases are emailed.

**Tests:**

```
uv run --with pytest --with requests --with beautifulsoup4 --with lxml pytest
```

**Checking the Charter classifier's accuracy:** `scripts/validate_classifier.py`
samples known Charter cases from the 402-case dataset plus other dockets, fetches
their SCC docket pages, and reports accuracy, recall and precision once the other
dockets have been labelled by hand. See the instructions at the top of the script.

## License

Code: MIT License — open for use, adaptation, and contribution.
Any datasets published by this project will be released under CC-BY or CC0, as
noted in each dataset's documentation.

## Acknowledgements

This project is funded through the Innovation Fellowship of the **Access to
Algorithmic Justice (A2AJ) Project** at Osgoode Hall Law School, York University,
with support from the **Law Foundation of Ontario**. It uses the A2AJ Canadian
case law dataset for case identification.
