from __future__ import annotations
import asyncio, gzip, hashlib, json, re, time, random, os, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, quote
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from config import SITEMAPS, RAW, FILTERS, bank_dir

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 DatasetBuilder/1.0"

def _atomic_json_write(path: Path, data) -> None:
    temporary=path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
    try:
        for attempt in range(12):
            try:
                os.replace(temporary,path)
                return
            except PermissionError:
                if attempt == 11: raise
                time.sleep(0.10*(attempt+1))
    finally:
        try: temporary.unlink(missing_ok=True)
        except OSError: pass

if '_SCRAPE_LOCKS_GUARD' not in globals(): _SCRAPE_LOCKS_GUARD=threading.Lock()
if '_SCRAPE_LOCKS' not in globals(): _SCRAPE_LOCKS={}
if '_SCRAPE_CANCEL_EVENTS' not in globals(): _SCRAPE_CANCEL_EVENTS={}
def _bank_scrape_lock(bank: str):
    key=bank.strip().lower()
    with _SCRAPE_LOCKS_GUARD:
        return _SCRAPE_LOCKS.setdefault(key,threading.Lock())

def _bank_cancel_event(bank: str):
    key=bank.strip().lower()
    with _SCRAPE_LOCKS_GUARD:
        return _SCRAPE_CANCEL_EVENTS.setdefault(key,threading.Event())

def is_scrape_running(bank: str) -> bool:
    lock=_bank_scrape_lock(bank)
    return lock.locked()

def request_scrape_stop(bank: str) -> bool:
    if not is_scrape_running(bank): return False
    _bank_cancel_event(bank).set()
    return True

def language(url: str) -> str:
    for part in urlparse(url).path.lower().split('/')[:5]:
        m = re.fullmatch(r'(fr|nl|en)(?:[-_][a-z]{2})?', part)
        if m: return m.group(1)
    return 'unknown'

def clean_visible_html(html: str) -> tuple[str, dict]:
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script','style','noscript','svg','template','nav','footer']): tag.decompose()
    main = soup.find('main') or soup.find('article') or soup.body or soup
    headings = [x.get_text(' ', strip=True) for x in main.find_all(re.compile('^h[1-6]$'))]
    paragraphs = [x.get_text(' ', strip=True) for x in main.find_all('p') if x.get_text(' ', strip=True)]
    lists = [[li.get_text(' ', strip=True) for li in ul.find_all('li', recursive=False)] for ul in main.find_all(['ul','ol'])]
    text = '\n'.join(x for x in main.stripped_strings if x)
    return text, {'headings': headings, 'paragraphs': paragraphs, 'lists': lists}

def _get(url: str) -> bytes:
    response = requests.get(url, headers={'User-Agent': UA}, timeout=60)
    response.raise_for_status(); return response.content

def gather_sitemaps(bank: str, seeds: list[str], progress=None) -> dict:
    import xml.etree.ElementTree as ET
    root_url = f"{urlparse(seeds[0]).scheme}://{urlparse(seeds[0]).netloc}"
    robots_url = root_url + '/robots.txt'
    try: robots_text = _get(robots_url).decode('utf8','replace')
    except Exception: robots_text = ''
    starts = re.findall(r'(?im)^\s*sitemap:\s*(\S+)', robots_text) or [root_url + '/sitemap.xml']
    parser = RobotFileParser(); parser.set_url(robots_url); parser.parse(robots_text.splitlines())
    queue=list(starts); seen=set(); rows={}; failures=[]
    while queue:
        url=queue.pop(0)
        if url in seen or urlparse(url).netloc != urlparse(root_url).netloc: continue
        seen.add(url)
        try:
            body=_get(url)
            if url.lower().split('?')[0].endswith('.gz'): body=gzip.decompress(body)
            doc=ET.fromstring(body)
            index=doc.tag.rsplit('}',1)[-1].lower()=='sitemapindex'
            for node in doc:
                values={child.tag.rsplit('}',1)[-1].lower():(child.text or '').strip() for child in node}
                loc=values.get('loc','')
                if not loc or urlparse(loc).netloc != urlparse(root_url).netloc: continue
                if index or loc.lower().split('?')[0].endswith(('.xml','.xml.gz')): queue.append(loc)
                else:
                    rows[loc]={'url':loc,'language':language(loc),'last_modified':values.get('lastmod'), 'sitemap_source':url,'robots_allowed':parser.can_fetch(UA,loc)}
        except Exception as exc: failures.append({'url':url,'error':str(exc)})
        if progress: progress(f'{len(seen)} sitemap files; {len(rows):,} URLs')
    result={'bank':bank,'created_at':datetime.now(timezone.utc).isoformat(),'seeds':seeds,'rows':sorted(rows.values(),key=lambda x:x['url']),'failures':failures}
    path=bank_dir(SITEMAPS,bank)/'latest.json'; path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8'); return result

