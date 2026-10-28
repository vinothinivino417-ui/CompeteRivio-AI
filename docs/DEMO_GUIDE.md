# CompeteRivio AI: simple demo guide

## Purinjukka vendiya main point

**Business details kuduthaa, nearby similar businesses-ai find panni, review panna oru report kudukkum.**

Main menu-la three screens:

1. **New analysis** — business details, profile confirmation, competitor review, and report creation.
2. **Dashboard** — charts, selected competitor list, map, and report download.
3. **Saved reports** — previously generated reports.

## A short opening explanation

> My project is CompeteRivio AI, a competitor discovery and analysis assistant. A user enters a business name, location, and industry. The application finds nearby business candidates using OpenStreetMap, attempts AI classification, and prepares a report. Users can review the selection and add sourced evidence. Missing information is shown as unavailable rather than being invented.

## Demo steps

### 1. Show the input

Open **Start analysis**. Use:

| Field | Input |
|---|---|
| Business name | DMart |
| Location | Velachery, Chennai, Tamil Nadu, India |
| Industry | Supermarket |
| Radius | 3 km |
| Website | Leave blank unless you have verified the correct URL. |

Click **Search and generate report**. Check the matched address. If the app uses an approximate area location, point that out.

Say: “The application searches for businesses around the mapped location. Results depend on map coverage and service availability.”

### 2. Show the competitor selection

Open **Results → Competitor list**. Explain names, categories, distance, classification, and confidence.

The observed successful example had **four selected businesses: three Direct and one Indirect**. Use those numbers only if the current screen still shows that selection.

If classification needs retrying, open **Advanced tools → Competitor Analysis**, click **Classify Competitors with Gemini**, review the list, select the desired rows, and click **Approve Selected Competitors**. This makes an AI request and depends on available quota/service capacity.

Say: “These are AI classification estimates. The user reviews the businesses before using them in the report.”

### 3. Show results visually

In **Results**, switch between **Charts**, **Competitor list**, and **Map**.

Say: “Distances are straight-line estimates. Being nearby does not by itself prove competitive strength.”

### 4. Show the report

Return to **Start analysis**. If the selection changed, open **Update report or evidence** and regenerate the report. Preview it and click **Download PDF report**.

Say: “The report describes the available evidence and labels AI suggestions as proposals. If AI is unavailable, the application can create a factual report with standard validation steps.”

For a portable copy, open **More download formats → Download complete analysis (ZIP)**.

### 5. Show saved work

Open **Saved reports**, select the latest run, and demonstrate its PDF download or **Use this saved search** option.

Say: “Completed reports are stored locally. Opening a saved report does not repeat discovery or use Gemini tokens.”

## Optional evidence demonstration

Only if real measurements are available, open **Advanced tools → Evidence & Scores**. Add the measurement, its source, and its observation date.

**Theriyaadha value-ai blank-aa vidunga. Zero-nu guess panni enter panna vendam.**

Explain: “Scores use supported categories with complete comparable evidence. They are partial and relative to the selected group.”

## If a service fails during the demo

| What appears | What to do and say |
|---|---|
| Limited search coverage | Continue with the labelled candidate list; explain that it is not exhaustive. |
| Not classified / Unavailable | Explain that AI classification did not complete. A report retry does not retry classification. |
| Gemini unavailable or quota error | Use a previously saved classified run, clearly labelled as saved, or demonstrate the factual report option. |
| Missing website or measurements | Leave them unavailable. Explain what additional evidence would be needed. |

Do not repeatedly run the complete search just to retry one failed stage.

## Simple answers to common questions

**What does Gemini do?** It estimates competitor classifications and proposes validation actions. It does not independently verify the businesses.

**Where do business locations come from?** OpenStreetMap services and mapped listings, or a clearly labelled area-centre fallback.

**Are ratings and reviews collected automatically?** Not in the current implementation. They can be supplied with sources and dates.

**Why are some scores unavailable?** Comparable measurements are missing, or no complete supported category has a positive weight.

**Is the full seven-category strength score complete?** No. Three limited scoring categories are supported with supplied evidence; the score is explicitly partial.

**Is it entirely free?** No paid business-data API is used. AI availability depends on the configured Gemini account, quota, and billing settings. A no-AI factual report can be generated from saved discovery data.

**What is the main benefit?** A simple workflow that organizes nearby discovery, review, available evidence, and reporting in one place.

## Closing explanation

> This project makes an initial competitor investigation easier to organize. It combines nearby discovery, reviewed AI estimates, charts, and downloadable reports. Its sources and availability notes help users understand which conclusions still need verification.

## Before presenting

- Run the app and confirm the correct business address.
- Keep a completed saved report ready in case an external service is unavailable.
- Confirm that the PDF reflects the current approved selection.
- Explain the difference between captured data, AI estimates, and missing evidence.
- Keep API keys and environment files off the presentation screen.
