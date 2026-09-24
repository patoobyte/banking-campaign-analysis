# Editable AI prompts

Every prompt is read from disk when used. Save a file and the next AI request uses it; Streamlit does not need restarting.

## Main prompts

- `dataset_cleaning_system.md`: **initial AI cleaning**—decides URL/page eligibility and assigns basic target audiences.
- `campaign_coding_system.md`: one-page-at-a-time final campaign and communication coding.
- `campaign_features_v01.md`: feature inventory supplied with each campaign-coding request.
- `demo_campaign_features.md`: demo feature framework with 1?5 communication positions and controlled, screenshot-based visual labels; the demo CSV separates labels from their evidence. Recode earlier campaigns to populate new label columns.
- `analyst_chat_system.md`: analyst behavior, injected selected context, and the validated `<graphs>` directive for requesting up to three Matplotlib charts. The model never executes Python.
- `normalisation_suggestions_system.md`: proposes reviewed exact-value normalisation rules.

## Supporting prompts

- `cleaning_boss_default.md`: default text shown in the cleaning instruction box.
- `campaign_boss_default.md`: default text shown in campaign coding.
- `normalisation_boss_default.md`: default text shown in normalisation.
- `json_repair_user.md`: retry message after malformed JSON.
- `provider_preflight_user.md`: provider test message.

## Template placeholders

Use double braces exactly as shown. Python replaces these immediately before the request:

- `{{BANK}}`: selected bank name.
- `{{AUDIENCES}}`: allowed basic audience labels.
- `{{BOSS_INSTRUCTION}}`: current optional instruction-box value.
- `{{ADDITIONAL_INSTRUCTION}}`: current analyst chat instruction.
- `{{CONTEXT_JSON}}`: campaign records selected by runs, languages, and filters.

Page text, source metadata, feature definitions, and normalisation value lists are sent as structured user payloads, not interpolated into the system-prompt text.

Do not rename or remove required placeholders unless the corresponding Python call is also changed. Unresolved placeholders cause a clear runtime error rather than silently sending a broken prompt.
