from __future__ import annotations
import asyncio, base64, hashlib, io, json, math, os, re, statistics, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import matplotlib.pyplot as plt
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image, ImageStat
from config import ROOT, DATA, PROMPTS, slug
from ai import client, provider_settings, provider_preflight, configure_ai_pacing, _wait_request_slot, parse_json, read_prompt
from quantitative_html_metrics import extract_quantitative_html_metrics, EXTRACTOR_VERSION
from demo_visual_schema import VISUAL_SCHEMA_VERSION, validate_demo_coding

DEMO_ROOT=DATA/'demo'; DEMO_CAPTURES=DEMO_ROOT/'captures'; DEMO_RUNS=DEMO_ROOT/'runs'; DEMO_GRAPHS=DEMO_ROOT/'graphs'
for folder in (DEMO_ROOT,DEMO_CAPTURES,DEMO_RUNS,DEMO_GRAPHS): folder.mkdir(parents=True,exist_ok=True)
URLS_PATH=DEMO_ROOT/'urls.json'; PROGRESS_PATH=DEMO_ROOT/'capture-progress.json'; RUN_PATH=DEMO_RUNS/'demo-campaigns.json'
DEMO_BANKS={
    'BNP Paribas Fortis':{'code':'BNP','host':'www.bnpparibasfortis.be','source':ROOT/'Filteredurl'/'BaripasfortisCampainurl.txt'},
    'ING':{'code':'ING','host':'www.ing.be','source':ROOT/'Filteredurl'/'INGcampainurl.txt'},
    'N26':{'code':'N26','host':'n26.com','source':ROOT/'Filteredurl'/'Onlinebank'/'N26'/'n26url(probablywillneedscreenshot).txt'},
}
COMMUNICATION_DIMENSIONS=['Formality','Humanity','Emotionality','Energy','Confidence','Accessibility','Warmth','Optimism','Customer orientation','Persuasive intensity','Urgency','Contemporary character','Premium character','Playfulness','Directness','CTA intensity']
METRIC_LABELS={'text_characters':'Text characters','word_count':'Words','sentence_count':'Sentences','paragraph_count':'Paragraphs','heading_count':'Headings','image_count':'Images','visible_image_count':'Visible images','button_count':'Buttons','link_count':'Links','mean_sentence_words':'Mean sentence words','text_image_ratio':'Words per visible image','screenshot_brightness':'Brightness (0-255)','screenshot_contrast':'Contrast','screenshot_warmth':'Warmth','screenshot_colourfulness':'Colourfulness'}
QUANTITATIVE_METRIC_LABELS={'word_count':'HTML words (team extractor)','heading_count':'HTML headings (team extractor)','paragraph_count':'HTML paragraphs (team extractor)','list_count':'HTML lists','list_item_count':'HTML list items','average_list_length':'Average list items per list','sentence_count':'HTML sentences (team extractor)','average_paragraph_length':'Average paragraph words','average_sentence_length':'Average sentence words','primary_headline_length':'Primary headline words','cta_count':'CTA mentions','price_mention_count':'Price mentions','date_mention_count':'Date mentions','question_count':'Questions','link_count':'HTML links','text_volume':'Text-volume category (1-5)'}
_CAPTURE_LOCK=threading.Lock(); _CAPTURE_CANCEL=threading.Event()

_JSON_WRITE_LOCKS_GUARD=threading.Lock()
_JSON_WRITE_LOCKS={}
def _json_write_lock(path: Path):
    key=str(path.resolve()).lower()
    with _JSON_WRITE_LOCKS_GUARD:
        return _JSON_WRITE_LOCKS.setdefault(key,threading.Lock())

def _write_json(path: Path,data):
    """Atomically write JSON on Windows despite readers, antivirus, or parallel callbacks."""
    path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(data,ensure_ascii=False,indent=2)
    lock=_json_write_lock(path)
    with lock:
        temporary=path.with_name(f'{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp')
        temporary.write_text(payload,encoding='utf8')
        try:
            for attempt in range(15):
                try:
                    os.replace(temporary,path)
                    return
                except PermissionError:
                    if attempt==14: raise
                    time.sleep(0.10*(attempt+1))
        finally:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass

def _read_json(path: Path,default):
    try: return json.loads(path.read_text(encoding='utf8'))
    except (OSError,json.JSONDecodeError): return default

def _normalise_url(value):
    value=value.strip(); repaired=False
    if value.lower().startswith('nttps://'): value='https://'+value[8:]; repaired=True
    return value.rstrip('/')+'/' if urlparse(value).path in ('','/') else value.rstrip('/'),repaired

def _valid_for_bank(bank,url):
    parsed=urlparse(url); expected=DEMO_BANKS[bank]['host']
    return parsed.scheme in ('http','https') and parsed.netloc.lower().removeprefix('www.')==expected.removeprefix('www.')

def _seed_urls():
    banks={}; warnings=[]
    for bank,config in DEMO_BANKS.items():
        lines=[]
        if config['source'].exists(): lines=[x.strip() for x in config['source'].read_text(encoding='utf-8-sig').splitlines() if x.strip()]
        urls=[]
        for raw in lines:
            url,repaired=_normalise_url(raw)
            if repaired: warnings.append(f'Repaired `{raw}` to `{url}` while importing {bank}.')
            if _valid_for_bank(bank,url) and url not in urls: urls.append(url)
            elif not _valid_for_bank(bank,url): warnings.append(f'Ignored invalid or wrong-host URL for {bank}: `{raw}`')
        banks[bank]=urls
    data={'updated_at':datetime.now(timezone.utc).isoformat(),'banks':banks,'import_warnings':warnings}; _write_json(URLS_PATH,data); return data

