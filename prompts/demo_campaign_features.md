# Campaign communication coding framework — presentation scope

This file is read for every campaign-coding request. The 16 communication dimensions below supersede earlier non-comparable tone fields. They are positional scales, not quality scores.

## Required campaign fields

Preserve or derive concise English values for: Bank, Source URL, capture date, language, communication format, product family, target audience, campaign objective, offer/incentive, primary CTA, and campaign summary. Never translate or alter URLs.

## Standardized communication dimensions

For every dimension return three separate values: `score` (integer 1–5 or null), `justification` (one sentence), and `evidence_quote` (short supplied quotation). Never combine the number and prose.

1. **Formality** — 1 highly conversational/informal; 3 balanced professional/conversational; 5 highly formal/institutional.
2. **Humanity** — 1 strongly institutional/impersonal; 3 balanced; 5 strongly human/personal/relatable.
3. **Emotionality** — 1 almost entirely factual/rational; 3 balanced; 5 strongly emotional.
4. **Energy** — 1 very calm/restrained; 3 moderate; 5 highly energetic/vivid/intense.
5. **Confidence** — 1 cautious/qualified; 3 balanced; 5 highly assertive/confident.
6. **Accessibility** — 1 highly technical/difficult; 3 moderately accessible; 5 extremely simple/direct/accessible.
7. **Warmth** — 1 distant/impersonal; 3 moderately warm; 5 strongly warm/caring/supportive.
8. **Optimism** — 1 strongly problem/caution-focused; 3 balanced; 5 strongly aspirational/hopeful/future-oriented.
9. **Customer orientation** — 1 bank/institution/product-focused; 3 balanced; 5 strongly focused on customer needs/goals/experience.
10. **Persuasive intensity** — 1 primarily informational; 3 moderately persuasive; 5 highly persuasive/action-oriented.
11. **Urgency** — 1 no urgency; 3 moderate urgency; 5 strong/immediate pressure to act.
12. **Contemporary character** — 1 strongly traditional/conventional; 3 balanced; 5 strongly contemporary/unconventional/innovative.
13. **Premium character** — 1 mass-market/accessibility-oriented; 3 neutral; 5 strongly premium/exclusive/sophisticated.
14. **Playfulness** — 1 entirely serious; 3 occasional lightness; 5 strongly playful/humorous/witty.
15. **Directness** — 1 indirect/implicit/nuanced; 3 balanced; 5 extremely direct/concise/explicit.
16. **CTA intensity** — 1 no call to action; 2 passive invitation; 3 soft suggestion; 4 clear request; 5 strong/immediate instruction.

If evidence is insufficient, return JSON null as the score and explain the uncertainty. Apply exactly the same definitions to every campaign. Do not infer creators' intentions, effectiveness, bank-wide personality, or unsupported audiences.

## Visual assessment from screenshot evidence

Return concise English values for dominant colours, imagery subjects, layout, visual complexity, brand prominence, CTA visual prominence, mobile orientation, visible paragraph density, paragraph-size disparity, typography hierarchy, whitespace balance, scanability, and screenshot-based evidence. The screenshot is evidence, especially for visual-first pages. Do not treat white/black backgrounds as signature colours without stronger evidence.

## Deterministic metrics

The application calculates these in code and merges them into the record; do not estimate them: text characters, words, sentences, paragraphs, headings, image count, visible image count, buttons, links, page width/height, viewport dimensions, screenshot aspect ratio, mean brightness, contrast, warmth, colourfulness, and text/image proxy. These metrics use separate bar or box plots, not the 1–5 communication radar.


## Parallel quantitative HTML evidence

The application also supplies and stores `quantitative_html_metrics` from the team extractor: word, heading, paragraph, list, list-item, sentence, CTA, price, date, question, and link counts; average list-item, paragraph, and sentence lengths; primary heading; table presence; text-volume category; and paragraph-length category. Do not regenerate or overwrite those values. Screenshot judgments about visual paragraph disparity or apparent size remain separate because DOM structure and visible rendering can legitimately differ.
