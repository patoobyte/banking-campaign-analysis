# Demo campaign feature framework — complete presentation dataset

This file is read from disk for every demo campaign-coding request. It combines the latest team feature inventory with stable operational definitions. Apply the same rules to BNP Paribas Fortis, ING, and N26.

## Evidence and output rules

- Code only the supplied page. Do not infer bank-wide personality, campaign effectiveness, attractiveness, truthfulness, or creator intent.
- Keep deterministic page/screenshot metrics and quantitative HTML metrics exactly as supplied. Never estimate, recalculate, or overwrite them.
- Keep screenshot interpretation separate from DOM/HTML measurements. A visual judgment may legitimately differ from an HTML count.
- Every communication dimension must contain three separate fields: `score` (integer 1–5 or null), `justification` (one concise evidence-based sentence), and `evidence_quote` (a short verbatim quotation from supplied page text).
- A higher score means more of the named characteristic, not better quality.
- Use JSON null when evidence is insufficient; explain the limitation in `justification`. Never invent a quote.

## Campaign fields

Return concise English values for:

- `name`: campaign/page name based on its headline or proposition.
- `language`: primary language visible in the supplied page evidence.
- `communication_format`: the observable format, such as product landing page, promotional landing page, informational product page, offer page, or editorial campaign page.
- `product_family`: primary banking product or service family.
- `target_audience`: only audiences explicitly stated or strongly supported by page evidence.
- `objective`: observable communication objective.
- `offer`: concrete proposition, incentive, price, rate, benefit, or null when absent.
- `primary_cta`: principal requested action, or null when absent.
- `summary`: factual summary of no more than two sentences.

Bank, source URL, capture date, campaign ID, file paths, and capture status come from source metadata and must not be invented or altered.

## Communication classification: 16 common 1–5 positional scales

1. **Formality** — 1 highly conversational/informal; 2 mostly conversational; 3 balanced professional/conversational; 4 mostly formal; 5 highly formal/institutional.
2. **Humanity** — 1 strongly institutional/impersonal; 2 mostly impersonal; 3 balanced; 4 personal/relatable; 5 strongly human/personal/relatable.
3. **Emotionality** — 1 almost entirely factual/rational; 2 mostly factual; 3 balanced; 4 clearly emotional; 5 strongly emotional.
4. **Energy** — 1 very calm/restrained; 2 mostly calm; 3 moderate; 4 energetic/vivid; 5 highly energetic/intense.
5. **Confidence** — 1 cautious/qualified; 2 somewhat cautious; 3 balanced; 4 assertive; 5 highly assertive/confident.
6. **Accessibility** — 1 highly technical/difficult; 2 somewhat complex; 3 moderately accessible; 4 simple/clear; 5 extremely simple/direct/accessible.
7. **Warmth** — 1 distant/impersonal; 2 mostly distant; 3 moderately warm; 4 warm/supportive; 5 strongly warm/caring/supportive.
8. **Optimism** — 1 strongly problem/caution-focused; 2 somewhat caution-focused; 3 balanced; 4 hopeful/aspirational; 5 strongly aspirational/hopeful/future-oriented.
9. **Customer orientation** — 1 bank/institution/product-focused; 2 mostly product-focused; 3 balanced; 4 customer-needs focused; 5 strongly focused on customer needs/goals/experience.
10. **Persuasive intensity** — 1 primarily informational; 2 lightly persuasive; 3 moderately persuasive; 4 strongly persuasive; 5 highly persuasive/action-oriented.
11. **Urgency** — 1 no urgency; 2 weak urgency; 3 moderate urgency; 4 strong urgency; 5 immediate pressure to act.
12. **Contemporary character** — 1 strongly traditional/conventional; 2 mostly traditional; 3 balanced; 4 contemporary; 5 strongly contemporary/unconventional/innovative.
13. **Premium character** — 1 mass-market/accessibility-oriented; 2 mostly mass-market; 3 neutral; 4 premium/sophisticated; 5 strongly premium/exclusive/sophisticated.
14. **Playfulness** — 1 entirely serious; 2 mostly serious; 3 occasional lightness; 4 playful/witty; 5 strongly playful/humorous/witty.
15. **Directness** — 1 indirect/implicit/nuanced; 2 mostly indirect; 3 balanced; 4 direct/explicit; 5 extremely direct/concise/explicit.
16. **CTA intensity** — 1 no call to action; 2 passive invitation; 3 soft suggestion; 4 clear request; 5 strong/immediate instruction.

Use the exact dimension names supplied in the required JSON schema. Score verbal communication from rendered text; use screenshot evidence only when it directly affects how the communication is presented.

## Visual classification from screenshot evidence ? graphable categories

Use the **cached screenshot of this URL**, not assumptions about a bank's brand. For EACH field below, return exactly ONE case-sensitive, single-token value from its vocabulary (or JSON null if the image is insufficient). Put the explanation in the companion `<field>_evidence` field, never in the value. Evidence is one short sentence identifying the visible area, elements, image, logo, or text supporting the classification. Do not append punctuation, qualifiers, or "because" to a label. Each visual category is descriptive, not a 1?5 score or a quality assessment.