def load_demo_urls():
    data=_read_json(URLS_PATH,None) or _seed_urls()
    for bank in DEMO_BANKS: data.setdefault('banks',{}).setdefault(bank,[])
    return data

def parse_demo_urls(bank,text):
    """Preview a draft URL list; route known bank hosts without silently dropping them."""
    if bank not in DEMO_BANKS: raise ValueError(f'Unknown demo bank: {bank}')
    grouped={bank:[]}; invalid=[]
    for raw in text.splitlines():
        if not raw.strip(): continue
        url,_=_normalise_url(raw)
        from demo_manual_youth import NEW_URL as YOUTH_URL, OLD_URLS as YOUTH_ALIASES
        if url in YOUTH_ALIASES: url=YOUTH_URL
        owner=next((candidate for candidate in DEMO_BANKS if _valid_for_bank(candidate,url)),None)
        if owner is None: invalid.append(raw.strip())
        elif url not in grouped.setdefault(owner,[]): grouped[owner].append(url)
    if invalid: raise ValueError('Unsupported or invalid URL(s): '+', '.join(invalid))
    return grouped


def save_demo_urls(bank,text):
    grouped=parse_demo_urls(bank,text)
    data=load_demo_urls()
    # This bank's editor replaces its own list. Other banks receive additive URLs only.
    data['banks'][bank]=grouped[bank]
    for other,urls in grouped.items():
        if other!=bank: data['banks'][other]=list(dict.fromkeys(data['banks'][other]+urls))
    data['updated_at']=datetime.now(timezone.utc).isoformat()
    _write_json(URLS_PATH,data)
    return data['banks'][bank]

def campaign_id(bank,url):
    path=urlparse(url).path.strip('/'); name=(path.split('/')[-1] if path else 'home') or 'home'
    name=re.sub(r'[^a-zA-Z0-9]+','-',name).strip('-').lower() or 'home'
    return f"{DEMO_BANKS[bank]['code']}_{name}"

def capture_dir(bank):
    path=DEMO_CAPTURES/slug(bank); path.mkdir(parents=True,exist_ok=True); return path

def capture_index(bank): return _read_json(capture_dir(bank)/'index.json',{})

def _text_metrics(text):
    words=re.findall(r"\b[\w’'-]+\b",text,flags=re.UNICODE); sentences=[x for x in re.split(r'(?<=[.!?])\s+',text) if x.strip()]
    return {'text_characters':len(text),'word_count':len(words),'sentence_count':len(sentences),'mean_sentence_words':round(len(words)/max(1,len(sentences)),2)}

def _image_metrics(path):
    with Image.open(path) as source:
        image=source.convert('RGB'); width,height=image.size; thumb=image.copy(); thumb.thumbnail((900,2500)); stat=ImageStat.Stat(thumb)
        means=stat.mean; std=stat.stddev; pixels=np.asarray(thumb,dtype=np.float32); rg=np.abs(pixels[:,:,0]-pixels[:,:,1]); yb=np.abs(0.5*(pixels[:,:,0]+pixels[:,:,1])-pixels[:,:,2])
        colourfulness=float(math.sqrt(float(rg.std())**2+float(yb.std())**2)+0.3*math.sqrt(float(rg.mean())**2+float(yb.mean())**2))
        return {'screenshot_width':width,'screenshot_height':height,'screenshot_aspect_ratio':round(width/max(1,height),4),'screenshot_brightness':round(sum(means)/3,2),'screenshot_contrast':round(sum(std)/3,2),'screenshot_warmth':round(means[0]-means[2],2),'screenshot_colourfulness':round(colourfulness,2)}

