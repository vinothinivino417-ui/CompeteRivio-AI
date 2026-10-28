# CompeteRivio AI

## Project documentation

Prepared: 26 October 2026. This document describes the implemented local application and its current limits.

## 1. Project in one sentence

CompeteRivio AI finds nearby businesses, helps a user review their competitive relevance, and prepares a report from the information available.

## 2. Abstract

Small businesses often need a convenient starting point for identifying nearby competitors. CompeteRivio AI combines OpenStreetMap discovery, optional Gemini classification, public website checks, and user-supplied measurements in a Streamlit application. A user enters a business name, location, and industry. The application locates a mapped business or explicitly uses an approximate area centre when the listing cannot be found. It discovers nearby candidates, attempts to classify a limited selection, and creates a downloadable report. The user can review the selection, add sourced evidence, view charts and a map, and save reports locally. Missing information remains unavailable. AI classifications and recommendations are estimates requiring review.

## 3. Problem and objectives

The problem is the effort needed to identify nearby businesses and organize information for an initial competitor review.

The project aims to:

- Collect the main search details in one form.
- Find nearby business candidates and show their source and approximate distance.
- Use AI to suggest Direct, Indirect, or Irrelevant classifications when the service is available.
- Let the user review and approve the selected businesses.
- Compare sourced measurements without turning missing data into zero.
- Export a report and preserve completed analyses locally.

The application supports an initial investigation. It does not independently establish market share, business quality, customer demand, or commercial advantage.

## 4. Simple user workflow

**Business details → nearby discovery → classification attempt → review → report and downloads**

| Main screen | Purpose |
|---|---|
| Start analysis | Enter details, start a search, see availability notes, download a report. |
| Results | View charts, the selected business list, or the map, one section at a time. |
| Saved reports | Open previous reports, download them, compare saved selections, or reuse a search. |

Advanced tools contain Business & Discovery, Competitor Analysis, Evidence & Scores, Keyword Intelligence, Marketing Intelligence, and AI Insights & Reports. They are optional tools for correcting or enriching the main workflow.

Appearance uses the native top-right menu: **⋮ → Theme → Light or Dark**.

## 5. Example input and observed output

| Field | Example |
|---|---|
| Business name | DMart |
| Location | Velachery, Chennai, Tamil Nadu, India |
| Industry | Supermarket |
| Radius | 3 km |
| Website | Optional; leave blank when unknown. |

In a user-provided demonstration screenshot, a reviewed selection of four businesses showed three Direct and one Indirect classification. This describes that selection, not every supermarket in the area. The classifications are AI estimates and the results may differ on another run.

![Observed classified selection: three Direct and one Indirect](images/classification-example.png)

## 6. Main modules and data flow

| Stage | Implementation | Result |
|---|---|---|
| Interface and navigation | `dashboard_preview.py`, `dashboard/navigation.py` | Three main screens with optional advanced tools. |
| Automated workflow | `services/automatic_analysis.py` | Coordinates lookup, discovery, website checks, classification, and reporting. |
| Location lookup | `services/geocoding.py`, business discovery | Mapped listing or labelled approximate area location. |
| Nearby discovery | `dashboard/competitor_discovery.py`, discovery fallback services | Candidate businesses with identifiers, sources, and straight-line distances. |
| AI assistance | `services/ai_insights.py` | Classification estimates and proposed validation actions. |
| Website evidence | `services/website_analysis.py` | Captured public page text, source URLs, and retrieval times. |
| Manual evidence and scoring | `services/competitor_evidence.py` | Validated measurements and explicitly partial relative scores. |
| Keyword and marketing views | Keyword and marketing services and dashboard pages | Comparisons restricted to captured terms and supplied measurements. |
| Report generation | `services/report_content.py`, `services/report_export.py` | Evidence-based narrative with labelled suggestions; PDF and text exports. |
| Persistence and history | Workspace storage, analysis history, backup and comparison services | Local workspace, saved snapshots, restore, and selection comparisons. |
| Portable export | `services/analysis_bundle.py` | ZIP containing the report, CSVs, JSON snapshot, and checksum manifest. |

## 7. Technologies used

| Technology | Role |
|---|---|
| Python | Application logic and data processing. |
| Streamlit | Web interface, forms, navigation, tables, and native themes. |
| OpenStreetMap, Nominatim, Overpass | Mapped location lookup and nearby discovery. |
| Gemini through `google-genai` | Optional classification and suggested validation actions. |
| Requests and HTTP utilities | Public data and website requests. |
| pandas | Tabular processing and CSV exports. |
| Plotly | Interactive comparison charts. |
| ReportLab | PDF report generation. |
| JSON and Python standard library | Local persistence, backups, ZIP files, and checksums. |

The app uses no paid business-data API. Gemini usage is subject to the configured account's quota and billing settings; the app cannot guarantee that every available model or account is free. Public map and website services can impose access limits or become unavailable.

## 8. Implemented features

### Discovery and reporting

- One-form automated analysis, optional search radius and website checks.
- Mapped business lookup with an explicitly labelled area-centre fallback.
- Nearby discovery with a limited best-match fallback when the primary map service fails.
- AI classification of up to 15 candidates in the automatic workflow.
- Manual review, filtering, and approval of competitors.
- Charts, distance comparisons, map, and CSV exports.
- Report retry from saved businesses without repeating discovery.
- A factual report when AI recommendations cannot be generated, plus an explicit no-AI report option.