def load_inventory(bank: str):
    path=bank_dir(SITEMAPS,bank)/'latest.json'
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else None

# Defaults remain editable per bank in data/url-filters/<bank>/filters.json.
DEFAULT_BANNED_TERMS = [
    'faq','help','support','article','articles','news','nieuws','actualites','actus','press','presse',
    'legal','legals','juridique','privacy','cookies','cookie','terms','conditions','voorwaarden',
    'about','about-us','who-we-are','a-propos','a-propos-de-nous','over-ons','contact','contact-us',
    'report','reports','annual-report','annual-reports','rapport','rapports','jaarverslag','jaarverslagen',
    'career','careers','jobs','job','vacature','vacatures','login'
]
DEFAULT_DESCENDANT_ROOTS = {
    'ING': [
        'https://www.ing.be/en/individuals/insurance/insure-my-home',
        'https://www.ing.be/fr/particuliers/assurances/assurer-mon-habitation',
        'https://www.ing.be/nl/particulieren/verzekeren/mijn-woning-verzekeren'
    ]
}

def filter_settings_path(bank: str): return bank_dir(FILTERS, bank) / 'filters.json'

def load_filter_settings(bank: str) -> dict:
    path=filter_settings_path(bank)
    defaults={'banned_terms':DEFAULT_BANNED_TERMS,'descendant_roots':DEFAULT_DESCENDANT_ROOTS.get(bank,[])}
    if not path.exists(): return defaults
    try: data=json.loads(path.read_text(encoding='utf8'))
    except (OSError,json.JSONDecodeError): return defaults
    return {'banned_terms':list(dict.fromkeys(str(x).strip() for x in data.get('banned_terms',[]) if str(x).strip())),
            'descendant_roots':list(dict.fromkeys(str(x).strip().rstrip('/') for x in data.get('descendant_roots',[]) if str(x).strip()))}

def save_filter_settings(bank: str, banned_terms: list[str], descendant_roots: list[str]) -> dict:
    data={'bank':bank,'updated_at':datetime.now(timezone.utc).isoformat(),
          'banned_terms':list(dict.fromkeys(x.strip().lower() for x in banned_terms if x.strip())),
          'descendant_roots':list(dict.fromkeys(x.strip().rstrip('/') for x in descendant_roots if x.strip()))}
    filter_settings_path(bank).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8'); return data

def _term_pattern(terms):
    # A user entry is literal. Hyphen, underscore and slash boundaries avoid accidental substring matches.
    escaped=[re.escape(x.strip().lower()) for x in terms if x.strip()]
    return re.compile(r'(?i)(?:^|[-_/])(?:'+'|'.join(escaped)+r')(?:$|[-_/])') if escaped else None

def _is_descendant(url: str, root: str) -> bool:
    u=urlparse(url); r=urlparse(root)
    if u.netloc.lower()!=r.netloc.lower(): return False
    up=u.path.rstrip('/'); rp=r.path.rstrip('/')
    return up.startswith(rp + '/')  # Keep the product root itself; reject only children.

