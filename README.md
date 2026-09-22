# Campaign Dataset Builder

Dark-theme Streamlit application for collecting banking pages, building a reusable eligible-page dataset, coding campaign communication features, normalising values, and analysing selected records with chat and charts.

## Windows setup

1. Copy `.env.example` to `.env` and enter the provider settings.
2. Run `setup_windows.bat` once.
3. Run `run_windows.bat`.
4. Open `http://127.0.0.1:8512/`.

## Pipeline

1. Gather same-host recursive sitemap URLs and robots decisions.
2. Apply language, bank-specific banned-term, and descendant-root rules.
3. Cache raw HTML/content, cleaned text, and metadata with Camoufox.
4. AI-review eligibility and assign canonical audiences.
5. Preserve the clean page dataset independently.
6. Code one eligible page per AI request into a versioned campaign JSON.
7. Optionally create a normalised copy; originals remain unchanged.
8. Filter one or more runs for analyst chat and deterministic charts.

## Editable prompts

All model instructions are under `prompts/` and are read from disk whenever they are used. Saving a prompt is enough; a Streamlit restart is not required.

- `dataset_cleaning_system.md`: page eligibility and audience assignment.
- `campaign_coding_system.md`: final per-page feature coding.
- `campaign_features_v01.md`: full feature inventory supplied to campaign coding.
- `normalisation_suggestions_system.md`: AI replacement suggestions.
- `analyst_chat_system.md`: analyst-chat behavior.
- `cleaning_boss_default.md`, `campaign_boss_default.md`, `normalisation_boss_default.md`: editable defaults displayed in UI instruction boxes.
- `json_repair_user.md`: malformed-JSON retry instruction.
- `provider_preflight_user.md`: provider connectivity probe.

The UI instruction boxes are run-specific additions. Edit the system prompt files for permanent team-wide behavior.

## Normalisation example: verbose Adult labels

1. Open **Dataset normalisation** and select the campaign JSON.
2. Select `Target audience` as the feature.
3. In **AI suggestion instructions**, request canonical audience labels and specifically collapse descriptive adult variants to `Adult`.
4. Click **Ask AI for reviewed replacement suggestions**.
5. Review the generated exact rules, for example:

```text
Adults with savings seeking a low-risk investment. => Adult
Adults, car owners/drivers => Adult
Adults with at least €85,000 in assets seeking personal Priority Banking support. => Adult
Professional (entrepreneurs) => Professional
```

6. Remove any incorrect rule and click **Create normalised copy**.

The replacement box is an execution list, not an AI instruction box. Matching is exact whole-value matching: it does not replace substrings, prose elsewhere, or URLs.

Outputs are non-destructive:

```text
BNP-campaign-01_normalised.json
BNP-campaign-01_normalised(1).json
```

## Local data and collaboration

`data/` is ignored by Git so pulling code changes cannot overwrite a colleague's local collection or analysis data. The app creates required data directories automatically.

To share completed work manually, send the relevant JSON and place it under the corresponding local bank directory, for example:

```text
data/campaign-runs/bnp-paribas-fortis/BNP-campaign-01.json
data/campaign-runs/ing/ING-campaign-01.json
data/campaign-runs/revolut/REV-campaign-01.json
```

The Overview, campaign runner, normalisation workspace, and Chat & graphs workspace discover matching campaign JSON files automatically. Normalised copies are also discoverable. Share only intentional artifacts; never share `.env`.

## Storage

- `data/sitemaps/<bank>/latest.json`
- `data/raw/<bank>/index.json`, HTML/content JSON, and text
- `data/clean/<bank>/dataset.json`
- `data/backups/<bank>/*.zip`
- `data/campaign-runs/<bank>/<BANK>-campaign-XX.json`
- `data/graphs/*.png`

## Repository safety

`.gitignore` excludes `.env`, virtual environments, Python caches, logs, temporary files, and all generated `data/`. `.env.example`, application code, prompt files, setup scripts, and documentation remain shareable.
