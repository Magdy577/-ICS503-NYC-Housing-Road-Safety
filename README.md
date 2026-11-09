# NYC Housing × Road Safety — ICS503 Milestone 1 (9 Nov 2026)

**Question:** Across NYC boroughs and years 2022–2025, how do affordable housing project starts compare with SIRTA serious-road-injury reporting? **This is association, not causation.**

## Official datasets (one per required domain)

1. **Housing & Development (H2)** — HPD Affordable Housing Production by Building: https://data.cityofnewyork.us/d/hg8x-zxpr — 41 columns, ~9,551 records on 30 Sep 2026. Housing metric is the **number of affordable units associated with project STARTS**, not completed homes.
2. **Transportation (T4)** — NYC DOT Serious Injury Response, Tracking & Analysis Program (SIRTA): https://data.cityofnewyork.us/d/xeqp-qz8h — 23 columns, ~13,800 records on 9 Oct 2026. **SIRTA is a selected serious-crash program, not the universe of crashes.**

## Run locally (Python 3.11 recommended)

```bash
python -m pip install -r requirements.txt
python pipeline.py
python app.py
```

Open **http://127.0.0.1:8050**. The ETL downloads the actual official datasets and writes `data/housing_clean.csv`, `data/transport_clean.csv`, `data/integrated.csv`, and `data/quality_report.json`. In Jupyter/Colab, open `ICS503_Milestone1.ipynb` and run all cells from top to bottom. **Internet is needed the first time**. There are no invented sample findings.

## Integration and cleaning

- Drop exact duplicate rows; parse dates and numeric counts; map borough labels to five canonical names; drop records with invalid/missing keys and implausible negative counts; restrict to complete study years 2022–2025.
- Housing row = building in a given project; never deduplicate valid repeats of a building across different projects. Preserve IQR high-end outliers, which may be legitimate large buildings; record the number flagged.
- The SIRTA program has its own selection process; its row counts should be called SIRTA records, not all NYC collisions.
- Aggregate **independently** by `(borough, year)`, then **one-to-one outer merge for auditing** and keep matched groups for analysis. There is no row-level join. Missing unmatched groups are **not** replaced with zero. All fields and audit statistics are in the notebook and `data/quality_report.json`.
- The dashboard computes matched aggregates **again when construction/severity filters change** rather than naively filtering previously merged records.
- Visualization 9 uses z-score differences (descriptive, not crash risk); visualization 10 compares each borough's percent share of the selected domain total; visualization 11 compares annual growth. Do not interpret any as injury risk per person.

## Website features

- Multiple dropdowns: borough, year, construction type, SIRTA severity.
- Plain-language search examples: `Brooklyn 2023 preservation fatal`, `Queens 2024 new construction severe`.
- Central **Generate Report** button updates all 12 Plotly charts and four KPI cards.
- Search, zoom, hover, filtering, 12 paired research questions and dynamic story text.

## Deploy free on Render

1. Push **all** repository files to your GitHub repository, **including `data/housing_clean.csv`, `data/transport_clean.csv`, `data/integrated.csv` and `data/quality_report.json` after running the pipeline**, and the notebook.
2. Go to Render → New → Web Service → Connect your GitHub repo. Use Python with **Build Command** `pip install -r requirements.txt` and **Start Command** `gunicorn app:server --bind 0.0.0.0:$PORT --timeout 150`.
3. Select a free instance (if available), deploy, open the URL, use search and Generate Report. The provided `render.yaml` can also be used as a blueprint.
4. If CSVs were not committed, the app tries downloading them at first startup, which is less dependable. Commit real cleaned CSVs for reliability.

## Research-question assignments (replace placeholders before submission)

Each student needs **two questions with corresponding visualizations**. Assign charts 1–2 to Member 1, charts 3–4 to Member 2, charts 5–6 to Member 3, charts 7–8 to Member 4, charts 9–10 to Member 5, charts 11–12 to Member 6. For a team of 4, questions 9–12 are supplemental; for a team of 5, questions 11–12 are supplemental.

**Team contributions:** Fill out `TEAM_CONTRIBUTIONS.md` with REAL names, IDs, and who performed which notebook cleaning, integration, website and deployment tasks. Never present placeholder allocations as actual work.

## Required submission

- GitHub repository URL; LIVE tested website URL; all student IDs; two original dataset links.
- Send **one** group email to **ICS503Data@gmail.com** by the stated deadline. The template `SUBMISSION_EMAIL.txt` contains blanks to fill.
- Include prompts used (see `PROMPTS_USED.md`) and link(s) in notebook, and upload notebook to GitHub.

## Known methodological limitations

Observational aggregates over five boroughs × four years have a small sample and substantial geographic confounding. A cross-sectional association cannot show housing causes traffic injuries. Comparing absolute counts (rather than per-person rates) can overemphasize larger boroughs. HPD starts differ from completions; SIRTA reports a selected subset of serious crashes. The reported data are only as current and complete as the API download date. A filtered severity category changes which SIRTA records are counted, not the severity definitions of events outside the program.