def deterministic_filter(rows: list[dict], selected_languages: list[str], bank: str|None=None, settings: dict|None=None) -> tuple[list[dict],list[dict]]:
    kept=[]; rejected=[]; selected=set(selected_languages); settings=settings or load_filter_settings(bank or '')
    pattern=_term_pattern(settings.get('banned_terms',[])); roots=settings.get('descendant_roots',[])
    for row in rows:
        reason=None; path=urlparse(row['url']).path.lower()
        if not row.get('robots_allowed', True): reason='robots_disallowed'
        elif selected and row.get('language') not in selected: reason='language_out_of_scope'
        elif bank=='Revolut' and re.match(r'^/[a-z]{2}-[a-z]{2}(?:/|$)',path) and not re.match(r'^/(?:en|fr|nl)-be(?:/|$)',path): reason='market_out_of_scope'
        elif pattern and pattern.search(path): reason='banned_url_term'
        elif any(_is_descendant(row['url'],root) for root in roots): reason='descendant_of_banned_root'
        target=dict(row, deterministic_status='rejected' if reason else 'kept', deterministic_reason=reason)
        (rejected if reason else kept).append(target)
    return kept,rejected

def _json_visible_strings(value):
    """Extract human-facing strings from a public content API response."""
    skip={'url','href','src','id','uuid','key','type','componenttype','extension','transformbaseurl','original','publishedat','alt'}
    out=[]
    def walk(node,key=''):
        if isinstance(node,dict):
            for k,v in node.items():
                if str(k).lower() not in skip: walk(v,str(k))
        elif isinstance(node,list):
            for v in node: walk(v,key)
        elif isinstance(node,str):
            value=BeautifulSoup(node,'html.parser').get_text(' ',strip=True)
            if value and not value.startswith(('http://','https://')) and len(value)>1: out.append(value)
    walk(value)
    return '\n'.join(dict.fromkeys(out))

def _ing_pagemodel_url(html: str):
    soup=BeautifulSoup(html,'html.parser')
    for tag in soup.find_all(['link','a']):
        href=(tag.get('href') or '').replace('&amp;','&')
        if 'api.www.ing.be/' in href and '/pagemodel?' in href: return href
    return None

