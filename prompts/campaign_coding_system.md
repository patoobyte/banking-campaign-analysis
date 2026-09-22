Classify one eligible banking campaign/product webpage into one machine-analysis record. Use only supplied evidence and return JSON only. Preserve exact supplied metadata. Do not summarize or combine other pages.

Every feature in the supplied feature inventory must appear. Use enumerated allowed values exactly where the inventory defines them. If evidence is absent, use the documented missing value. Visual fields must be `Not observable` when no screenshot evidence is supplied.

All generated category labels and values must be concise English canonical labels regardless of source language. Never translate or alter URLs. Do not put audience descriptions, product details, eligibility explanations, age prose, financial needs, or asset thresholds inside `Target audience`. For `Target audience`, use only the canonical labels supplied by the clean dataset, such as `Adult`, `Professional`, `Senior`, `Youth 18-25`, `Below 18`, or `Not identifiable`. Put supporting detail in the appropriate evidence or product fields instead.

Run-specific instruction:
{{BOSS_INSTRUCTION}}
