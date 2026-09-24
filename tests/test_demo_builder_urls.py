"""Offline regression checks for draft URL routing and capture readiness."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import demo_backend as backend


BNP_URL = 'https://www.bnpparibasfortis.be/en/public/individuals/daily-banking/accounts/current-account-compare'
ING_URL = 'https://www.ing.be/en/individuals/campaign/current-account-free-youth'
OLD_ING = 'https://www.ing.be/nl/particulieren/campaign/existing'
OLD_BNP = 'https://www.bnpparibasfortis.be/en/public/existing'


class DemoBuilderURLTests(unittest.TestCase):
    def test_mixed_host_draft_routes_to_owners_and_deduplicates(self):
        draft = '\n'.join([OLD_ING, ING_URL, BNP_URL, ING_URL])
        grouped = backend.parse_demo_urls('ING', draft)
        self.assertEqual(grouped, {'ING': [OLD_ING, ING_URL], 'BNP Paribas Fortis': [BNP_URL]})

    def test_superseded_youth_urls_map_to_manual_target(self):
        from demo_manual_youth import OLD_URLS
        grouped = backend.parse_demo_urls('ING', '\n'.join((*OLD_URLS, ING_URL)))
        self.assertEqual(grouped, {'ING': [ING_URL]})

    def test_invalid_url_does_not_save_partial_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'urls.json'
            original = {'banks': {'ING': [OLD_ING], 'BNP Paribas Fortis': [OLD_BNP], 'N26': []}}
            backend._write_json(path, original)
            with patch.object(backend, 'URLS_PATH', path):
                with self.assertRaises(ValueError):
                    backend.save_demo_urls('ING', ING_URL + '\nhttps://example.com/wrong-host')
            self.assertEqual(json.loads(path.read_text(encoding='utf8')), original)

    def test_save_preserves_other_bank_and_routes_foreign_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'urls.json'
            backend._write_json(path, {'banks': {'ING': [OLD_ING], 'BNP Paribas Fortis': [OLD_BNP], 'N26': []}})
            with patch.object(backend, 'URLS_PATH', path):
                saved = backend.save_demo_urls('ING', '\n'.join([OLD_ING, ING_URL, BNP_URL, BNP_URL]))
                self.assertEqual(saved, [OLD_ING, ING_URL])
                data = backend.load_demo_urls()['banks']
            self.assertEqual(data['BNP Paribas Fortis'], [OLD_BNP, BNP_URL])
            self.assertEqual(data['ING'], [OLD_ING, ING_URL])

    def test_readiness_requires_both_files_and_no_error(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'page.txt').write_text('content', encoding='utf8')
            index = {ING_URL: {'text_file': 'page.txt'}}
            with patch.object(backend, 'capture_dir', return_value=folder), patch.object(backend, 'capture_index', return_value=index):
                self.assertEqual(backend.capture_status('ING', [ING_URL])['remaining'], 1)
                (folder / 'page.png').write_bytes(b'fake screenshot')
                index[ING_URL]['screenshot_file'] = 'page.png'
                self.assertEqual(backend.capture_status('ING', [ING_URL])['remaining'], 0)
                (folder / 'page.txt').write_text('', encoding='utf8')
                self.assertEqual(backend.capture_status('ING', [ING_URL])['remaining'], 1)
                (folder / 'page.txt').write_text('content', encoding='utf8')
                index[ING_URL]['capture_error'] = 'failed to refresh'
                self.assertEqual(backend.capture_status('ING', [ING_URL])['remaining'], 1)
                self.assertEqual(backend.all_demo_captures(['ING']), [])

    def test_complete_cached_capture_does_not_start_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'page.txt').write_text('content', encoding='utf8')
            (folder / 'page.png').write_bytes(b'fake screenshot')
            item = {'bank': 'ING', 'url': ING_URL, 'text_file': 'page.txt', 'screenshot_file': 'page.png'}
            with patch.object(backend, 'capture_dir', return_value=folder), \
                 patch.object(backend, 'capture_index', return_value={ING_URL: item}), \
                 patch.object(backend, 'PROGRESS_PATH', folder / 'progress.json'):
                # No Playwright/Camoufox installed in the test: returning here proves reuse.
                import asyncio
                result = asyncio.run(backend._capture_pages('ING', [ING_URL], visible=False))
            self.assertEqual((result['new'], result['reused'], result['failed']), (0, 1, 0))


if __name__ == '__main__':
    unittest.main()