async def scrape_rendered_pages(bank: str, rows: list[dict], progress=None, cancel_event=None) -> dict:
    """Collect protection-sensitive sites through one real, visible Camoufox page."""
    from playwright.async_api import async_playwright
    from camoufox.async_api import AsyncNewBrowser
    cancel_event=cancel_event or threading.Event()
    folder=bank_dir(RAW,bank); html_dir=folder/'html'; text_dir=folder/'text'; html_dir.mkdir(exist_ok=True); text_dir.mkdir(exist_ok=True)
    index_path=folder/'index.json'; progress_path=folder/'progress.json'; index=_load_json_object_resilient(index_path)
    # Recover deterministic text files before deciding what remains.
    for row in rows:
        key=hashlib.sha256(row['url'].encode()).hexdigest(); tp=text_dir/f'{key}.txt'; hp=html_dir/f'{key}.html'
        if tp.exists() and tp.stat().st_size>0:
            entry=index.setdefault(row['url'],dict(row)); entry['text_file']=str(tp.relative_to(folder)); entry['text_chars']=tp.stat().st_size
            if hp.exists(): entry['html_file']=str(hp.relative_to(folder))
    pending=[row for row in rows if not index.get(row['url'],{}).get('text_file')]
    reused=len(rows)-len(pending); done=success=failed=retries=0
    def checkpoint(state='running',message=''):
        _atomic_json_write(progress_path,{'state':state,'mode':'visible_rendered_camoufox','message':message,'total':len(rows),'pending_at_start':len(pending),'reused':reused,'completed':done,'completed_this_run':done,'completed_total':reused+done,'successful_text_pages':success,'successful_this_run':success,'successful_total':reused+success,'failed':failed,'retry_attempts':retries,'remaining':max(0,len(pending)-done),'workers':1,'updated_at':datetime.now(timezone.utc).isoformat()})
    checkpoint(message='Opening one visible Camoufox browser. Revolut pages are rendered sequentially; images and scripts remain enabled.')
    async with async_playwright() as pw:
        browser=await AsyncNewBrowser(pw,headless=False,geoip=False,humanize=True)
        context=await browser.new_context(locale='en-BE',timezone_id='Europe/Brussels',viewport={'width':1440,'height':1000})
        page=await context.new_page()
        try:
            for row in pending:
                if cancel_event.is_set(): break
                started=time.time(); entry=dict(row); captured=False
                checkpoint(message=f"Visible Camoufox is rendering {row['url']}. If a challenge appears, complete it in the browser window.")
                for attempt in range(3):
                    if cancel_event.is_set(): break
                    try:
                        response=await page.goto(row['url'],wait_until='domcontentloaded',timeout=90000)
                        await page.wait_for_timeout(5000 if attempt==0 else 12000)
                        status=response.status if response else 0; html=await page.content(); title=await page.title()
                        body_text=await page.locator('body').inner_text(timeout=15000)
                        protection=status in (403,429) or any(token in (title+' '+body_text[:1000]).lower() for token in ('access denied','verify you are human','just a moment','captcha'))
                        if protection:
                            retries+=1; checkpoint('challenge',f'Revolut protection page detected. The visible browser will wait 30 seconds for manual completion before retry {attempt+2}/3.')
                            await page.wait_for_timeout(30000); continue
                        text,structure=clean_visible_html(html)
                        if len(text)<200 and len(body_text)>len(text): text=body_text
                        if status==200 and text.strip():
                            key=hashlib.sha256(row['url'].encode()).hexdigest(); hp=html_dir/f'{key}.html'; tp=text_dir/f'{key}.txt'
                            hp.write_text(html,encoding='utf8'); tp.write_text(text,encoding='utf8')
                            entry.update({'status':status,'title':title,'collector_mode':'visible_rendered_camoufox','html_file':str(hp.relative_to(folder)),'text_file':str(tp.relative_to(folder)),'captured_at':datetime.now(timezone.utc).isoformat(),'text_chars':len(text),'structure':structure,'elapsed_seconds':round(time.time()-started,2),'attempts':attempt+1})
                            entry.pop('error',None); success+=1; captured=True; break
                    except Exception as exc:
                        retries+=1; entry['error']=f'{type(exc).__name__}: {exc}'
                        if attempt<2: await page.wait_for_timeout(10000)
                if not captured:
                    failed+=1; entry.update({'status':entry.get('status',0),'captured_at':datetime.now(timezone.utc).isoformat(),'collector_mode':'visible_rendered_camoufox','error':entry.get('error','Rendered page did not produce usable text after 3 attempts.')})
                index[row['url']]=entry; done+=1; _atomic_json_write(index_path,index); checkpoint()
        finally:
            await context.close(); await browser.close()
    state='cancelled' if cancel_event.is_set() else ('complete_with_failures' if failed else 'complete'); checkpoint(state)
    return {'total':len(rows),'new':len(pending),'reused':reused,'successful_text_pages':success,'failed':failed,'retry_attempts':retries,'cancelled':cancel_event.is_set(),'index_path':str(index_path),'mode':'visible_rendered_camoufox'}

