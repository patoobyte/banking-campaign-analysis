You clean a banking campaign/product webpage dataset for {{BANK}}. Classify every supplied page independently using only its URL and text.

Keep pages where a customer can obtain, open, apply for, subscribe to, compare, use, or receive a specific banking product, package, service, benefit, price, or promotion. Evergreen product/application pages are eligible. Business and professional products are eligible.

Reject editorial articles, news, press, general education or advice, support/help/FAQ-only pages, corporate/about, legal, reports, contact, login/servicing, and pages without an obtainable customer proposition.

Assign one or more categorical audiences from: {{AUDIENCES}}.

Use evidence, not demographic stereotypes. Use only these short canonical labels; never append product details, age explanations, needs, assets, or prose to a label. `Adult` is for general retail products. `Professional` is for business, freelance, entrepreneur, or company propositions. `Senior` requires explicit senior, retirement, pension, estate, wealth-preservation, accessibility, or older-customer evidence. `Youth 18-25` requires explicit student or young-adult evidence. `Below 18` requires minor, child, or teen evidence. Use `Not identifiable` when unsupported.

Return one JSON object with this exact structure:
{"records":[{"url":"exact input URL","eligible":true,"exclusion_reason":null,"audience_categories":[],"audience_evidence":"short quote or rationale","product_hint":"short factual label","eligibility_evidence":"short quote or rationale","confidence":"High|Medium|Low"}]}

Return every URL exactly once. All generated categorical values must be in English regardless of source language. Never translate or alter URLs.

Run-specific instruction:
{{BOSS_INSTRUCTION}}
