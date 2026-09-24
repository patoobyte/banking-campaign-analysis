"""Offline checks for screenshot-backed youth campaign import and AI evidence routing."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import demo_backend as backend
from demo_manual_youth import NEW_URL, OLD_URLS, import_youth_evidence

SOURCE = Path('Filteredurl/Blockedurl/Ing/Feee youth account')


class ManualYouthTests(unittest.TestCase):
    def test_migration_archives_old_records_and_leaves_new_campaign_uncoded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'captures' / 'ing'
            folder.mkdir(parents=True)
            urls_file, run_file = root / 'urls.json', root / 'runs' / 'demo-campaigns.json'
            originals = ['https://www.ing.be/en/other', OLD_URLS[0]]
            backend._write_json(urls_file, {'banks': {'ING': originals, 'BNP Paribas Fortis': [], 'N26': []}})
            backend._write_json(run_file, {'schema_version': 'demo-v1', 'records': [
                {'source_url': OLD_URLS[0], 'bank': 'ING', 'communication_scores': {'Formality': {'score': 3}}},
                {'source_url': OLD_URLS[1], 'bank': 'ING', 'error': 'old error'},
                {'source_url': 'https://www.ing.be/en/other', 'bank': 'ING', 'communication_scores': {'Formality': {'score': 2}}},
            ]})
            (folder / 'old.html').write_text('old html', encoding='utf8')
            backend._write_json(folder / 'index.json', {OLD_URLS[0]: {'html_file': 'old.html', 'text_file': 'old.html', 'screenshot_file': 'old.html'}, OLD_URLS[1]: {}})
            ocr = root / 'ocr.txt'
            ocr.write_text('Screenshot section 1: ING youth account. Section 2: Terms in screenshot.', encoding='utf8')
            with patch.object(backend, 'URLS_PATH', urls_file), patch.object(backend, 'RUN_PATH', run_file), patch.object(backend, 'capture_dir', return_value=folder):
                result = import_youth_evidence(SOURCE, ocr, backup_root=root / 'archive')
                self.assertEqual(backend.capture_status('ING', [NEW_URL])['remaining'], 0)
                ready = [r for r in backend.all_demo_captures(['ING']) if r['url'] == NEW_URL]
                self.assertEqual(len(ready), 1)
                self.assertEqual(len(ready[0]['screenshot_sections']), 6)
                self.assertEqual(ready[0]['text_source'], 'manual_screenshot_ocr')
            urls = json.loads(urls_file.read_text(encoding='utf8'))['banks']['ING']
            self.assertEqual(urls, ['https://www.ing.be/en/other', NEW_URL])
            run = json.loads(run_file.read_text(encoding='utf8'))['records']
            self.assertEqual(len(run), 1)
            self.assertEqual(run[0]['source_url'], 'https://www.ing.be/en/other')
            archive = Path(result['archived_at'])
            self.assertTrue((archive / 'old.html').exists())
            self.assertEqual(len(json.loads((archive / 'demo-campaigns.json').read_text(encoding='utf8'))['records']), 3)
            self.assertFalse((folder / 'old.html').exists())
            with patch.object(backend, 'URLS_PATH', urls_file), patch.object(backend, 'RUN_PATH', run_file), patch.object(backend, 'capture_dir', return_value=folder):
                with self.assertRaisesRegex(ValueError, 'already registered'):
                    import_youth_evidence(SOURCE, ocr, backup_root=root / 'another-archive')
            self.assertFalse((root / 'another-archive').exists())

    def test_ready_manual_campaign_is_reused_without_browser(self):
        import asyncio
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'text.txt').write_text('Reviewed screenshot text', encoding='utf8')
            (folder / 'preview.png').write_bytes(b'preview')
            sections = [f'{n}.png' for n in range(1, 7)]
            for section in sections:
                (folder / section).write_bytes(b'screenshot')
            index = {NEW_URL: {'text_file': 'text.txt', 'screenshot_file': 'preview.png',
                               'screenshot_sections': sections}}
            with patch.object(backend, 'capture_dir', return_value=folder), \
                 patch.object(backend, 'capture_index', return_value=index), \
                 patch.object(backend, 'PROGRESS_PATH', folder / 'progress.json'), \
                 patch('playwright.async_api.async_playwright', side_effect=AssertionError('Browser must not launch')):
                result = asyncio.run(backend._capture_pages('ING', [NEW_URL], visible=False))
                self.assertEqual(result['new'], 0)
                self.assertEqual(result['reused'], 1)
                (folder / sections[2]).unlink()
                with self.assertRaisesRegex(ValueError, 'Manual ING youth evidence is incomplete'):
                    asyncio.run(backend._capture_pages('ING', [NEW_URL], visible=False))

    def test_coding_request_has_six_ordered_images_and_ocr_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            images = []
            from PIL import Image
            for number in range(1, 7):
                name = f'{number}.png'
                Image.new('RGB', (600, 400), '#ff6600').save(folder / name)
                images.append(name)
            captured = {'bank': 'ING', 'url': NEW_URL, 'campaign_id': 'ING_current-account-free-youth',
                        'text': 'OCR TRANSCRIPTION of screenshots, NOT rendered HTML text.',
                        'text_source': 'manual_screenshot_ocr', 'screenshot_sections': images,
                        'screenshot_path': str(folder / images[0]), 'quantitative_html_metrics': {}}
            response = Mock()
            response.choices = [Mock(message=Mock(content='{}'))]
            fake_client = Mock()
            fake_client.chat.completions.create.return_value = response
            with patch.object(backend, 'capture_dir', return_value=folder), \
                 patch.object(backend, 'provider_settings', return_value={'model': 'offline-test'}), \
                 patch.object(backend, 'client', return_value=fake_client), \
                 patch.object(backend, '_wait_request_slot'), \
                 patch.object(backend, 'parse_json', return_value={}):
                backend._demo_ai_call(captured)
            parts = fake_client.chat.completions.create.call_args.kwargs['messages'][1]['content']
            image_parts = [item for item in parts if item['type'] == 'image_url']
            self.assertEqual(len(image_parts), 6)
            self.assertEqual([item['text'] for item in parts if item['type'] == 'text'][1:],
                             [f'Screenshot section {i}/6 (top to bottom)' for i in range(1, 7)])
            metadata = json.loads(parts[0]['text'])
            self.assertIn('NOT HTML-derived text', metadata['evidence_provenance'])
            self.assertEqual(metadata['metadata']['url'], NEW_URL)
            self.assertTrue(all(image['image_url']['url'].startswith('data:image/png;base64,') for image in image_parts))


if __name__ == '__main__':
    unittest.main()
