"""Controlled visual and profile labels for the demo presentation dataset.

Older prose-only records are left untouched; a label is only graphable after recoding.
"""

VISUAL_SCHEMA_VERSION = 'demo-visual-categorical-v1'

VISUAL_CATEGORIES = {
    'dominant_colours': ('Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple', 'Pink', 'Teal', 'Brown', 'Gold', 'Black', 'Grey', 'White', 'Multicolour', 'None', 'Other'),
    'imagery_subjects': ('People', 'Devices', 'Products', 'Illustrations', 'Icons', 'Places', 'Abstract', 'None', 'Other'),
    'layout': ('Hero', 'Grid', 'Cards', 'Editorial', 'Minimal', 'Other'),
    'visual_complexity': ('Low', 'Medium', 'High'),
    'brand_prominence': ('Low', 'Medium', 'High'),
    'cta_visual_prominence': ('Low', 'Medium', 'High'),
    'mobile_orientation': ('Desktop', 'Responsive', 'Mobile', 'Unclear'),
    'visible_paragraph_density': ('Low', 'Medium', 'High'),
    'paragraph_size_disparity': ('Low', 'Medium', 'High'),
    'typography_hierarchy': ('Weak', 'Moderate', 'Strong'),
    'whitespace_balance': ('Sparse', 'Balanced', 'Dense'),
    'scanability': ('Low', 'Medium', 'High'),
}

PROFILE_TAGS = frozenset(
    'Formal Conversational Human Institutional Emotional Rational Energetic Calm '
    'Confident Cautious Accessible Technical Warm Distant Optimistic Pragmatic '
    'CustomerFocused ProductFocused Persuasive Informational Urgent Relaxed '
    'Contemporary Traditional Premium Mainstream Playful Serious Direct Indirect '
    'ActionOriented Passive'.split()
)


def valid_label(value, choices):
    return value if isinstance(value, str) and value in choices else None


def validate_demo_coding(result):
    """Reject ungraphable free-text categories and missing screenshot evidence."""
    errors = []
    visual = result.get('visual_assessment')
    if not isinstance(visual, dict):
        errors.append('visual_assessment is missing')
    else:
        for field, choices in VISUAL_CATEGORIES.items():
            value = visual.get(field)
            if value is not None and valid_label(value, choices) is None:
                errors.append(f'{field}: expected one of {", ".join(choices)} or null')
            evidence = visual.get(f'{field}_evidence')
            if not isinstance(evidence, str) or not evidence.strip():
                errors.append(f'{field}_evidence: missing screenshot observation')
    traits = result.get('dominant_characteristics')
    if not isinstance(traits, list) or not 3 <= len(traits) <= 5 or len(set(map(str, traits))) != len(traits):
        errors.append('dominant_characteristics: expected 3-5 distinct tags')
    elif any(valid_label(value, PROFILE_TAGS) is None for value in traits):
        errors.append('dominant_characteristics: invalid tag')
    trait_evidence = result.get('dominant_characteristics_evidence')
    if isinstance(traits, list) and not isinstance(trait_evidence, dict):
        errors.append('dominant_characteristics_evidence: missing tag evidence')
    elif isinstance(traits, list):
        for tag in traits:
            if not isinstance(tag, str) or not isinstance(trait_evidence.get(tag), str) or not trait_evidence[tag].strip():
                errors.append(f'dominant_characteristics_evidence: missing evidence for {tag}')
    profile = result.get('overall_communication_profile')
    if profile is not None and valid_label(profile, PROFILE_TAGS) is None:
        errors.append('overall_communication_profile: invalid tag')
    explanation = result.get('overall_communication_profile_evidence')
    if not isinstance(explanation, str) or not explanation.strip():
        errors.append('overall_communication_profile_evidence: missing synthesis')
    quality = result.get('evidence_quality')
    if not isinstance(quality, dict) or valid_label(quality.get('rating'), ('High', 'Medium', 'Low')) is None:
        errors.append('evidence_quality.rating: expected High, Medium, or Low')
    if not isinstance(quality, dict) or not isinstance(quality.get('explanation'), str) or not quality['explanation'].strip():
        errors.append('evidence_quality.explanation: missing explanation')
    return errors
