"""Offline, reversible import of user-supplied ING youth campaign screenshots.

Do not crawl the campaign: its live rendering is black on this machine. The saved
HTML is a JS shell; screenshot OCR is separately labelled as such, not HTML text.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

NEW_URL = 'https://www.ing.be/en/individuals/campaign/current-account-free-youth'
OLD_URLS = (
    'https://www.ing.be/en/individuals/current-accounts-packs/youth-account',
    'https://www.ing.be/nl/particulieren/campaign/zichtrekening-gratis-youth',
)


def import_youth_evidence(source: Path, ocr_file: Path, *, backup_root: Path | None = None):
    """Register supplied assets as a ready, uncoded capture; archive superseded data."""
    import demo_backend as db

    source = Path(source)
    ocr_file = Path(ocr_file)
    html_sources = list(source.glob('*.htm'))
    images = [source / f'{number}.png' for number in range(1, 7)]
    if len(html_sources) != 1 or not all(path.is_file() for path in images):
        raise ValueError('Expected exactly one saved .htm and screenshots 1.png through 6.png')
    if not ocr_file.is_file() or not ocr_file.read_text(encoding='utf8').strip():
        raise ValueError('OCR transcription is missing or empty')
    raw = html_sources[0].read_bytes()
    # The saved file declares UTF-8 but contains Windows-1252 euro bytes.
    html = raw.decode('windows-1252')
    soup = BeautifulSoup(html, 'html.parser')
    canonical = soup.find('link', rel='canonical')
    if not canonical or canonical.get('href') != NEW_URL:
        raise ValueError('Saved HTML canonical URL does not match the target campaign')
    for path in images:
        with Image.open(path) as image:
            image.verify()
    folder = db.capture_dir('ING')
    urls = db.load_demo_urls()
    index = db.capture_index('ING')
    run = db._read_json(db.RUN_PATH, {'schema_version': 'demo-v1', 'records': []})
    if NEW_URL in index and not any(url in index for url in OLD_URLS):
        raise ValueError('Manual evidence already registered; refusing to reset an existing campaign coding')
    if any(r.get('source_url') == NEW_URL and r.get('communication_scores') for r in run.get('records', [])):
        raise ValueError('New youth campaign already coded; restore missing evidence without replacing its run record')
    old_records = [r for r in run.get('records', []) if r.get('source_url') in (*OLD_URLS, NEW_URL)]
    if backup_root is None:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        backup_root = db.DEMO_ROOT / 'archives' / f'ing-youth-migration-{stamp}'
    backup_root = Path(backup_root)
    if backup_root.exists():
        raise FileExistsError(f'Archive destination exists: {backup_root}')
    backup_root.mkdir(parents=True)
    for original in (db.URLS_PATH, folder / 'index.json', db.RUN_PATH):
        if original.exists():
            shutil.copy2(original, backup_root / original.name)
    old_assets = []
    for url in (*OLD_URLS, NEW_URL):
        for field in ('html_file', 'text_file', 'screenshot_file'):
            filename = index.get(url, {}).get(field)
            if filename:
                asset = folder / filename
                if asset.is_file() and asset not in old_assets:
                    old_assets.append(asset)
                    shutil.copy2(asset, backup_root / asset.name)
    (backup_root / 'migration.json').write_text(json.dumps({
        'replaced_urls': list(OLD_URLS), 'target_url': NEW_URL,
        'previous_coded_records': len(old_records),
        'archived_assets': [p.name for p in old_assets],
        'source_html': str(html_sources[0]),
        'source_screenshots': [str(p) for p in images],
        'source_ocr': str(ocr_file),
    }, ensure_ascii=False, indent=2), encoding='utf8')

    prefix = hashlib.sha256(NEW_URL.encode('utf8')).hexdigest()
    html_name = prefix + '.html'
    text_name = prefix + '.txt'
    stitched_name = prefix + '.png'
    filenames = [prefix + f'-section-{number}.png' for number in range(1, 7)]
    # Preserve the six original captures independently; preview is for UI/metrics.
    for original, filename in zip(images, filenames):
        shutil.copy2(original, folder / filename)
    (folder / html_name).write_text(html, encoding='utf8')
    (folder / text_name).write_text(ocr_file.read_text(encoding='utf8'), encoding='utf8')
    width = 1500
    panels = []
    for path in images:
        with Image.open(path) as original:
            img = original.convert('RGB')
            img.thumbnail((width, 1400), Image.Resampling.LANCZOS)
            panels.append(img)
    gap = 36
    height = sum(panel.height + gap for panel in panels)
    preview = Image.new('RGB', (width, height), '#eeeeee')
    draw = ImageDraw.Draw(preview)
    y = 0
    for number, panel in enumerate(panels, 1):
        draw.text((16, y + 8), f'Section {number} / 6 (top to bottom)', fill='#111111')
        y += gap
        preview.paste(panel, ((width - panel.width) // 2, y))
        y += panel.height
    preview.save(folder / stitched_name, optimize=True)
    text = (folder / text_name).read_text(encoding='utf8')
    metrics = db._text_metrics(text)
    metrics.update(db._image_metrics(folder / stitched_name))
    metrics.update({
        'image_count': None, 'visible_image_count': None, 'heading_count': None,
        'paragraph_count': None, 'link_count': None, 'button_count': None,
        'text_image_ratio': None, 'page_width': None, 'page_height': None,
    })
    now = datetime.now(timezone.utc).isoformat()
    description = soup.find('meta', attrs={'name': 'description'})
    entry = {
        'bank': 'ING', 'url': NEW_URL, 'campaign_id': db.campaign_id('ING', NEW_URL),
        'title': soup.title.get_text(' ', strip=True) if soup.title else 'ING youth account',
        'status': None, 'capture_date': now, 'captured_at': now,
        'html_file': html_name, 'text_file': text_name, 'screenshot_file': stitched_name,
        'screenshot_sections': filenames,
        'evidence_source': 'user-supplied saved HTML and six ordered screenshots; offline OCR transcribed and manually reviewed',
        'text_source': 'manual_screenshot_ocr',
        'html_evidence_limit': 'Downloaded HTML is a JS shell, not a rendered campaign page.',
        'screenshot_order': 'sections 1 through 6, top to bottom',
        'html_description': description.get('content') if description else None,
        'metrics': metrics,
        'quantitative_html_metrics': db.extract_quantitative_html_metrics(html),
        'quantitative_extractor_version': db.EXTRACTOR_VERSION,
    }
    if not db._capture_complete(folder, entry):
        raise ValueError('Manual capture is not ready; previous index and run remain unchanged')
    ing_urls = urls['banks']['ING']
    ing_urls[:] = list(dict.fromkeys([NEW_URL if u in OLD_URLS else u for u in ing_urls] + [NEW_URL]))
    urls['updated_at'] = now
    for url in (*OLD_URLS, NEW_URL):
        index.pop(url, None)
    index[NEW_URL] = entry
    run['records'] = [r for r in run.get('records', []) if r.get('source_url') not in (*OLD_URLS, NEW_URL)]
    db._write_json(db.URLS_PATH, urls)
    db._write_json(folder / 'index.json', index)
    db._write_json(db.RUN_PATH, run)
    for asset in old_assets:
        if asset.name not in (html_name, text_name, stitched_name, *filenames):
            asset.unlink()
    return {'url': NEW_URL, 'archived_at': str(backup_root), 'archived_coded_records': len(old_records),
            'screenshot_files': filenames, 'ocr_characters': len(text)}


def restore_youth_evidence():
    """Restore ignored manual cache from versioned source assets, without touching coding."""
    import demo_backend as db
    source = db.ROOT / 'Filteredurl' / 'Blockedurl' / 'Ing' / 'Feee youth account'
    reviewed = db.ROOT / 'Filteredurl' / 'Blockedurl' / 'Ing' / 'youth-reviewed-transcript.txt'
    if not source.is_dir() or not reviewed.is_file():
        raise FileNotFoundError('Missing user screenshots/HTML or reviewed screenshot transcript; no live browser capture is allowed')
    return import_youth_evidence(source, reviewed)