### Evidence and scoring

- Manual or CSV entry of rating, review count, active-ad count, and keyword count.
- Source and observation-date validation for supplied measurements.
- Clear distinction between blank/unavailable and an observed zero.
- Partial scores from comparable supported categories only.
- Adjustable weights; Default, Retail, Healthcare, and Restaurants starting presets.
- Category contributions and the business's gap versus the selected competitors' average.
- Evidence date review reminders and a CSV checklist. The 90-day window is a reminder, not proof that evidence has expired or is accurate.

### Website, keyword, and marketing views

- Conservative public website checks with URL validation, access controls, caching, and bounded requests.
- Captured page titles, descriptions, headings, link labels, contact text, and candidate terms where available.
- Keyword overlap and potential content gaps based on captured samples only.
- Sourced ad-count comparisons and captured website messaging, without invented ad creatives or campaign performance.

### Saved work and exports

- Automatic local workspace persistence.
- Up to 50 saved report snapshots, without silently deleting older runs.
- History backup and validated restore with duplicate skipping.
- Comparison of saved selections for the same business and location.
- Reuse of saved search details without automatically making new API calls.
- PDF, Markdown, CSV, JSON, and complete-analysis ZIP downloads.
- Native Light and Dark modes, with theme-aware charts.

## 9. Scoring method and limits

Currently supported scoring categories are Reputation, Paid activity, and Keyword strategy. They use supplied rating/review counts, active-ad counts, and keyword counts respectively. These are limited proxies, not the full original seven-category strength model.

A category is included only when the business and every selected competitor have all its required measurements and its selected weight is positive.

For each metric:

`Normalized value = 100 × (value − minimum) / (maximum − minimum)`

Equal values receive a neutral 50. Reputation averages normalized rating and review count. The overall partial score is the weighted average of included category scores.

- Scores are relative to the selected group. Changing the group can change scores.
- Missing values do not become zero.
- Default scoring-weight coverage can reach 50% with the current supported fields.
- Custom chosen-weight coverage can reach 100% by assigning zero weight to unavailable categories. That does not complete the seven-category model.
- The score gap compares supplied evidence; it is not a measured business-performance advantage.

## 10. Failure handling

| Situation | Application behaviour |
|---|---|
| Exact business listing missing | Attempts an area lookup and labels the location and distances as approximate. |
| Primary map service unavailable | Attempts a bounded fallback and warns that coverage is limited. |
| AI classification fails | Keeps nearby candidates unclassified; does not invent Direct/Indirect labels. |
| No valid classifications | Displays classification counts as Unavailable rather than suggesting zero competitors. |
| AI report request fails | Builds a labelled factual report with standard validation steps. |
| Website missing or inaccessible | Marks website evidence unavailable. |
| Measurements missing | Shows unavailable measurements and scores; avoids fabricated values. |
| Invalid backup or full history | Rejects the restore without partially importing or deleting existing records. |

## 11. Running the existing installation

In PowerShell:

```powershell
cd "C:\Users\VINOTHINI\OneDrive\Desktop\CompeteRivio Ai\CompeteRivio-AI"
python -m streamlit run dashboard_preview.py
```

Open `http://localhost:8501`.

Gemini reads `GEMINI_API_KEY` or `GOOGLE_API_KEY` from the environment, including the project's local `.env` file. Keep real keys private. The factual report option can work without an AI request once discovery data is available.

Implementation note for a fresh installation: the repository's pinned `requirements.txt` differs from the currently verified Python environment and does not list ReportLab. Review and reconcile dependencies before promising a reproducible clean installation. The existing app was tested with Streamlit 1.62.0, pandas 3.0.5, Plotly 7.1.0, ReportLab 5.1.0, and google-genai 2.33.0.

## 12. Validation and demonstration evidence

The most recent full automated run passed **128 tests**. These cover workflow failures, classification availability, report content, persistence, history and restore, exports, scoring, and UI interactions. Native Light/Dark chart behaviour was also checked in the browser. Tests do not independently validate map listings or AI business judgments, and they do not guarantee external service availability.

Tests can be run from the project folder:

```powershell
python -m unittest discover -s tests -q
```

For a presentation, capture the current input form, classified selection, results charts/map, downloaded report, and saved-history entry. Describe any failed or unavailable step honestly.

## 13. Known limitations and future work

Current limitations include external service availability, incomplete map coverage, uncertain branch identity, straight-line rather than travel distances, and unverified AI interpretations. A same-brand branch may appear in a candidate list and needs user review. The app does not automatically supply verified ratings, reviews, Google positions, search volumes, social engagement, market share, prices, or Meta ad creatives. Website text is self-published and may be incomplete or inaccessible.

Future work could improve branch/chain handling, dependency reproducibility, licensed evidence integrations, source-specific observation history, and evaluation against manually labelled competitor datasets. These are future directions, not completed features.

## 14. Conclusion

CompeteRivio AI provides a local workflow for nearby business discovery, reviewed AI classification, evidence organization, and report export. Its results are a starting point for investigation. The application preserves sources and availability limits so the user can distinguish observed information from estimates and missing evidence.
