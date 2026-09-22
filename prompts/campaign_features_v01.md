# Campaign feature list - v01 - Team Anna, Imad & Soo 

This inventory follows the codebook v01. 
It lists leaf-level fields only; grouping headings such as **Tone**, **Message framing**, and **Visual communication** are not counted as separate features.

## Part 1 — Simple feature list

### Metadata (that part is factual code like thought stuff like target audiance would need AI as some of it is AI if the AI is able to identify one)

- Bank
- Source URL
- Capture date
- Language
- Channel
- Communication format
- Timing
- Product family
- Target audience ( It should be one if not unknow)
- Campaign objective
- Incentive type
- Incentive value
- Validity period
- Associated season/event (It can be interessing or nothing, like school start and bank making promotion for it but it can also be nothing)
- Viewport dimensions
- Signature color

### Communication (that part is AI as we will compare commmunication to see what it can catch)

- Formality
- Warmth
- Humor
- Emotional valence
- Grammatical person
- Dominant appeal
- Benefit focus
- Concrete support
- Core message specificity
- Word count
- Heading count
- Paragraph count
- List count
- List item count
- Average list length
- Sentence count
- Average paragraph length
- Average sentence length
- Primary headline length
- Text volume *(optional derived category)*
- Paragraph length category *(optional derived category)*
- Readability
- Financial jargon
- Sentence style
- Imperatives
- Questions
- Metaphors (figurative language)
- Emojis
- CTA action level
- Urgency
- Scarcity
- Trust *(derived feature)*
- Personalization
- Trust-building approach
- Storytelling
- Human imagery
- Product imagery
- Imagery style
- Visual text density
- Content section count
- Text-image layout patterns
- Visual complexity
- Brand prominence
- Colour palette relationship
- Offer prominence
- CTA visual prominence

## Part 2 — Feature definitions, selection types, and allowed values

### Metadata

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| Bank | Bank associated with the campaign. | Supplied metadata; exact reproduction | Project's internal bank classification; examples: `ING`, `BNP Paribas Fortis`, `Belfius`, `KBC`. No missing value. |
| Source URL | Exact webpage URL from which the screenshot was captured. | Supplied metadata; URL string | Exact captured URL. Do not reconstruct, shorten, or guess it. |
| Capture date | Date on which the communication was observed. | Supplied metadata; date | `YYYY-MM-DD`. No missing value. |
| Language | Language used in the captured communication. | Supplied metadata; single value | Suggested values: `English`, `French`, `Dutch`, `German`. No missing value. |
| Channel | Platform or environment in which the communication appeared. | Supplied metadata; single value | Current project: `Website` only. No missing value. |
| Communication format | Dominant role performed by the captured page. | Model-classified; single select | `Homepage`, `Product page`, `Promotional page`, `Other`, `Not observable`. |
| Timing | Strongest explicit temporal context of the campaign. | Model-classified; single select | `Event-based`, `Seasonal`, `Other limited-time promotion`, `Evergreen`, `Not observable`. |
| Product family | Main financial product promoted by the campaign. | Model-classified; single select | `Current`, `Pack`, `Card`, `Savings`, `Pension`, `Insurance`, `Loan`, `Other`, `Not observable`. |
| Target audience | Evidence-based description of the person or group expected to respond. | Model-generated; free text | Short audience description; optionally distinguish primary and supported secondary audiences. Missing value: `Not identifiable`. |
| Campaign objective | Main behavioral or communication goal, primarily based on the dominant CTA and proposition. | Model-classified; single select | `Acquisition`, `Upselling`, `Product usage`, `Retention`, `Awareness`, `Other`, `Not observable`. |
| Incentive type | Additional promotional reason to act beyond normal permanent product features. | Model-classified; multi-select | `Cash`, `Discount`, `Waived fee`, `Gift`, `Competition`, `Enhanced feature`, `None`, `Other`, `Not observable`. `None` and `Not observable` cannot be combined with another value. |
| Incentive value | Exact visible monetary or material value attached to each incentive. | Model-extracted; one value per selected incentive type | Exact amount and currency, percentage, fee reduction, duration, stated retail value, or non-monetary benefit. Missing values: `Not found`, `Not applicable`, `Not observable`. |
| Validity period | Exact period during which the campaign can be acted on or its incentive applies. | Model-extracted; one or more labelled dates or durations | Preserve visible date, deadline, event period, or duration wording; use `YYYY-MM-DD` only when the full date is visible. Missing values: `Not found`, `Not applicable`, `Not observable`. |
| Associated season/event | Explicit cultural, commercial, academic, or institutional context. | Model-classified and extracted; one normalized category plus visible wording | Possible normalized categories: `Christmas`, `New Year`, `Valentine's Day`, `Easter`, `Summer`, `Halloween`, `Back to school/rentrée`, `Black Friday`, `Holiday travel`, `Named university event`, `Named sporting event`, `Named music festival`, `Bank anniversary`, `Other`, `None`, `Not observable`. The normalized list is extensible when no existing category fits. |
| Viewport dimensions | Browser viewport used for the capture, before scrolling. | Supplied technical metadata; dimensions | `width × height` in pixels, for example `1440 × 900`. No missing value. |
| Signature color | Bank's supplied signature colour, used for palette comparison. | Supplied metadata; colour value | Exact supplied colour value. No missing value. |

