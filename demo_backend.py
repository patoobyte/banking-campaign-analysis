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

def save_demo_urls(bank,text):
    data=load_demo_urls(); valid=[]; invalid=[]
    for raw in text.splitlines():
        if not raw.strip(): continue
        url,_=_normalise_url(raw)
        if _valid_for_bank(bank,url):
            if url not in valid: valid.append(url)
        else: invalid.append(raw.strip())
    if invalid: raise ValueError('Invalid or wrong-host URLs: '+', '.join(invalid))
    data['banks'][bank]=valid; data['updated_at']=datetime.now(timezone.utc).isoformat(); _write_json(URLS_PATH,data); return valid

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

def is_demo_capture_running(): return _CAPTURE_LOCK.locked()
def stop_demo_capture(): _CAPTURE_CANCEL.set(); return is_demo_capture_running()

async def _capture_pages(bank,urls,visible=True,progress=None):
    from playwright.async_api import async_playwright
    from camoufox.async_api import AsyncNewBrowser
    folder=capture_dir(bank); index=capture_index(bank); pending=[url for url in urls if not index.get(url,{}).get('screenshot_file') or not (folder/index[url]['screenshot_file']).exists()]
    total=len(urls); reused=total-len(pending); completed=failed=0
    def checkpoint(state='running',message=''):
        _write_json(PROGRESS_PATH,{'state':state,'bank':bank,'message':message,'total':total,'pending':len(pending),'reused':reused,'completed':completed,'failed':failed,'remaining':max(0,len(pending)-completed),'updated_at':datetime.now(timezone.utc).isoformat()})
        if progress: progress(f'{bank}: {reused+completed}/{total} captured · {max(0,len(pending)-completed)} remaining · {failed} failed. {message}')
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
                except Exception as exc:
                    failed+=1; entry.update({'status':0,'capture_error':f'{type(exc).__name__}: {exc}'})
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
    for bank in selected:
        folder=capture_dir(bank)
        for url,item in capture_index(bank).items():
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
    image_url=_visual_evidence_data_url(Path(capture['screenshot_path'])); settings=provider_settings(); messages=[{'role':'system','content':system},{'role':'user','content':[{'type':'text','text':json.dumps(payload,ensure_ascii=False)},{'type':'image_url','image_url':{'url':image_url,'detail':'high'}}]}]
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