async def scrape_pages(bank: str, rows: list[dict], workers=10, progress=None, cancel_event=None) -> dict:
    """Resumable, paced bulk collection with retries and shared cooldowns for every bank."""
    if bank=='Revolut': return await scrape_rendered_pages(bank,rows,progress,cancel_event)
    from playwright.async_api import async_playwright
    from camoufox.async_api import AsyncNewBrowser
    cancel_event=cancel_event or threading.Event()
    folder=bank_dir(RAW,bank); html_dir=folder/'html'; text_dir=folder/'text'; html_dir.mkdir(exist_ok=True); text_dir.mkdir(exist_ok=True)
    index_path=folder/'index.json'; progress_path=folder/'progress.json'
    index=_load_json_object_resilient(index_path)
    # The URL hash makes text files self-identifying. Recover any successful files
    # omitted by an older/stale index writer instead of losing their cache status.
    recovered=0
    for row in rows:
        key=hashlib.sha256(row['url'].encode()).hexdigest(); tp=text_dir/f'{key}.txt'; hp=html_dir/f'{key}.html'; jp=html_dir/f'{key}.content.json'
        if tp.exists() and tp.stat().st_size>0:
            entry=index.setdefault(row['url'],dict(row)); entry['text_file']=str(tp.relative_to(folder)); entry['text_chars']=tp.stat().st_size
            if hp.exists(): entry['html_file']=str(hp.relative_to(folder))
            if jp.exists(): entry['content_json_file']=str(jp.relative_to(folder))
            recovered+=1
    if recovered: _atomic_json_write(index_path,index)
    pending=[r for r in rows if not index.get(r['url'],{}).get('text_file')]
    queue=asyncio.Queue()
    for row in pending: queue.put_nowait(row)
    lock=asyncio.Lock(); rate_lock=asyncio.Lock(); cooldown_lock=asyncio.Lock()
    next_request_at=0.0; cooldown_until=0.0; done=success=failed=0; retries=0
    def checkpoint(state='running',message=''):
        _atomic_json_write(progress_path,{'state':state,'message':message,'total':len(rows),'pending_at_start':len(pending),'reused':len(rows)-len(pending),'completed':done,'completed_this_run':done,'completed_total':len(rows)-len(pending)+done,'successful_text_pages':success,'successful_this_run':success,'successful_total':len(rows)-len(pending)+success,'failed':failed,'retry_attempts':retries,'remaining':max(0,len(pending)-done),'workers':workers,'cooldown_seconds_remaining':max(0,round(cooldown_until-time.monotonic())),'updated_at':datetime.now(timezone.utc).isoformat()})
    checkpoint()
    async with async_playwright() as pw:
        browser=await AsyncNewBrowser(pw,headless=True,geoip=False)
        context=await browser.new_context(locale='fr-BE',timezone_id='Europe/Brussels',no_viewport=True)
        async def throttled_get(url):
            nonlocal next_request_at
            while True:
                if cancel_event.is_set(): return None
                wait=max(0.0,cooldown_until-time.monotonic())
                if not wait: break
                checkpoint('cooldown',f'Server protection detected. Waiting {round(wait)} seconds before retrying.')
                await asyncio.sleep(min(1.0,wait))
            async with rate_lock:
                now=time.monotonic(); wait=max(0.0,next_request_at-now); next_request_at=max(now,next_request_at)+0.70
            if wait: await asyncio.sleep(wait)
            return await context.request.get(url,timeout=45000,fail_on_status_code=False)
        async def fetch_with_retry(url):
            nonlocal cooldown_until,retries
            response=None
            for attempt in range(8):
                if cancel_event.is_set(): return None,attempt
                try: response=await throttled_get(url); status=response.status if response else 0
                except Exception:
                    status=0; response=None
                if status not in (0,403,408,425,429,500,502,503,504): return response,attempt+1
                retries+=1
                # Shared cooldown stops all workers instead of letting them worsen a temporary block.
                retry_after=0
                if response:
                    try: retry_after=int(response.headers.get('retry-after','0'))
                    except ValueError: retry_after=0
                delay=max(retry_after,min(120,5*(2**attempt)))+random.random()*2
                async with cooldown_lock: cooldown_until=max(cooldown_until,time.monotonic()+delay)
                checkpoint('cooldown',f'HTTP {status or "network error"}. Pausing all workers for {round(delay)} seconds before retry {attempt+2}/8.')
            return response,8
        async def worker():
            nonlocal done,success,failed
            while True:
                if cancel_event.is_set(): return
                try: row=queue.get_nowait()
                except asyncio.QueueEmpty: return
                started=time.time(); entry=dict(row)
                try:
                    is_ing=urlparse(row['url']).netloc.lower().endswith('ing.be')
                    api_url=('https://api.www.ing.be/be/public/pagemodel?pageUrl='+quote(urlparse(row['url']).path,safe='')) if is_ing else None
                    target=row['url']; response,attempts=await fetch_with_retry(target); status=response.status if response else 0
                    api_json=None; html=''; content_type=response.headers.get('content-type','') if response else ''; text=''; structure={'headings':[],'paragraphs':[],'lists':[]}
                    if response and status==200:
                        body=await response.body(); html=body.decode('utf8','replace') if 'html' in content_type.lower() or not content_type else ''
                        text,structure=clean_visible_html(html) if html else (text,structure)
                        discovered=_ing_pagemodel_url(html) if is_ing and html else None
                        if discovered:
                            api_response,api_attempts=await fetch_with_retry(discovered)
                            attempts+=api_attempts
                            if api_response and api_response.status==200:
                                api_url=discovered; entry['content_api_url']=api_url; api_json=await api_response.json(); api_text=_json_visible_strings(api_json)
                                if len(api_text)>len(text): text=api_text
                    key=hashlib.sha256(row['url'].encode()).hexdigest(); hp=html_dir/f'{key}.html'; tp=text_dir/f'{key}.txt'; jp=html_dir/f'{key}.content.json'
                    if html: hp.write_text(html,encoding='utf8'); entry['html_file']=str(hp.relative_to(folder))
                    if api_json is not None: jp.write_text(json.dumps(api_json,ensure_ascii=False),encoding='utf8'); entry['content_json_file']=str(jp.relative_to(folder))
                    if text: tp.write_text(text,encoding='utf8'); entry['text_file']=str(tp.relative_to(folder)); success+=1
                    else: entry.pop('text_file',None); failed+=1
                    entry.update({'status':status,'attempts':attempts,'content_type':content_type,'captured_at':datetime.now(timezone.utc).isoformat(),'text_chars':len(text),'structure':structure,'elapsed_seconds':round(time.time()-started,2)})
                    entry.pop('error',None)
                except Exception as exc:
                    entry.update({'status':0,'error':f'{type(exc).__name__}: {exc}','captured_at':datetime.now(timezone.utc).isoformat()}); failed+=1
                async with lock:
                    previous=index.get(row['url'],{})
                    if previous.get('text_file') and not entry.get('text_file'):
                        entry={**entry,'text_file':previous['text_file'],'text_chars':previous.get('text_chars',0),'preserved_previous_success':True}
                    index[row['url']]=entry; done+=1
                    # Content files are durable; checkpoint the shared index in worker-sized waves.
                    if done % max(1,min(int(workers),10))==0 or done==len(pending):
                        disk=_load_json_object_resilient(index_path)
                        for saved_url,saved_entry in disk.items():
                            if saved_entry.get('text_file') and not index.get(saved_url,{}).get('text_file'): index[saved_url]=saved_entry
                        _atomic_json_write(index_path,index)
                    checkpoint('running')
                queue.task_done()
        await asyncio.gather(*(worker() for _ in range(min(max(1,int(workers)),50,max(1,len(pending))))))
        await context.close(); await browser.close()
    disk=_load_json_object_resilient(index_path)
    for saved_url,saved_entry in disk.items():
        if saved_entry.get('text_file') and not index.get(saved_url,{}).get('text_file'): index[saved_url]=saved_entry
    _atomic_json_write(index_path,index); checkpoint('cancelled' if cancel_event.is_set() else ('complete_with_failures' if failed else 'complete'))
    return {'total':len(rows),'new':len(pending),'reused':len(rows)-len(pending),'successful_text_pages':success,'failed':failed,'retry_attempts':retries,'cancelled':cancel_event.is_set(),'index_path':str(index_path)}