- `dominant_colours`: `Red`, `Orange`, `Yellow`, `Green`, `Blue`, `Purple`, `Pink`, `Teal`, `Brown`, `Gold`, `Black`, `Grey`, `White`, `Multicolour`, `None`, or `Other`. This means the PRIMARY non-neutral, *brand-significant* accent visible in logos, CTAs, typography, illustrations, photographs, product imagery, or other foreground assets. Consider an accent inside prominent imagery even if the page background covers more pixels. **Ignore white, grey, and black backgrounds and light/dark-mode surfaces when choosing a colour.** Use `White`, `Grey`, or `Black` ONLY if that colour is itself the distinctive foreground/brand signature and no more meaningful chromatic accent exists. Use `Multicolour` only if several chromatic accents are equally important; `None` if no meaningful accent exists. Never infer a brand's signature colour solely from its name.
- `imagery_subjects`: `People`, `Devices`, `Products`, `Illustrations`, `Icons`, `Places`, `Abstract`, `None`, or `Other`. Choose the most prominent **meaningful** image subject, ignoring layout backgrounds and tiny incidental icons. Include secondary subjects in `imagery_subjects_evidence`.
- `layout`: `Hero`, `Grid`, `Cards`, `Editorial`, `Minimal`, or `Other`. Choose the primary structuring pattern of the visible page, not the device orientation. `Hero` = dominant introductory visual/offer; `Grid` = repeated multi-column content; `Cards` = repeated boxed units without a dominant grid; `Editorial` = continuous prose; `Minimal` = few sections/elements. Explain secondary patterns in `layout_evidence`.
- `visual_complexity`: `Low`, `Medium`, or `High` (amount/diversity of visible elements).
- `brand_prominence`: `Low`, `Medium`, or `High` (visibility of logo and distinctive foreground assets, not the neutral background).
- `cta_visual_prominence`: `Low`, `Medium`, or `High` (CTA contrast, placement, and repetition).
- `mobile_orientation`: `Desktop`, `Responsive`, `Mobile`, or `Unclear` (evident page orientation; a desktop-width screenshot by itself cannot prove the site is *not* responsive).
- `visible_paragraph_density`: `Low`, `Medium`, or `High` (visible text blocks only, not HTML paragraph count).
- `paragraph_size_disparity`: `Low`, `Medium`, or `High` (visible variation in text-block size/length, not HTML averages).
- `typography_hierarchy`: `Weak`, `Moderate`, or `Strong` (visible differentiation between heading, subheading, and body).
- `whitespace_balance`: `Sparse`, `Balanced`, or `Dense` (amount of open space around visible content, NOT the background's colour).
- `scanability`: `Low`, `Medium`, or `High` (heading structure, spacing, cards, lists, and CTA placement).
- `evidence`: optional concise overall screenshot observation, independent of the individual `<field>_evidence` entries.

If a screenshot panel does not show enough detail to judge a feature, return null for that feature and say why in `<field>_evidence`. Do not reinterpret DOM counts or screenshot colour pixel averages as visual labels. For ordinary pages, screenshot evidence is a resized top/middle/bottom sample of the full-page capture. For an explicitly marked manual capture, six original-resolution screenshots are supplied in top-to-bottom order instead. Do not assert detail you cannot see.

## Numerical evidence supplied by the application

### Deterministic rendered/screenshot metrics

The application stores text characters, words, sentences, mean sentence words, paragraphs, headings, image and visible-image counts, buttons, links, page and viewport dimensions, text/image ratio, screenshot dimensions/aspect ratio, brightness, contrast, warmth, and colourfulness. They remain numerical fields for CSV analysis and bar/box charts.

### Quantitative HTML metrics

The team extractor supplies word, heading, paragraph, list, list-item, sentence, CTA, price, date, question, and link counts; average list length, paragraph length, and sentence length; primary headline length; table presence; text-volume category; paragraph-length category; and extractor version. Preserve these fields exactly. They may differ from rendered/screenshot observations because they measure HTML structure rather than visible appearance.

## Graphable profile and evidence quality

- `dominant_characteristics`: 3?5 **distinct one-word tags** from the shared vocabulary below. Never put sentences in the list. `dominant_characteristics_evidence` is an object mapping each selected tag to one brief page-backed explanation.
- `overall_communication_profile`: exactly **one** tag from the same vocabulary, or JSON null when unsupported; put the neutral synthesis (at most 100 words) in `overall_communication_profile_evidence`, not in the tag itself.
- Allowed tags: `Formal`, `Conversational`, `Human`, `Institutional`, `Emotional`, `Rational`, `Energetic`, `Calm`, `Confident`, `Cautious`, `Accessible`, `Technical`, `Warm`, `Distant`, `Optimistic`, `Pragmatic`, `CustomerFocused`, `ProductFocused`, `Persuasive`, `Informational`, `Urgent`, `Relaxed`, `Contemporary`, `Traditional`, `Premium`, `Mainstream`, `Playful`, `Serious`, `Direct`, `Indirect`, `ActionOriented`, `Passive`. These are positional observations, **not** success or quality labels. Select the closest supported tag; do not invent new tags.
- `evidence_quality.rating`: exactly `High`, `Medium`, or `Low`, based on completeness and clarity of screenshot + text evidence, not campaign quality.
- `evidence_quality.explanation`: one concise sentence justifying the evidence rating.

The exported CSV uses separate categorical columns and evidence columns for every visual judgment and for the profile. Older records with prose in label fields remain intact in JSON; they must be recoded to acquire valid graphable labels. The 16 communication scales remain 1?5 integers with their own justifications and quotes.