def build_demo_campaigns(banks=None,concurrent_calls=5,request_spacing=.5,boss_instruction='',progress=None,retry_errors=True):
    selected_banks=set(banks or DEMO_BANKS)
    captures=[x for x in all_demo_captures(selected_banks) if x.get('screenshot_path') and x.get('text')]
    existing=_read_json(RUN_PATH,{'schema_version':'demo-v1','records':[]}); by_url={x.get('source_url'):x for x in existing.get('records',[]) if x.get('source_url')}
    pending=[x for x in captures if x['url'] not in by_url or (retry_errors and by_url[x['url']].get('error'))]
    preserved=[x for x in by_url.values() if x.get('bank') not in selected_banks or not x.get('error') or not retry_errors]
    if not pending: return existing
    configure_ai_pacing(request_spacing); probe=provider_preflight(); completed=failed=0; records=list(preserved); workers=min(max(1,int(concurrent_calls)),20,len(pending))
    if progress: progress(f"Provider {probe['model']} connected. Coding {len(pending)} screenshot-backed campaigns with {workers} concurrent calls.")
    def process(capture):
        result=_demo_ai_call(capture,boss_instruction); errors=_validate_scores(result)
        if errors: raise ValueError('; '.join(errors))
        return {'source_url':capture['url'],'bank':capture['bank'],'campaign_id':capture['campaign_id'],'capture_date':capture.get('capture_date'),'screenshot_file':capture.get('screenshot_path'),'deterministic_metrics':capture.get('deterministic_metrics') or capture.get('metrics',{}),'quantitative_html_metrics':capture.get('quantitative_html_metrics',{}),'quantitative_extractor_version':capture.get('quantitative_extractor_version',EXTRACTOR_VERSION),'campaign':result.get('campaign',{}),'communication_scores':result['communication_scores'],'visual_assessment':result.get('visual_assessment',{}),'dominant_characteristics':result.get('dominant_characteristics',[]),'overall_communication_profile':result.get('overall_communication_profile'),'evidence_quality':result.get('evidence_quality',{})}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(process,x):x for x in pending}
        for future in as_completed(futures):
            capture=futures[future]
            try: records.append(future.result())
            except Exception as exc: failed+=1; records.append({'source_url':capture['url'],'bank':capture['bank'],'campaign_id':capture['campaign_id'],'screenshot_file':capture.get('screenshot_path'),'deterministic_metrics':capture.get('deterministic_metrics') or capture.get('metrics',{}),'quantitative_html_metrics':capture.get('quantitative_html_metrics',{}),'quantitative_extractor_version':capture.get('quantitative_extractor_version',EXTRACTOR_VERSION),'error':f'{type(exc).__name__}: {exc}'})
            completed+=1; output={'schema_version':'demo-v1','created_at':datetime.now(timezone.utc).isoformat(),'model':provider_settings()['model'],'status':'running','records':records}; _write_json(RUN_PATH,output)
            if progress: progress(f'Demo campaigns coded {completed}/{len(pending)} - failed {failed}')
    deduped={x['source_url']:x for x in records}; final={'schema_version':'demo-v1','created_at':datetime.now(timezone.utc).isoformat(),'model':provider_settings()['model'],'status':'complete_with_failures' if failed else 'complete','records':sorted(deduped.values(),key=lambda x:(x.get('bank',''),x.get('campaign_id','')))}; _write_json(RUN_PATH,final); return final

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

def radar_figure(selections):
    dimensions=COMMUNICATION_DIMENSIONS; angles=np.linspace(0,2*np.pi,len(dimensions),endpoint=False).tolist(); angles+=angles[:1]
    fig,ax=plt.subplots(figsize=(11,8),subplot_kw={'polar':True}); colors=['#ff6200','#00965e','#35a7ff','#e15b64']
    for color,(label,records) in zip(colors,selections):
        data=radar_values(records); values=[data[x] if data[x] is not None else 1 for x in dimensions]; values+=values[:1]; ax.plot(angles,values,linewidth=2,label=label,color=color); ax.fill(angles,values,alpha=.10,color=color)
    ax.set_xticks(angles[:-1],dimensions,fontsize=9); ax.set_ylim(1,5); ax.set_yticks([1,2,3,4,5]); ax.set_title('Communication profile — position, not quality',pad=25); ax.legend(loc='upper right',bbox_to_anchor=(1.28,1.15)); fig.tight_layout(); return fig

def _metric_value(record,metric):
    if metric.startswith('quantitative.'):
        return record.get('quantitative_html_metrics',{}).get(metric.split('.',1)[1])
    return record.get('deterministic_metrics',{}).get(metric)

def metrics_figure(selections,metrics):
    labels=[QUANTITATIVE_METRIC_LABELS.get(x.split('.',1)[1],x) if x.startswith('quantitative.') else METRIC_LABELS.get(x,x) for x in metrics]; x=np.arange(len(metrics)); width=.8/max(1,len(selections)); fig,ax=plt.subplots(figsize=(11,5))
    for i,(label,records) in enumerate(selections):
        vals=[]
        for metric in metrics:
            nums=[_metric_value(r,metric) for r in records]; nums=[n for n in nums if isinstance(n,(int,float))]
            vals.append(statistics.mean(nums) if nums else 0)
        ax.bar(x-.4+width/2+i*width,vals,width,label=label)
    ax.set_xticks(x,labels,rotation=25,ha='right'); ax.legend(); ax.set_title('Deterministic page and screenshot metrics'); fig.tight_layout(); return fig

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