def run_scrape_pages(bank: str, rows: list[dict], workers=8, progress=None) -> dict:
    """Run one scrape per bank and report absolute progress."""
    import concurrent.futures
    bank_lock=_bank_scrape_lock(bank)
    cancel_event=_bank_cancel_event(bank)
    if not bank_lock.acquire(blocking=False):
        raise RuntimeError(f"A scrape for {bank} is already running. Use Stop active scrape before restarting it.")
    cancel_event.clear()
    def runner():
        loop=asyncio.ProactorEventLoop() if hasattr(asyncio,"ProactorEventLoop") else asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try: return loop.run_until_complete(scrape_pages(bank,rows,workers,None,cancel_event))
        finally:
            try: loop.run_until_complete(loop.shutdown_asyncgens())
            finally: loop.close()
    progress_path=bank_dir(RAW,bank)/"progress.json"; last=None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix="camoufox") as pool:
            future=pool.submit(runner)
            while not future.done():
                current=_load_json_object_resilient(progress_path)
                marker=(current.get("state"),current.get("message"),current.get("completed_total"),current.get("remaining"),current.get("successful_total"),current.get("failed"),current.get("retry_attempts"))
                if progress and marker!=last:
                    accounted=current.get("completed_total",current.get("reused",0)+current.get("completed",0))
                    successful=current.get("successful_total",current.get("reused",0)+current.get("successful_text_pages",0))
                    message=f"{accounted:,}/{current.get('total',0):,} total URLs accounted for ? {current.get('remaining',0):,} still missing ? {successful:,} cached with text ? {current.get('failed',0):,} failed this run ? {current.get('retry_attempts',0):,} retries"
                    prefix=current.get("message","")
                    progress((prefix+" | " if prefix else "")+message); last=marker
                time.sleep(0.75)
            return future.result()
    finally:
        bank_lock.release()

