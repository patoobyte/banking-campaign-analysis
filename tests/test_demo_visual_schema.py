"""Offline regression coverage for visual categories and demo exports."""
import csv
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import demo_backend as backend

from demo_backend import COMMUNICATION_DIMENSIONS
from demo_ui import _campaign_csv, _campaign_export
from demo_visual_schema import VISUAL_SCHEMA_VERSION, PROFILE_TAGS, VISUAL_CATEGORIES, validate_demo_coding


class VisualSchemaTests(unittest.TestCase):
    def setUp(self):
        self.scores = {
            dimension: {'score': 3, 'justification': 'Page evidence', 'evidence_quote': 'Apply online'}
            for dimension in COMMUNICATION_DIMENSIONS
        }
        self.visual = {field: choices[0] for field, choices in VISUAL_CATEGORIES.items()}
        self.visual.update({field + '_evidence': 'Visible foreground/page detail.' for field in VISUAL_CATEGORIES})
        self.result = {
            'communication_scores': self.scores,
            'visual_assessment': self.visual,
            'dominant_characteristics': ['Formal', 'Direct', 'Confident'],
            'dominant_characteristics_evidence': {'Formal': 'Official language.', 'Direct': 'Direct CTA.', 'Confident': 'Assertive heading.'},
            'overall_communication_profile': 'Direct',
            'overall_communication_profile_evidence': 'Clear and explicit communication.',
            'evidence_quality': {'rating': 'High', 'explanation': 'Text and screenshot available.'},
        }

    def test_valid_categorical_response(self):
        self.assertFalse(validate_demo_coding(self.result))

    def test_rejects_prose_or_unexplained_labels(self):
        self.result['visual_assessment']['visual_complexity'] = 'Medium, because the page has cards'
        self.result['visual_assessment']['layout_evidence'] = ''
        self.result['overall_communication_profile'] = 'A direct and helpful profile.'
        errors = validate_demo_coding(self.result)
        self.assertTrue(any('visual_complexity' in error for error in errors))
        self.assertTrue(any('layout_evidence' in error for error in errors))
        self.assertTrue(any('overall_communication_profile:' in error for error in errors))

    def test_prompt_lists_category_vocabularies(self):
        prompt = Path('prompts/demo_campaign_features.md').read_text(encoding='utf8')
        for field, choices in VISUAL_CATEGORIES.items():
            line = next(line for line in prompt.splitlines() if line.startswith(f'- `{field}`:'))
            for choice in choices:
                self.assertIn(f'`{choice}`', line, (field, choice))
        for tag in PROFILE_TAGS:
            self.assertIn(f'`{tag}`', prompt)

    def test_recode_failure_preserves_old_result_and_is_retryable(self):
        old = {'bank': 'ING', 'source_url': 'https://example.test/ing', 'campaign_id': 'ing',
               'communication_scores': self.scores,
               'visual_assessment': {'visual_complexity': 'Medium because there are cards.'}}
        capture = {'bank': 'ING', 'url': old['source_url'], 'campaign_id': 'ing',
                   'screenshot_path': 'cached-ing.png', 'text': 'captured page'}
        with TemporaryDirectory() as directory:
            with patch.object(backend, 'RUN_PATH', Path(directory) / 'run.json'), \
                 patch.object(backend, 'all_demo_captures', return_value=[capture]), \
                 patch.object(backend, 'provider_preflight', return_value={'model': 'offline-test'}), \
                 patch.object(backend, 'configure_ai_pacing'), \
                 patch.object(backend, 'provider_settings', return_value={'model': 'offline-test'}):
                backend._write_json(backend.RUN_PATH, {'records': [old]})
                with patch.object(backend, '_demo_ai_call', side_effect=ValueError('ungraphable label')):
                    result = backend.run_demo_coding(['ING'], force_recode=True)
                self.assertEqual(len(result['records']), 1)
                self.assertEqual(result['records'][0]['visual_assessment'], old['visual_assessment'])
                self.assertIn('ungraphable label', result['records'][0]['recode_error'])
                self.assertEqual(result['failed'], 1)
                with patch.object(backend, '_demo_ai_call', return_value=self.result) as ai_call:
                    recovered = backend.run_demo_coding(['ING'], retry_errors=True)
                ai_call.assert_called_once()
                self.assertEqual(len(recovered['records']), 1)
                self.assertEqual(recovered['records'][0]['visual_assessment'], self.visual)
                self.assertEqual(recovered['records'][0]['visual_schema_version'], VISUAL_SCHEMA_VERSION)
                self.assertNotIn('recode_error', recovered['records'][0])
                self.assertEqual(recovered['failed'], 0)

    def test_csv_separates_labels_and_evidence_without_fabricating_old_labels(self):
        fresh = {'visual_schema_version': VISUAL_SCHEMA_VERSION, 'bank': 'ING', 'campaign_id': 'ing-new', 'source_url': 'https://example.test/new',
                 'communication_scores': self.scores, 'visual_assessment': self.visual,
                 'dominant_characteristics': self.result['dominant_characteristics'],
                 'dominant_characteristics_evidence': self.result['dominant_characteristics_evidence'],
                 'overall_communication_profile': 'Direct', 'overall_communication_profile_evidence': 'Explicit CTA.',
                 'evidence_quality': self.result['evidence_quality']}
        legacy = {'bank': 'ING', 'campaign_id': 'ing-old', 'source_url': 'https://example.test/old',
                  'communication_scores': self.scores,
                  'visual_assessment': {'dominant_colours': 'White page with orange ING buttons.', 'visual_complexity': 'High because there are many cards.'},
                  'dominant_characteristics': ['Well balanced and informative'],
                  'overall_communication_profile': 'Strong, carefully explained summary.',
                  'evidence_quality': self.result['evidence_quality']}
        other = dict(fresh, bank='N26', campaign_id='n26')
        chosen, exported_json = _campaign_export([fresh, legacy, other], 'ING', ['ING'])
        self.assertEqual(json.loads(exported_json)['records'], [fresh, legacy])
        _, text = _campaign_csv([fresh, legacy, other], 'ING', ['ING'])
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['visual_dominant_colours'], self.visual['dominant_colours'])
        self.assertEqual(rows[0]['visual_dominant_colours_evidence'], 'Visible foreground/page detail.')
        self.assertEqual(rows[0]['overall_communication_profile'], 'Direct')
        self.assertEqual(rows[0]['overall_communication_profile_evidence'], 'Explicit CTA.')
        self.assertEqual(rows[1]['visual_dominant_colours'], '')
        # Even a legacy one-word answer is not evidence of the new controlled rubric.
        legacy['visual_assessment']['scanability'] = 'Low'
        _, legacy_csv = _campaign_csv([legacy], 'ING', ['ING'])
        legacy_row = next(csv.DictReader(io.StringIO(legacy_csv)))
        self.assertEqual(legacy_row['visual_scanability'], '')
        self.assertEqual(legacy_row['visual_scanability_evidence'], 'Low')
        self.assertEqual(rows[1]['visual_dominant_colours_evidence'], 'White page with orange ING buttons.')
        self.assertEqual(rows[1]['visual_visual_complexity'], '')
        self.assertEqual(rows[1]['visual_visual_complexity_evidence'], 'High because there are many cards.')
        self.assertEqual(rows[1]['overall_communication_profile'], '')
        self.assertEqual(rows[1]['overall_communication_profile_evidence'], 'Strong, carefully explained summary.')
        self.assertEqual(rows[1]['dominant_characteristics'], '')
        self.assertIn('Well balanced and informative', rows[1]['dominant_characteristics_evidence'])


if __name__ == '__main__':
    unittest.main()
