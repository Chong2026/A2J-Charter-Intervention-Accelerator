# A2J-Charter-Intervention-Accelerator
### A2AJ Project 2026-2027

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

## Current Tools (v1.0)

- **Interactive Network Map** — bipartite graph of NGO-counsel relationships 
  across 14 years of SCC Charter litigation (`visualizations/A2J_Counsel_NGO_Map.html`)
- **Jurisprudential Heatmap** — NGO intervention frequency by Charter section
- **Strategic Dashboards** — Top 10 NGOs and counsel across the 10 most 
  litigated Charter sections

## Planned Development (2026–2027)

- Charter Intervention Monitor — real-time SCC case alerts via RSS/JSON feeds
- Ottawa agent matching layer
- Expansion to Ontario and BC Courts of Appeal
- Intervention application toolkit with LLM-assisted drafting

## Data

All datasets are in `/data`. The core dataset covers 402 SCC Charter cases 
(2011–2025) scraped from official SCC dockets, validated at 96.67% accuracy 
against manual verification.

## How to Run

Open `notebooks/Final_Code_Chong_Tan.ipynb` in Jupyter Notebook. 
Required libraries: `pandas`, `networkx`, `pyvis`, `seaborn`, `matplotlib`, 
`beautifulsoup4`.

Install dependencies:
pip install pandas networkx pyvis seaborn matplotlib beautifulsoup4

## License

MIT License — open for use, adaptation, and contribution.

## Acknowledgements

This project uses the A2AJ Canadian case law dataset for case identification. 
Developed with support from the A2AJ Innovation Fellowship, funded by the 
Law Foundation of Ontario.