### Communication

#### Tone

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| Formality | Degree to which the wording is conversational or institutionally formal. | Model-classified; single select | `Informal`, `Balanced`, `Formal`, `Not observable`. |
| Warmth | Degree of friendliness, empathy, and human closeness in the message. | Model-classified; single select | `Low`, `Medium`, `High`, `Not observable`. |
| Humor | Presence and prominence of jokes, playfulness, or comic wording. | Model-classified; single select | `Absent`, `Subtle`, `Prominent`, `Not observable`. |
| Emotional valence | Overall emotional direction of the campaign message. | Model-classified; single select | `Negative`, `Neutral`, `Positive`, `Mixed`, `Not observable`. |

#### Grammatical person

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| Grammatical person | Dominant grammatical perspective used in the campaign copy. | Model-classified; single select | `First person`, `Second person`, `Third person`, `Mixed`, `Impersonal`, `Not observable`. |

#### Message framing

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| Dominant appeal | Whether the proposition primarily relies on practical reasons, feelings, or both. | Model-classified; single select | `Functional`, `Emotional`, `Mixed`, `Not observable`. |
| Benefit focus | Main beneficiary or focus of the explicit benefits. | Model-classified; single select | `Product`, `Customer`, `Societal`, `Mixed`, `No explicit benefit`, `Not observable`. |
| Concrete support | Amount of specific proof or factual detail supporting the proposition. | Model-classified; single select | `None`, `Limited`, `Substantial`, `Not observable`. |
| Core message specificity | Precision with which the central proposition identifies the product, audience, benefit, conditions, or action. | Model-classified; single select | `Generic`, `Moderately specific`, `Highly specific`, `Not observable`. |

#### Quantitative text metrics

All quantitative text metrics use cleaned, visible **full-page campaign content** and consistently exclude navigation, cookie banners, footers, standard legal disclosures, hidden text, and duplicate sticky content.

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| Word count | Total words in retained campaign content. | Automatically calculated | Non-negative integer. |
| Heading count | Valid campaign or product headings. | Automatically calculated | Non-negative integer. |
| Paragraph count | Retained normalized paragraph blocks. | Automatically calculated | Non-negative integer. |
| List count | Distinct retained bulleted, numbered, checklist, or semantic lists. | Automatically calculated | Non-negative integer. |
| List item count | Total individual items across retained lists. | Automatically calculated | Non-negative integer. |
| Average list length | Mean number of items per retained list. | Automatically calculated | Numeric value, rounded consistently; `Not applicable` when no lists are identified. |
| Sentence count | Sentences in retained paragraphs and bullet items. | Automatically calculated | Non-negative integer. |
| Average paragraph length | Mean words per retained paragraph, excluding bullets and headings. | Automatically calculated | Numeric value, rounded consistently; `Not applicable` when no paragraphs are retained. |
| Average sentence length | Mean words per retained sentence. | Automatically calculated | Numeric value, rounded consistently; `Not applicable` when no complete sentences are identified. |
| Primary headline length | Words in the cleaned main campaign heading. | Automatically calculated | Non-negative integer; `Not found` when no primary campaign heading is identified. |
| Text volume *(optional)* | Ordinal category derived from total word count. | Automatically derived; single value | `1` = 0–150, `2` = 151–300, `3` = 301–600, `4` = 601–1,000, `5` = more than 1,000 words. Thresholds are provisional. |
| Paragraph length category *(optional)* | Category derived from average paragraph length. | Automatically derived; single select | `Concise` (≤15 words), `Balanced` (16–35), `Detailed` (>35), `Not applicable` (no paragraphs). |

The quantitative feature family also permits `Extraction failed` when calculation cannot be completed.