def capture_status(bank,urls):
    folder=capture_dir(bank); index=capture_index(bank); captured=screenshots=failed=0
    for url in urls:
        item=index.get(url,{})
        text_ok=bool(item.get('text_file') and (folder/item['text_file']).exists())
        shot_ok=bool(item.get('screenshot_file') and (folder/item['screenshot_file']).exists())
        if text_ok: captured+=1
        if shot_ok: screenshots+=1
        if item.get('capture_error') or item.get('error'): failed+=1
    return {'total':len(urls),'captured':captured,'screenshots':screenshots,'failed':failed,'remaining':max(0,len(urls)-captured)}

def load_demo_records():
    captures=all_demo_captures(); coded={x.get('source_url'):x for x in load_demo_run().get('records',[]) if x.get('source_url')}; output=[]
    for capture in captures:
        row=dict(capture); coded_row=coded.pop(capture['url'],None)
        if coded_row: row.update(coded_row)
        output.append(row)
    output.extend(coded.values())
    return sorted(output,key=lambda x:(x.get('bank',''),x.get('campaign_id',''),x.get('url','')))

def run_demo_coding(banks=None,progress=None,concurrent_calls=5,request_spacing=.5,boss_instruction='',retry_errors=True):
    selected=set(banks or DEMO_BANKS)
    result=build_demo_campaigns(selected,concurrent_calls,request_spacing,boss_instruction,progress,retry_errors)
    records=result.get('records',[]); scoped=[x for x in records if x.get('bank') in selected]; failed=sum(bool(x.get('error')) for x in scoped)
    return {'successful':len(scoped)-failed,'failed':failed,'status':result.get('status'),'records':records,'selected_records':scoped,'banks':sorted(selected),'path':str(RUN_PATH)}

def comparison_profile(records):
    scores=radar_values(records); evidence={}
    for dimension in COMMUNICATION_DIMENSIONS:
        evidence[dimension]=[str(r.get('communication_scores',{}).get(dimension,{}).get('evidence_quote')) for r in records if r.get('communication_scores',{}).get(dimension,{}).get('evidence_quote')]
    return {'scores':scores,'evidence':evidence,'records':records}

def _save_demo_figure(fig,prefix):
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f'); path=DEMO_GRAPHS/f'{stamp}-{prefix}.png'; fig.savefig(path,dpi=160,bbox_inches='tight'); plt.close(fig); return path

def radar_chart(profiles,title='Communication profile - position, not quality',aggregate=None):
    selections=[(label,profile.get('records',[])) for label,profile in profiles.items()]
    fig=radar_figure(selections); fig.axes[0].set_title(title,pad=25); return _save_demo_figure(fig,'communication-radar')

def metric_chart(records,metrics,chart_type='bar'):
    banks=sorted({r.get('bank') for r in records if r.get('bank')})
    selections=[(bank,[r for r in records if r.get('bank')==bank]) for bank in banks]
    if chart_type=='box' and len(metrics)==1:
        metric=metrics[0]; fig,ax=plt.subplots(figsize=(10,5)); labels=[]; values=[]
        for label,subset in selections:
            nums=[_metric_value(r,metric) for r in subset]; nums=[x for x in nums if isinstance(x,(int,float))]
            if nums: labels.append(label); values.append(nums)
        if values: ax.boxplot(values,tick_labels=labels,vert=False)
        ax.set_title(f"{QUANTITATIVE_METRIC_LABELS.get(metric.split('.',1)[1],metric) if metric.startswith('quantitative.') else METRIC_LABELS.get(metric,metric)} distribution"); fig.tight_layout()
    else: fig=metrics_figure(selections,metrics)
    return _save_demo_figure(fig,'deterministic-metrics')

def demo_chat(messages,records,instruction=''):
    context=json.dumps(records,ensure_ascii=False,separators=(',',':')); system=read_prompt('demo_analyst_chat_system.md',{'ADDITIONAL_INSTRUCTION':instruction.strip() or 'None.','CONTEXT_JSON':context}); settings=provider_settings(); _wait_request_slot(); response=client().chat.completions.create(model=settings['model'],messages=[{'role':'system','content':system}]+messages[-20:]); return response.choices[0].message.content or ''