def _load_json_object_resilient(path: Path) -> dict:
    # Older active crawler processes may still truncate index.json while writing.
    # Retry transient empty/partial reads and recover from the atomic temporary copy.
    for candidate in (path,path.with_suffix(path.suffix+'.tmp')):
        for attempt in range(8):
            try:
                raw=candidate.read_text(encoding='utf8')
                if raw.strip():
                    value=json.loads(raw)
                    if isinstance(value,dict): return value
            except (OSError,json.JSONDecodeError): pass
            time.sleep(0.15*(attempt+1))
    return {}

def audit_and_deduplicate_raw(bank: str, urls: set[str]|None=None, minimum_chars=200) -> dict:
    """Quarantine exact duplicate and incomplete text records without deleting raw evidence."""
    folder=bank_dir(RAW,bank); path=folder/'index.json'; index=_load_json_object_resilient(path)
    selected=set(urls) if urls is not None else set(index); hash_owner={}; duplicate=invalid=kept=0; reasons={}
    for url in sorted(selected):
        entry=index.get(url)
        if not entry: continue
        tf=entry.get('text_file'); tp=folder/tf if tf else None; reason=None; digest=None; size=0
        if not tp or not tp.exists(): reason='missing_text_file'
        else:
            text=tp.read_text(encoding='utf8',errors='replace'); normalized=re.sub(r'\s+',' ',text).strip().lower(); size=len(normalized)
            if size<minimum_chars: reason=f'incomplete_under_{minimum_chars}_chars'
            else: digest=hashlib.sha256(normalized.encode('utf8')).hexdigest()
        if not reason and digest in hash_owner: reason='exact_duplicate_text'; entry['duplicate_of']=hash_owner[digest]; duplicate+=1
        elif not reason: hash_owner[digest]=url; kept+=1
        else: invalid+=1
        entry['content_audit_status']='excluded' if reason else 'valid'; entry['content_audit_reason']=reason; entry['normalized_text_hash']=digest; entry['audited_text_chars']=size
        reasons[reason or 'valid']=reasons.get(reason or 'valid',0)+1
    _atomic_json_write(path,index)
    report={'bank':bank,'audited':len(selected),'valid_unique':kept,'exact_duplicates':duplicate,'incomplete_or_missing':invalid,'minimum_chars':minimum_chars,'reasons':reasons,'created_at':datetime.now(timezone.utc).isoformat()}
    _atomic_json_write(folder/'content-audit.json',report); return report

def load_raw_records(bank: str, urls: set[str]|None=None, include_text=True, valid_only=True):
    folder=bank_dir(RAW,bank); path=folder/'index.json'
    if not path.exists() and not path.with_suffix(path.suffix+'.tmp').exists(): return []
    index=_load_json_object_resilient(path); out=[]
    if urls is not None:
        repaired=False
        for url in urls:
            key=hashlib.sha256(url.encode()).hexdigest(); tp=folder/'text'/f'{key}.txt'
            if tp.exists() and tp.stat().st_size>0 and not index.get(url,{}).get('text_file'):
                index.setdefault(url,{})['text_file']=str(tp.relative_to(folder)); index[url]['text_chars']=tp.stat().st_size; repaired=True
        if repaired: _atomic_json_write(path,index)
    for url,item in index.items():
        if urls is not None and url not in urls: continue
        row=dict(item); row['url']=url
        if valid_only and row.get('content_audit_status')=='excluded': continue
        if include_text and row.get('text_file'):
            try: row['text']=(folder/row['text_file']).read_text(encoding='utf8')
            except OSError: row['text']=''
        out.append(row)
    return sorted(out,key=lambda x:x['url'])
