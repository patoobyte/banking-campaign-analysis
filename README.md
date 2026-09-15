# Market Signal — ING Belgium competitive-intelligence POC

Market Signal is a Streamlit proof of concept for evidence-based comparison of public bank websites. It combines an agentic LangGraph/LangChain research loop, installed Google Chrome, screenshot-based vision analysis, local SQLite history, individual bank profiles, cross-bank comparison, and grounded chat.

## General concept

Each bank is researched independently so evidence is not mixed. The application starts from approved public domains, opens pages in an isolated Chrome profile, reads navigation and interactive controls, and lets the AI decide which relevant product, pricing, comparison, account-opening, savings, cards, loan, investment, insurance, communication, and visual routes to inspect. A final multimodal pass receives collected text and screenshots and builds a structured profile. Completed profiles can then be compared.

### The AI can currently

- Explore allowed public bank domains from supplied seed URLs.
- Check `robots.txt` before direct navigation.
- Keep one Chrome session open during a bank run.
- Navigate discovered URLs; click visible links, buttons, tabs, menus and accordions; scroll; go back; and inspect the current page.
- Preserve cookie and navigation state in an isolated project profile.
- Save screenshots and treat visible screenshot content as evidence.
- Extract and compare communication style, terminology, information architecture, UX friction, product propositions, prices when visible, CTAs, journeys, colors, imagery, campaigns, trust signals, and support.
- Store dated evidence and reports locally.

### Current limitations

- It accesses only public pages and must not log in or collect private banking data.
- It stays on configured allowed domains; it does not search the open web.
- Website anti-automation systems, maintenance responses, unusual components, CAPTCHAs, and changing labels may reduce coverage.
- A page/tool budget limits each run. The maximum is not a guarantee that every category will be found.
- Vision can read screenshots but may still miss small, hidden, collapsed, or low-resolution details.
- Failed clicks are recoverable, but a site redesign may require prompt or tool adjustments.
- Findings are POC intelligence, not audited legal, financial, accessibility, or compliance conclusions.
- Human review of sources and screenshots is required before business decisions.

## Windows installation

1. Install Python 3.11 and Google Chrome.
2. Extract the project ZIP.
3. Double-click `setup_windows.bat` once.
4. Put the provider key in `.env` when Notepad opens.
5. Double-click `run_windows.bat`.
6. Open `http://localhost:8501`.

See `installation files.txt`, `RUN_MANUALLY.txt`, and `TROUBLESHOOTING.txt` for alternatives.

## Typical workflow

1. Open **Run analysis**.
2. Select a bank and use **Agentic investigation**.
3. Review allowed seed URLs.
4. Enable visual analysis.
5. Choose page and tool-step budgets.
6. Run each bank separately.
7. Review detailed evidence under **Bank profiles**.
8. Build the cross-bank comparison after individual profiles are current.
9. Use **Ask intelligence** for questions grounded in saved profiles.

## Editing prompts

Yes: edit the Markdown files in `prompts/`.

- `prompts/bank_analysis.md` controls the individual bank research/profile schema, reasoning priorities, screenshot rules, product and journey analysis, tone, visual analysis, and required JSON fields.
- `prompts/comparison.md` controls how saved bank profiles are compared and how alerts/recommendations are returned.

Recommended prompt workflow:

1. Make a copy of the prompt file before major changes.
2. Keep `{bank}` in `bank_analysis.md`; the application replaces it with the selected bank.
3. Preserve the instruction to return valid JSON.
4. If top-level JSON field names change, update the matching field reads in `app.py`.
5. Keep observed evidence separate from inference.
6. Keep URLs and screenshot-evidence requirements.
7. Restart Streamlit after changing Python code. Markdown prompt changes are read at analysis time, so a new analysis run is required.
8. Re-run each bank after prompt changes; old reports are not automatically regenerated.

## Project structure

```text
Prototype/
├── app.py                    # Streamlit entry point and pages
├── agent_backend.py          # LangGraph/LangChain agent and research tools
├── persistent_browser.py     # Dedicated-thread persistent Chrome controller
├── backend.py                # HTTP helpers, LLM client, SQLite and report storage
├── prompts/
│   ├── bank_analysis.md      # Individual bank analysis prompt
│   └── comparison.md         # Cross-bank comparison prompt
├── data/
│   ├── campaigns.db          # Generated local history; not shared
│   └── chrome-profile/       # Generated isolated Chrome state; not shared
├── screenshots/              # Generated visual evidence; ignored by Git
├── reports/                  # Generated JSON reports; ignored by Git
├── requirements.txt          # Python dependencies
├── .env.example              # Safe configuration template
├── .env                      # Local secret; excluded from ZIP/Git
├── setup_windows.bat         # One-time Windows installer
├── run_windows.bat           # Normal launcher
├── RUN_MANUALLY.txt          # Manual fallback commands
└── TROUBLESHOOTING.txt       # Common failures
```

## Security and sharing

`.env`, `.venv`, SQLite data, Chrome profile data, screenshots, generated reports, logs, and raw model output are ignored by Git and excluded from the teammate ZIP. Never commit or send a real API key. Teammates should create their own `.env` from `.env.example`.

Use only public, approved URLs. Review website terms, `robots.txt`, internal security requirements, and data-governance rules before production use.
