You code one curated bank campaign webpage for a presentation dataset. The page is already eligible. Evaluate only supplied rendered text, deterministic metrics, quantitative HTML metrics, metadata, and screenshot evidence. The screenshot is a primary source, especially for visual-first pages such as N26.

Apply the same definitions to every bank. Never evaluate quality, effectiveness, attractiveness, truthfulness, or personal preference. Do not compare this page with other campaigns. If evidence is insufficient, use null for a numeric score and explain why.

The supplied `quantitative_html_metrics` are deterministic measurements produced by the team's HTML extractor. Preserve them conceptually but do not recalculate, override, or treat them as visual judgments. Judge paragraph-size disparity, visible paragraph density, typography hierarchy, whitespace balance, and scanability from the screenshot separately. It is acceptable for deterministic HTML structure and screenshot-based appearance to differ; explain such differences rather than forcing agreement.

Return one JSON object with exactly these top-level keys:
- `campaign`: concise factual English fields: `name`, `product_family`, `target_audience`, `objective`, `offer`, `primary_cta`, `summary`.
- `communication_scores`: every required dimension as an object containing `score`, `justification`, and `evidence_quote`.
- `visual_assessment`: `dominant_colours`, `imagery_subjects`, `layout`, `visual_complexity`, `brand_prominence`, `cta_visual_prominence`, `mobile_orientation`, `visible_paragraph_density`, `paragraph_size_disparity`, `typography_hierarchy`, `whitespace_balance`, `scanability`, and `evidence`.
- `overall_communication_profile`: no more than 100 words.
- `dominant_characteristics`: 3 to 5 concise items.
- `evidence_quality`: object with `rating` (`High`, `Medium`, or `Low`) and `explanation`.

For every communication dimension, `score` must be either a JSON integer from 1 to 5 or JSON null. Never put prose inside `score`; prose belongs in `justification`, and a short quotation belongs in `evidence_quote`. Return all required dimensions exactly once. Never alter the supplied source URL.

Run-specific instruction:
{{BOSS_INSTRUCTION}}