def _visual_evidence_data_url(path):
    with Image.open(path) as source:
        image=source.convert('RGB'); width,height=image.size; slice_height=min(height,max(700,int(width*0.75))); starts=sorted(set([0,max(0,(height-slice_height)//2),max(0,height-slice_height)])); panels=[]
        for start in starts:
            panel=image.crop((0,start,width,min(height,start+slice_height))); panel.thumbnail((700,700)); panels.append(panel)
        canvas=Image.new('RGB',(sum(x.width for x in panels),max(x.height for x in panels)),(240,240,240)); x=0
        for panel in panels: canvas.paste(panel,(x,0)); x+=panel.width
        output=io.BytesIO(); canvas.save(output,format='JPEG',quality=78,optimize=True)
    return 'data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode('ascii')

def _manual_image_data_url(path):
    # Keep all six sections at their original resolution; small text in resized
    # panels can obscure offer dates and conditions.
    return 'data:image/png;base64,'+base64.b64encode(Path(path).read_bytes()).decode('ascii')

def is_demo_capture_running(): return _CAPTURE_LOCK.locked()
def stop_demo_capture(): _CAPTURE_CANCEL.set(); return is_demo_capture_running()

async def _capture_pages(bank,urls,visible=True,progress=None):
    folder=capture_dir(bank); index=capture_index(bank)
    from demo_manual_youth import NEW_URL as MANUAL_YOUTH_URL, OLD_URLS as YOUTH_ALIASES, restore_youth_evidence
    if bank=='ING' and any(url in YOUTH_ALIASES for url in urls):
        raise ValueError('Superseded ING youth URL. Use the manually captured English youth campaign URL instead.')
    if bank=='ING' and MANUAL_YOUTH_URL in urls and MANUAL_YOUTH_URL not in index:
        # Fresh checkout: cached data/ is ignored, but the six user assets and
        # reviewed transcript are versioned. Never visit the black live page.
        restore_youth_evidence()
        index=capture_index(bank)
    pending=[url for url in urls if not _capture_complete(folder,index.get(url,{}))]
    # The manually supplied youth campaign cannot be rendered by the browser on this machine.
    # If an asset is lost, report the missing manual evidence rather than caching a black page.
    if bank=='ING' and MANUAL_YOUTH_URL in pending:
        raise ValueError('Manual ING youth evidence is incomplete. Restore its screenshot/OCR files from data/demo/archives; do not recapture the black live page.')
    total=len(urls); reused=total-len(pending); completed=failed=0
    def checkpoint(state='running',message=''):
        _write_json(PROGRESS_PATH,{'state':state,'bank':bank,'message':message,'total':total,'pending':len(pending),'reused':reused,'completed':completed,'failed':failed,'remaining':max(0,len(pending)-completed),'updated_at':datetime.now(timezone.utc).isoformat()})
        if progress: progress(f'{bank}: {reused+completed}/{total} captured · {max(0,len(pending)-completed)} remaining · {failed} failed. {message}')
    if not pending:
        checkpoint('complete','Every selected page already has cached text and screenshot.')
        return {'bank':bank,'total':total,'new':0,'reused':reused,'failed':0,'cancelled':False}
    from playwright.async_api import async_playwright
    from camoufox.async_api import AsyncNewBrowser
    checkpoint(message='Opening visible Camoufox browser.')
    async with async_playwright() as pw:
        browser=await AsyncNewBrowser(pw,headless=not visible,geoip=False,humanize=True); context=await browser.new_context(locale='en-BE',timezone_id='Europe/Brussels',viewport={'width':1440,'height':1000}); page=await context.new_page()
        try:
            for url in pending:
                if _CAPTURE_CANCEL.is_set(): break
                entry={'bank':bank,'url':url,'campaign_id':campaign_id(bank,url),'capture_date':datetime.now(timezone.utc).isoformat()}; checkpoint(message=f'Rendering {url}')
                try:
                    response=await page.goto(url,wait_until='domcontentloaded',timeout=90000)
                    try: await page.wait_for_load_state('networkidle',timeout=12000)
                    except Exception: pass
                    await page.wait_for_timeout(2500)
                    status=response.status if response else 0; title=await page.title(); body=(await page.locator('body').inner_text(timeout=20000)).strip(); html=await page.content()
                    if status in (403,429) or any(x in (title+' '+body[:1000]).lower() for x in ('access denied','verify you are human','captcha','just a moment')):
                        checkpoint('challenge','Protection challenge detected; complete it in the visible browser. Waiting 45 seconds.'); await page.wait_for_timeout(45000); body=(await page.locator('body').inner_text()).strip(); html=await page.content()
                    key=hashlib.sha256(url.encode()).hexdigest(); html_path=folder/f'{key}.html'; text_path=folder/f'{key}.txt'; shot_path=folder/f'{key}.png'
                    html_path.write_text(html,encoding='utf8'); text_path.write_text(body,encoding='utf8'); await page.screenshot(path=str(shot_path),full_page=True,animations='disabled')
                    dom=await page.evaluate("""() => {const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>1&&r.height>1};return {paragraphs:document.querySelectorAll('p').length,headings:document.querySelectorAll('h1,h2,h3,h4,h5,h6').length,images:document.images.length,visible_images:[...document.images].filter(visible).length,buttons:document.querySelectorAll('button,[role=button]').length,links:document.links.length,page_width:document.documentElement.scrollWidth,page_height:document.documentElement.scrollHeight}}""")
                    metrics={**_text_metrics(body),'paragraph_count':dom['paragraphs'],'heading_count':dom['headings'],'image_count':dom['images'],'visible_image_count':dom['visible_images'],'button_count':dom['buttons'],'link_count':dom['links'],'page_width':dom['page_width'],'page_height':dom['page_height'],'viewport_width':1440,'viewport_height':1000}
                    metrics['text_image_ratio']=round(metrics['word_count']/max(1,metrics['visible_image_count']),2); metrics.update(_image_metrics(shot_path))
                    quantitative=extract_quantitative_html_metrics(html)
                    entry.update({'status':status,'title':title,'html_file':html_path.name,'text_file':text_path.name,'screenshot_file':shot_path.name,'metrics':metrics,'quantitative_html_metrics':quantitative,'quantitative_extractor_version':EXTRACTOR_VERSION,'captured_at':datetime.now(timezone.utc).isoformat()}); entry.pop('capture_error',None)
                    if not _capture_complete(folder,entry):
                        raise ValueError('Rendered page text or screenshot is empty; page is not ready for campaign coding.')
                except Exception as exc:
                    failed+=1
                    entry.update({'status':0,'capture_error':f'{type(exc).__name__}: {exc}'})
                index[url]=entry; completed+=1; _write_json(folder/'index.json',index); checkpoint()
        finally:
            await context.close(); await browser.close()
    state='cancelled' if _CAPTURE_CANCEL.is_set() else ('complete_with_failures' if failed else 'complete'); checkpoint(state); return {'bank':bank,'total':total,'new':completed,'reused':reused,'failed':failed,'cancelled':_CAPTURE_CANCEL.is_set()}

def run_demo_capture(bank,urls,visible=True,progress=None):
    if not _CAPTURE_LOCK.acquire(False): raise RuntimeError('A demo capture is already running.')
    _CAPTURE_CANCEL.clear()
    def runner():
        loop=asyncio.ProactorEventLoop() if hasattr(asyncio,'ProactorEventLoop') else asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        try: return loop.run_until_complete(_capture_pages(bank,urls,visible,None))
        finally: loop.close()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(runner); last=None
            while not future.done():
                current=_read_json(PROGRESS_PATH,{})
                marker=(current.get('state'),current.get('message'),current.get('completed'),current.get('remaining'))
                if progress and marker!=last:
                    progress(f"{current.get('bank',bank)}: {current.get('reused',0)+current.get('completed',0)}/{current.get('total',len(urls))} captured - {current.get('remaining',0)} remaining - {current.get('failed',0)} failed. {current.get('message','')}"); last=marker
                time.sleep(.75)
            return future.result()
    finally: _CAPTURE_LOCK.release()

def all_demo_captures(banks=None):
    selected=set(banks or DEMO_BANKS); output=[]
    from demo_manual_youth import OLD_URLS as YOUTH_ALIASES
    for bank in selected:
        folder=capture_dir(bank)
        for url,item in capture_index(bank).items():
            if bank=='ING' and url in YOUTH_ALIASES: continue
            if not _capture_complete(folder,item): continue
            row=dict(item); row['url']=url; row['bank']=bank
            if row.get('text_file'):
                try: row['text']=(folder/row['text_file']).read_text(encoding='utf8')
                except OSError: row['text']=''
            if row.get('screenshot_file'): row['screenshot_path']=str(folder/row['screenshot_file'])
            row['deterministic_metrics']=dict(row.get('metrics') or row.get('deterministic_metrics') or {})
            if not row.get('quantitative_html_metrics') and row.get('html_file'):
                html_path=folder/row['html_file']
                if html_path.exists(): row['quantitative_html_metrics']=extract_quantitative_html_metrics(html_path.read_text(encoding='utf8',errors='replace'))
            row['quantitative_html_metrics']=dict(row.get('quantitative_html_metrics') or {})
            row['quantitative_extractor_version']=row.get('quantitative_extractor_version') or EXTRACTOR_VERSION
            output.append(row)
    return sorted(output,key=lambda x:(x['bank'],x['url']))

def _demo_ai_call(capture,boss_instruction=''):
    system=read_prompt('demo_campaign_coding_system.md',{'BOSS_INSTRUCTION':boss_instruction.strip() or 'None.'}); dimensions=read_prompt('demo_campaign_features.md')
    payload={'metadata':{k:capture.get(k) for k in ('bank','url','campaign_id','capture_date','title')},'deterministic_metrics':capture.get('deterministic_metrics') or capture.get('metrics',{}),'quantitative_html_metrics':capture.get('quantitative_html_metrics',{}),'required_framework':dimensions,'rendered_text':capture.get('text','')[:70000]}
    parts=capture.get('screenshot_sections')
    if parts:
        if len(parts)!=6 or capture.get('text_source')!='manual_screenshot_ocr': raise ValueError('Manual campaign needs all six ordered screenshots and labelled OCR text')
        payload['evidence_provenance']='User-supplied saved HTML is a JS shell. rendered_text is a manually reviewed OCR transcription of the six screenshots, NOT HTML-derived text; verify screenshot wording, dates, amounts, and conditions before quoting or asserting an offer. Deterministic text counts are from the screenshot transcript, not DOM. HTML quantitative metrics describe the saved JS shell only.'
        payload['screenshot_sections']='Six full-width user screenshots ordered from top to bottom, each supplied as a separate image below.'
        folder=capture_dir(capture['bank'])
        images=[]
        for number,name in enumerate(parts,1):
            image=folder/name
            if not image.is_file(): raise FileNotFoundError(f'Missing manual screenshot section {number}: {name}')
            images.extend([{'type':'text','text':f'Screenshot section {number}/6 (top to bottom)'}, {'type':'image_url','image_url':{'url':_manual_image_data_url(image),'detail':'high'}}])
    else:
        images=[{'type':'image_url','image_url':{'url':_visual_evidence_data_url(Path(capture['screenshot_path'])),'detail':'high'}}]
    settings=provider_settings(); messages=[{'role':'system','content':system},{'role':'user','content':[{'type':'text','text':json.dumps(payload,ensure_ascii=False)},*images]}]
    last=None
    for attempt in range(7):
        try:
            _wait_request_slot(); response=client().chat.completions.create(model=settings['model'],messages=messages,response_format={'type':'json_object'}); return parse_json(response.choices[0].message.content or '')
        except Exception as exc:
            last=exc
            if attempt==6: raise
            time.sleep(min(90,3*(2**attempt)))
    raise last

def _validate_scores(result):
    scores=result.get('communication_scores'); errors=[]
    if not isinstance(scores,dict): return ['communication_scores is missing']
    for dimension in COMMUNICATION_DIMENSIONS:
        item=scores.get(dimension)
        if not isinstance(item,dict): errors.append(f'{dimension}: missing object'); continue
        score=item.get('score')
        if score is not None and (not isinstance(score,int) or isinstance(score,bool) or not 1<=score<=5): errors.append(f'{dimension}: score must be integer 1-5 or null')
        if not item.get('justification'): errors.append(f'{dimension}: missing justification')
        if not item.get('evidence_quote'): errors.append(f'{dimension}: missing evidence quote')
    return errors

def build_demo_campaigns(banks=None,concurrent_calls=5,request_spacing=.5,boss_instruction='',progress=None,retry_errors=True,force_recode=False):
    selected_banks=set(banks or DEMO_BANKS)
    captures=[x for x in all_demo_captures(selected_banks) if x.get('screenshot_path') and x.get('text')]
    existing=_read_json(RUN_PATH,{'schema_version':'demo-v1','records':[]}); by_url={x.get('source_url'):x for x in existing.get('records',[]) if x.get('source_url')}
    pending=[x for x in captures if force_recode or x['url'] not in by_url or (retry_errors and (by_url[x['url']].get('error') or by_url[x['url']].get('recode_error')))]
    if not pending: return existing
    configure_ai_pacing(request_spacing); probe=provider_preflight(); completed=failed=0; records=list(by_url.values()); workers=min(max(1,int(concurrent_calls)),20,len(pending))
    if progress: progress(f"Provider {probe['model']} connected. Coding {len(pending)} screenshot-backed campaigns with {workers} concurrent calls.")
    def process(capture):
        result=_demo_ai_call(capture,boss_instruction); errors=_validate_scores(result)+validate_demo_coding(result)
        if errors: raise ValueError('; '.join(errors))
        return {'source_url':capture['url'],'bank':capture['bank'],'campaign_id':capture['campaign_id'],'capture_date':capture.get('capture_date'),'screenshot_file':capture.get('screenshot_path'),'screenshot_sections':capture.get('screenshot_sections'),'text_source':capture.get('text_source'),'evidence_source':capture.get('evidence_source'),'html_evidence_limit':capture.get('html_evidence_limit'),'deterministic_metrics':capture.get('deterministic_metrics') or capture.get('metrics',{}),'quantitative_html_metrics':capture.get('quantitative_html_metrics',{}),'quantitative_extractor_version':capture.get('quantitative_extractor_version',EXTRACTOR_VERSION),'campaign':result.get('campaign',{}),'communication_scores':result['communication_scores'],'visual_schema_version':VISUAL_SCHEMA_VERSION,'visual_assessment':result.get('visual_assessment',{}),'dominant_characteristics':result.get('dominant_characteristics',[]),'dominant_characteristics_evidence':result.get('dominant_characteristics_evidence',{}),'overall_communication_profile':result.get('overall_communication_profile'),'overall_communication_profile_evidence':result.get('overall_communication_profile_evidence'),'evidence_quality':result.get('evidence_quality',{})}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(process,x):x for x in pending}
        for future in as_completed(futures):
            capture=futures[future]
            try: replacement=future.result()
            except Exception as exc:
                failed+=1
                previous=next((record for record in records if record.get('source_url')==capture['url']),None)
                if previous and previous.get('communication_scores'):
                    # Keep the last valid coding until a retry succeeds; never silently drop paid results.
                    replacement={**previous,'recode_error':f'{type(exc).__name__}: {exc}'}
                else:
                    replacement={'source_url':capture['url'],'bank':capture['bank'],'campaign_id':capture['campaign_id'],'screenshot_file':capture.get('screenshot_path'),'deterministic_metrics':capture.get('deterministic_metrics') or capture.get('metrics',{}),'quantitative_html_metrics':capture.get('quantitative_html_metrics',{}),'quantitative_extractor_version':capture.get('quantitative_extractor_version',EXTRACTOR_VERSION),'error':f'{type(exc).__name__}: {exc}'}
            records=[record for record in records if record.get('source_url')!=capture['url']]; records.append(replacement)
            completed+=1; output={'schema_version':'demo-v1','created_at':datetime.now(timezone.utc).isoformat(),'model':provider_settings()['model'],'status':'running','records':records}; _write_json(RUN_PATH,output)
            if progress: progress(f'Demo campaigns coded {completed}/{len(pending)} - failed {failed}')
    deduped={x['source_url']:x for x in records}; final={'schema_version':'demo-v1','created_at':datetime.now(timezone.utc).isoformat(),'model':provider_settings()['model'],'status':'complete_with_failures' if failed or any(x.get('error') or x.get('recode_error') for x in deduped.values()) else 'complete','records':sorted(deduped.values(),key=lambda x:(x.get('bank',''),x.get('campaign_id','')))}; _write_json(RUN_PATH,final); return final

def load_demo_run(): return _read_json(RUN_PATH,{'schema_version':'demo-v1','records':[]})

def radar_values(records):
    values={}
    for dimension in COMMUNICATION_DIMENSIONS:
        nums=[r.get('communication_scores',{}).get(dimension,{}).get('score') for r in records]; nums=[x for x in nums if isinstance(x,(int,float)) and not isinstance(x,bool)]
        values[dimension]=round(statistics.mean(nums),2) if nums else None
    return values

def selection_options(records):
    options={}
    for bank in DEMO_BANKS:
        subset=[x for x in records if x.get('bank')==bank and not x.get('error')]
        if subset: options[f'{bank} — all campaigns ({len(subset)})']={'label':bank,'records':subset,'type':'bank'}
    for record in records:
        if not record.get('error'): options[record['campaign_id']]={'label':record['campaign_id'],'records':[record],'type':'campaign'}
    return options

# Compact chart palette shared across communication, numeric and categorical comparisons.
_DEMO_CHART_COLORS=('#ff7838','#38cda2')
_DEMO_CHART_BG='#22252b'
_DEMO_CHART_TEXT='#eef1f5'
_DEMO_CHART_GRID='#4b525c'


def _style_chart(fig,ax):
    fig.patch.set_facecolor(_DEMO_CHART_BG)
    ax.set_facecolor(_DEMO_CHART_BG)
    ax.tick_params(colors=_DEMO_CHART_TEXT,labelsize=9)
    for spine in ax.spines.values(): spine.set_color(_DEMO_CHART_GRID)
    ax.grid(axis='x',color=_DEMO_CHART_GRID,alpha=.45)
    ax.set_axisbelow(True)


def _metric_label(metric):
    if metric.startswith('quantitative.'):
        return QUANTITATIVE_METRIC_LABELS.get(metric.split('.',1)[1],metric)
    return METRIC_LABELS.get(metric,metric)


def _metric_value(record,metric):
    if metric.startswith('quantitative.'):
        return record.get('quantitative_html_metrics',{}).get(metric.split('.',1)[1])
    return (record.get('deterministic_metrics') or record.get('metrics') or {}).get(metric)


def _numeric_values(records,metric):
    return [value for record in records if isinstance(value:=_metric_value(record,metric),(int,float))
            and not isinstance(value,bool) and math.isfinite(value)]


def _number_label(value):
    if value == 0: return '0'
    return f'{value:,.2f}'.rstrip('0').rstrip('.') if abs(value) < 100 else f'{value:,.0f}'


def radar_figure(selections):
    dimensions=COMMUNICATION_DIMENSIONS
    angles=np.linspace(0,2*np.pi,len(dimensions),endpoint=False).tolist()
    fig,ax=plt.subplots(figsize=(7.3,5.9),subplot_kw={'polar':True})
    _style_chart(fig,ax)
    ax.grid(color=_DEMO_CHART_GRID,alpha=.55)
    for (label,records),color in zip(selections,_DEMO_CHART_COLORS):
        data=radar_values(records)
        values=[data[d] if data[d] is not None else np.nan for d in dimensions]
        closed_angles=angles+[angles[0]]; closed_values=values+[values[0]]
        ax.plot(closed_angles,closed_values,linewidth=2.2,color=color,label=label,marker='o',markersize=2.7)
        if all(math.isfinite(value) for value in values): ax.fill(closed_angles,closed_values,alpha=.10,color=color)
    labels=[name.replace(' orientation','\norientation').replace(' intensity','\nintensity').replace(' character','\ncharacter') for name in dimensions]
    ax.set_xticks(angles,labels,fontsize=8,color=_DEMO_CHART_TEXT)
    ax.tick_params(axis='x',pad=7)
    ax.set_ylim(1,5)
    ax.set_yticks([1,2,3,4,5])
    ax.set_yticklabels(['1','2','3','4','5'],color=_DEMO_CHART_TEXT,fontsize=8)
    ax.set_rlabel_position(0)
    fig.subplots_adjust(left=.21,right=.79,top=.83,bottom=.13)
    fig.legend(loc='upper center',bbox_to_anchor=(.5,.99),ncol=2,frameon=False,labelcolor=_DEMO_CHART_TEXT,fontsize=8)
    return fig


def _comparison_figure(selections,metrics,box=False):
    # Independent horizontal scales prevent a character count from hiding image counts.
    height=max(2.8,1.65*len(metrics)+.8)
    fig,axes=plt.subplots(len(metrics),1,figsize=(8.2,height),squeeze=False)
    for axis,metric in zip(axes.flat,metrics):
        _style_chart(fig,axis)
        axis.set_title(_metric_label(metric),loc='left',color=_DEMO_CHART_TEXT,fontsize=11,pad=9)
        positions=list(range(len(selections)))[::-1]
        present=[]
        for (label,records),pos,color in zip(selections,positions,_DEMO_CHART_COLORS):
            values=_numeric_values(records,metric)
            if not values: continue
            present.extend(values)
            if box and len(values)>1:
                axis.boxplot([values],positions=[pos],orientation='horizontal',widths=.42,patch_artist=True,
                             manage_ticks=False,showfliers=True,
                             boxprops={'facecolor':color,'edgecolor':color,'alpha':.45},
                             medianprops={'color':'white','linewidth':2},
                             whiskerprops={'color':color},capprops={'color':color},
                             flierprops={'marker':'.','markerfacecolor':color,'markeredgecolor':color})
                axis.scatter(values,np.full(len(values),pos)+np.linspace(-.07,.07,len(values)),
                             c=color,s=15,alpha=.6,zorder=3)
            elif box:
                axis.scatter(values,[pos],color=color,s=75,marker='D',zorder=4)
                axis.annotate(_number_label(values[0]),(values[0],pos),xytext=(7,0),textcoords='offset points',
                              fontsize=9,color=_DEMO_CHART_TEXT,va='center')
            else:
                value=statistics.mean(values)
                axis.barh(pos,value,color=color,height=.42,alpha=.9)
                axis.annotate(_number_label(value),(value,pos),xytext=(7 if value>=0 else -7,0),
                              textcoords='offset points',ha='left' if value>=0 else 'right',
                              color=_DEMO_CHART_TEXT,fontsize=9,va='center')
        axis.set_yticks(positions,[f'{label} (n={len(_numeric_values(records,metric))})' if box else label
                                   for label,records in selections],color=_DEMO_CHART_TEXT)
        axis.set_ylim(-.6,len(selections)-.4)
        axis.set_xlabel('Campaign values' if box else 'Mean per campaign',color=_DEMO_CHART_TEXT,fontsize=8)
        axis.margins(x=.18)
        if not present: axis.text(.5,.5,'No numeric values available',transform=axis.transAxes,
                                  color=_DEMO_CHART_TEXT,ha='center')
    fig.subplots_adjust(left=.22,right=.88,top=.96,bottom=.09,hspace=.95)
    return fig


def metrics_figure(selections,metrics):
    return _comparison_figure(selections,metrics,box=False)


def box_metrics_figure(selections,metrics):
    return _comparison_figure(selections,metrics,box=True)


def category_figure(graph_rows,selections,*,mode='Individual campaigns',eligible=None):
    """Categories are nominal, not 1-5 scores: show presence or bank prevalence."""
    from collections import Counter
    from matplotlib.lines import Line2D
    categories=sorted({row['Category'] for row in graph_rows})
    if not categories: raise ValueError('No categories to chart')
    fig,ax=plt.subplots(figsize=(8.2,min(5.6,max(2.7,1.0+.47*len(categories)))))
    _style_chart(fig,ax)
    positions=np.arange(len(categories))
    counts=Counter((row['Selection'],row['Category']) for row in graph_rows)
    if mode=='Individual campaigns':
        # A single page either has a tag or does not; a 0-1 count axis
        # misleadingly resembles the 1-5 communication score scale.
        ax.grid(False)
        for i,(label,_) in enumerate(selections[:2]):
            for y,category in enumerate(categories):
                present=counts[(label,category)]>0
                ax.scatter(i,y,s=145 if present else 70,marker='o',zorder=3,
                           facecolors=_DEMO_CHART_COLORS[i] if present else 'none',
                           edgecolors=_DEMO_CHART_COLORS[i],linewidths=1.6,alpha=.95)
                ax.annotate('Yes' if present else 'No',(i,y),xytext=(13,0),
                            textcoords='offset points',va='center',color=_DEMO_CHART_TEXT,fontsize=9)
        ax.set_xticks([0,1],['Left','Right'],color=_DEMO_CHART_TEXT)
        ax.set_xlim(-.55,1.7)
        ax.set_xlabel('Label present in selected campaign',color=_DEMO_CHART_TEXT,fontsize=9)
        handles=[Line2D([0],[0],marker='o',linestyle='none',color=color,label=label,markersize=8)
                 for (label,_),color in zip(selections[:2],_DEMO_CHART_COLORS)]
    elif mode=='Whole banks':
        eligible=eligible or {}
        width=.35
        for i,(label,_) in enumerate(selections[:2]):
            total=eligible.get(label,0)
            values=[100*counts[(label,category)]/total if total else 0 for category in categories]
            bars=ax.barh(positions+(i-.5)*width,values,height=width*.92,
                         color=_DEMO_CHART_COLORS[i],label=label,alpha=.9)
            for bar,value in zip(bars,values):
                if value: ax.text(min(value+1.3,99),bar.get_y()+bar.get_height()/2,f'{value:.0f}%',
                                  va='center',fontsize=8,color=_DEMO_CHART_TEXT)
        ax.set_xlim(0,105)
        ax.set_xticks([0,25,50,75,100],['0%','25%','50%','75%','100%'])
        ax.set_xlabel('Share of eligible coded campaigns with this label',color=_DEMO_CHART_TEXT,fontsize=9)
        handles=None
    else:
        plt.close(fig)
        raise ValueError(f'Unknown comparison level: {mode}')
    ax.set_yticks(positions,categories,color=_DEMO_CHART_TEXT)
    ax.invert_yaxis()
    fig.subplots_adjust(left=.25,right=.89,top=.81,bottom=.17)
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.99),ncol=2,
               frameon=False,labelcolor=_DEMO_CHART_TEXT,fontsize=8)
    return fig


def distribution_figure(selections,dimension):
    fig,ax=plt.subplots(figsize=(9,4)); labels=[]; data=[]
    for label,records in selections:
        nums=[r.get('communication_scores',{}).get(dimension,{}).get('score') for r in records]; nums=[x for x in nums if isinstance(x,(int,float))]
        if nums: labels.append(label); data.append(nums)
    ax.boxplot(data,tick_labels=labels,vert=False); ax.set_xlim(.8,5.2); ax.set_xlabel('1–5 positional score'); ax.set_title(f'{dimension} distribution'); fig.tight_layout(); return fig

def refresh_quantitative_metrics(banks=None):
    """Re-run the replaceable team HTML extractor over every cached demo HTML file."""
    selected=set(banks or DEMO_BANKS); updated=missing=0
    for bank in selected:
        folder=capture_dir(bank); index=capture_index(bank)
        for url,item in index.items():
            html_path=folder/item.get('html_file','')
            if not item.get('html_file') or not html_path.exists(): missing+=1; continue
            item['quantitative_html_metrics']=extract_quantitative_html_metrics(html_path.read_text(encoding='utf8',errors='replace'))
            item['quantitative_extractor_version']=EXTRACTOR_VERSION; updated+=1
        _write_json(folder/'index.json',index)
    run=_read_json(RUN_PATH,None)
    if run:
        captures={row['url']:row for row in all_demo_captures(selected)}
        for record in run.get('records',[]):
            capture=captures.get(record.get('source_url'))
            if capture:
                record['quantitative_html_metrics']=capture.get('quantitative_html_metrics',{})
                record['quantitative_extractor_version']=capture.get('quantitative_extractor_version',EXTRACTOR_VERSION)
        _write_json(RUN_PATH,run)
    return {'updated':updated,'missing_html':missing,'extractor_version':EXTRACTOR_VERSION}

def refresh_quantitative_html_metrics(banks=None):
    return refresh_quantitative_metrics(banks)

def _capture_complete(folder,item):
    text_file=folder/item['text_file'] if item.get('text_file') else None
    shot_file=folder/item['screenshot_file'] if item.get('screenshot_file') else None
    sections=item.get('screenshot_sections')
    sections_ready=(not sections or (len(sections)==6 and all((folder/name).is_file() and (folder/name).stat().st_size>0 for name in sections)))
    return bool(not item.get('capture_error') and not item.get('error')
                and text_file and text_file.is_file() and text_file.stat().st_size>0
                and shot_file and shot_file.is_file() and shot_file.stat().st_size>0
                and sections_ready)


def capture_status(bank,urls):
    folder=capture_dir(bank); index=capture_index(bank); captured=screenshots=failed=ready=0
    for url in urls:
        item=index.get(url,{})
        if item.get('text_file') and (folder/item['text_file']).is_file() and (folder/item['text_file']).stat().st_size>0: captured+=1
        if item.get('screenshot_file') and (folder/item['screenshot_file']).is_file() and (folder/item['screenshot_file']).stat().st_size>0: screenshots+=1
        if item.get('capture_error') or item.get('error'): failed+=1
        if _capture_complete(folder,item): ready+=1
    return {'total':len(urls),'captured':captured,'screenshots':screenshots,'failed':failed,'remaining':len(urls)-ready}

def load_demo_records():
    captures=all_demo_captures(); coded={x.get('source_url'):x for x in load_demo_run().get('records',[]) if x.get('source_url')}; output=[]
    for capture in captures:
        row=dict(capture); coded_row=coded.pop(capture['url'],None)
        if coded_row: row.update(coded_row)
        output.append(row)
    output.extend(coded.values())
    return sorted(output,key=lambda x:(x.get('bank',''),x.get('campaign_id',''),x.get('url','')))

def run_demo_coding(banks=None,progress=None,concurrent_calls=5,request_spacing=.5,boss_instruction='',retry_errors=True,force_recode=False):
    selected=set(banks or DEMO_BANKS)
    result=build_demo_campaigns(selected,concurrent_calls,request_spacing,boss_instruction,progress,retry_errors,force_recode)
    records=result.get('records',[]); scoped=[x for x in records if x.get('bank') in selected]; failed=sum(bool(x.get('error') or x.get('recode_error')) for x in scoped)
    return {'successful':sum(bool(x.get('communication_scores')) for x in scoped),'failed':failed,'status':result.get('status'),'records':records,'selected_records':scoped,'banks':sorted(selected),'path':str(RUN_PATH)}

def comparison_profile(records):
    scores=radar_values(records); evidence={}
    for dimension in COMMUNICATION_DIMENSIONS:
        evidence[dimension]=[str(r.get('communication_scores',{}).get(dimension,{}).get('evidence_quote')) for r in records if r.get('communication_scores',{}).get(dimension,{}).get('evidence_quote')]
    return {'scores':scores,'evidence':evidence,'records':records}

def _save_demo_figure(fig,prefix):
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f'); path=DEMO_GRAPHS/f'{stamp}-{prefix}.png'; fig.savefig(path,dpi=125,bbox_inches='tight'); plt.close(fig); return path

def radar_chart(profiles,title='Communication profile - position, not quality',aggregate=None):
    selections=[(label,profile.get('records',[])) for label,profile in profiles.items()]
    return _save_demo_figure(radar_figure(selections),'communication-radar')


def metric_chart(records,metrics,chart_type='bar',selections=None):
    # Explicit Left/Right selections keep same-bank campaigns distinct.
    if selections is None:
        banks=sorted({r.get('bank') for r in records if r.get('bank')})
        selections=[(bank,[r for r in records if r.get('bank')==bank]) for bank in banks]
    fig=box_metrics_figure(selections,metrics) if chart_type=='box' else metrics_figure(selections,metrics)
    return _save_demo_figure(fig,'numeric-comparison')


def category_chart(graph_rows,selections,*,mode='Individual campaigns',eligible=None):
    return _save_demo_figure(category_figure(graph_rows,selections,mode=mode,eligible=eligible),'category-comparison')

def demo_chat(messages,records,instruction=''):
    context=json.dumps(records,ensure_ascii=False,separators=(',',':')); system=read_prompt('demo_analyst_chat_system.md',{'ADDITIONAL_INSTRUCTION':instruction.strip() or 'None.','CONTEXT_JSON':context}); settings=provider_settings(); _wait_request_slot(); response=client().chat.completions.create(model=settings['model'],messages=[{'role':'system','content':system}]+messages[-20:]); return response.choices[0].message.content or ''