#### Language

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| Readability | Overall ease or difficulty of reading the campaign copy. | Model-classified; single select | `Simple`, `Moderate`, `Complex`, `Not observable`. |
| Financial jargon | Extent of specialized financial terminology. | Model-classified; single select | `None`, `Limited`, `Extensive`, `Not observable`. |
| Sentence style | General compactness or density of sentence construction. | Model-classified; single select | `Concise`, `Balanced`, `Dense`, `Not observable`. |
| Imperatives | Whether the campaign uses command or action-oriented verb forms. | Model-classified; single select | `Present`, `Absent`, `Not observable`. |
| Questions | Whether questions appear in the analyzed campaign copy. | Model-classified; single select | `Present`, `Absent`, `Not observable`. |
| Metaphors (figurative language) | Whether figurative or metaphorical wording appears. | Model-classified; single select | `Present`, `Absent`, `Not observable`. |
| Emojis | Whether emoji characters appear in the analyzed content. | Model-classified; single select | `Present`, `Absent`, `Not observable`. |

#### Persuasion

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| CTA action level | Degree of commitment requested by the primary campaign CTA. | Model-classified; single select | `Informational`, `Exploratory`, `Transactional`, `Transactional with incentive`, `No CTA`, `Not observable`. |
| Urgency | Strength of time pressure or encouragement to act promptly. | Model-classified; single select | `Absent`, `Moderate`, `Strong`, `Not observable`. |
| Scarcity | Whether limited availability, quantity, or access is communicated. | Model-classified; single select | `Absent`, `Present`, `Not observable`. |
| Trust | Whether any explicit trust-building approach is present. | Derived; single select | `Present` when one or more trust-building approaches are selected; `Absent` for `None observed`; otherwise `Not observable`. |
| Personalization | Degree to which the message is adapted to a broad audience, segment, or individual. | Model-classified; single select | `Generic`, `Audience-specific`, `Individualized`, `Not observable`. |
| Trust-building approach | Explicit mechanism used to create confidence in the proposition. | Model-classified; multi-select | `Security and control`, `Expertise`, `Institutional credibility`, `Guarantees and reassurance`, `Customer evidence`, `None observed`, `Not observable`. `None observed` and `Not observable` cannot be combined with another value. |

#### Storytelling

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| Storytelling | Degree to which the campaign uses a narrative, character, sequence, or situation rather than only presenting information. | Model-classified; single select | `Absent`, `Light`, `Strong`, `Not observable`. |

#### Visual communication

| Feature | Short description | Selection or output type | Allowed values / format |
|---|---|---|---|
| Human imagery | Presence and grouping of people in meaningful campaign imagery. | Model-classified; single select | `Absent`, `Individual`, `Group`, `Mixed`, `Not observable`. |
| Product imagery | Presence and form of the promoted product in campaign imagery. | Model-classified; single select | `Absent`, `Physical product`, `Digital interface`, `Mixed`, `Not observable`. |
| Imagery style | Dominant role or style of meaningful campaign imagery. | Model-classified; single select | `Functional`, `Lifestyle`, `Symbolic/abstract`, `Mixed`, `No imagery`, `Not observable`. |
| Visual text density | How text-heavy the page appears visually. | Model-classified; single select | `Low`, `Medium`, `High`, `Not observable`. |
| Content section count | Number of top-level visual sections organizing the campaign page. | Model-extracted visual metric | Non-negative integer; `Not observable` when the complete layout cannot be assessed. |
| Text-image layout patterns | Substantial arrangements used to combine text and imagery. | Model-classified; multi-select | `Side-by-side`, `Alternating`, `Stacked`, `Grid/cards`, `Text overlay`, `Full-width visual`, `No imagery`, `Other`, `Not observable`. `No imagery` and `Not observable` cannot be combined with another value. |
| Visual complexity | Competition among visual elements and clarity of the page hierarchy. | Model-classified; single select | `Low`, `Medium`, `High`, `Not observable`. |
| Brand prominence | Visual centrality of explicit bank identity, excluding colour as evidence. | Model-classified; single select | `Low`, `Medium`, `High`, `Not observable`. |
| Colour palette relationship | Relationship between deliberate campaign colours and the supplied bank signature colour. | Model-classified; single select | `Signature-led`, `Signature-supported`, `Alternative-led`, `Neutral-led`, `Multicolour`, `Not observable`. |
| Offer prominence | Visual importance of the main product or temporary promotion. | Model-classified; single select | `Absent`, `Low`, `Medium`, `High`, `Not observable`. |
| CTA visual prominence | How strongly the primary campaign CTA stands out through size, contrast, placement, repetition, or persistence. | Model-classified; single select | `No CTA`, `Low`, `Medium`, `High`, `Not observable`. |
