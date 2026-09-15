from __future__ import annotations
import base64, hashlib, io, json, os, sqlite3, time, threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag
from urllib.robotparser import RobotFileParser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

ROOT=Path(__file__).parent; DB=ROOT/'data'/'campaigns.db'; REPORTS=ROOT/'reports'; SHOTS=ROOT/'screenshots'; CHROME_PROFILE=ROOT/'data'/'chrome-profile'
load_dotenv(ROOT/'.env')
BROWSER_LOCK=threading.RLock()
BANKS={'BNP Paribas Fortis':['https://www.bnpparibasfortis.be/fr/public/particuliers','https://newsroom.bnpparibasfortis.be/fr'],'Revolut':['https://www.revolut.com/','https://www.revolut.com/news/'],'ING':['https://www.ing.be/','https://newsroom.ing.be/fr']}
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36 ING-Market-Signal-POC/0.2'

def session():
 s=requests.Session(); retry=Retry(total=1,connect=1,read=1,backoff_factor=0.5,status_forcelist=[429,500,502,503,504],allowed_methods=['GET'])
 s.mount('https://',HTTPAdapter(max_retries=retry)); s.headers.update({'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8,fr;q=0.6,nl;q=0.5'}); return s

def init_db():
 DB.parent.mkdir(exist_ok=True); REPORTS.mkdir(exist_ok=True); SHOTS.mkdir(exist_ok=True)
 with sqlite3.connect(DB) as c: c.executescript('''CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,bank TEXT,url TEXT,captured_at TEXT,content_hash TEXT,text TEXT); CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY,bank TEXT,created_at TEXT,result TEXT); CREATE TABLE IF NOT EXISTS comparisons(id INTEGER PRIMARY KEY,created_at TEXT,result TEXT);''')

def allowed(url):
 p=urlparse(url); robots=f'{p.scheme}://{p.netloc}/robots.txt'
 try:
  r=session().get(robots,timeout=(5,12))
  if r.status_code in (401,403): return False,'robots.txt denied access'
  if r.status_code>=400: return True,f'robots.txt unavailable ({r.status_code}); public page only'
  rp=RobotFileParser(); rp.set_url(robots); rp.parse(r.text.splitlines()); return rp.can_fetch(UA,url),'robots.txt checked'
 except requests.RequestException as e: return True,f'robots.txt could not be checked ({type(e).__name__}); public page only'

def clean_html(html,base_url):
 s=BeautifulSoup(html,'html.parser'); links=[]
 for a in s.select('a[href]'):
  u=urldefrag(urljoin(base_url,a.get('href')))[0]
  if u.startswith(('http://','https://')): links.append(u)
 for x in s(['script','style','svg','noscript']): x.decompose()
 return (' '.join(s.get_text(' ',strip=True).split())[:40000],s.title.string.strip() if s.title and s.title.string else '',list(dict.fromkeys(links)))

def browser_scrape(url,shot_path):
 with BROWSER_LOCK:
  return _browser_scrape_locked(url,shot_path)

def _browser_scrape_locked(url,shot_path):
 try:
  from playwright.sync_api import sync_playwright
 except ImportError: raise RuntimeError('Browser collector unavailable. Run setup_windows.bat once.')
 CHROME_PROFILE.mkdir(parents=True,exist_ok=True)
 with sync_playwright() as p:
  options=dict(user_data_dir=str(CHROME_PROFILE),channel='chrome',headless=True,viewport={'width':1440,'height':1000},locale='fr-BE',timezone_id='Europe/Brussels',extra_http_headers={'Accept-Language':'fr-BE,fr;q=0.9,nl-BE;q=0.8,en;q=0.6'},args=['--disable-blink-features=AutomationControlled'])
  try: context=p.chromium.launch_persistent_context(**options)
  except Exception as e: raise RuntimeError(f'Installed Google Chrome could not be launched. Install Chrome and close any Market Signal Chrome window, then retry. {e}')
  page=context.pages[0] if context.pages else context.new_page(); page.goto(url,wait_until='domcontentloaded',timeout=60000)
  try: page.wait_for_load_state('networkidle',timeout=10000)
  except Exception: pass
  for label in ['Refuser les cookies optionnels','Les cookies essentiels','Continuer sans accepter','Reject optional cookies','Only necessary cookies','Alleen noodzakelijke cookies']:
   try: page.get_by_role('button',name=label).click(timeout=1500); break
   except Exception: pass
  page.wait_for_timeout(1800)
  for _ in range(8):
   page.mouse.wheel(0,900); page.wait_for_timeout(300)
  page.evaluate('window.scrollTo(0,0)'); page.wait_for_timeout(500); page.screenshot(path=str(shot_path),full_page=True,type='jpeg',quality=78)
  title=page.title(); text=' '.join(page.locator('body').inner_text(timeout=15000).split())[:60000]; final=page.url; links=page.eval_on_selector_all('a[href]',"els => els.map(a => a.href)"); structured=page.eval_on_selector_all('main, article, section, [role=main], table, [class*=card], [class*=price]',"els => els.map(e => e.innerText).filter(Boolean).join(String.fromCharCode(10)+'---BLOCK---'+String.fromCharCode(10))"); text=(text+'\n'+structured)[:90000]; context.close()
  return text,title,final,list(dict.fromkeys(links))

def scrape(url,bank,force_browser=False):
 permitted,note=allowed(url)
 if not permitted: return {'requested_url':url,'url':url,'error':'Blocked by robots.txt','collector':'none','robots':note}
 stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'); slug=hashlib.sha1(url.encode()).hexdigest()[:8]; shot=SHOTS/f'{stamp}-{bank.lower().replace(" ","-")}-{slug}.jpg'; errors=[]
 if not force_browser:
  try:
   r=session().get(url,timeout=(10,30)); r.raise_for_status(); text,title,links=clean_html(r.text,r.url)
   if len(text)>=300: return {'requested_url':url,'url':r.url,'title':title,'text':text,'links':links,'collector':'HTTP','robots':note}
   errors.append('HTTP returned too little visible text')
  except requests.RequestException as e: errors.append(f'HTTP: {type(e).__name__}: {e}')
 try:
  text,title,final,links=browser_scrape(url,shot); lower=(title+' '+text[:2000]).lower()
  maintenance=any(x in lower for x in ['maintenance','temporarily unavailable','momentanÃ©ment indisponible','tijdelijk niet beschikbaar'])
  return {'requested_url':url,'url':final,'title':title,'text':text,'links':links,'collector':'Installed Google Chrome (persistent project profile)','screenshot':str(shot),'robots':note,'page_state':'maintenance' if maintenance else 'normal','fallback_reason':'; '.join(errors)}
 except Exception as e: return {'requested_url':url,'url':url,'error':'; '.join(errors+[f'Browser: {type(e).__name__}: {e}']),'collector':'failed','robots':note}

def image_part(path):
 try:
  im=Image.open(path).convert('RGB'); im.thumbnail((1280,3000)); buf=io.BytesIO(); im.save(buf,'JPEG',quality=70,optimize=True)
  return {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()}}
 except Exception: return None

def client(settings=None):
 settings=settings or {}; return OpenAI(api_key=settings.get('key') or os.getenv('NAVY_API_KEY'),base_url=settings.get('base') or os.getenv('NAVY_BASE_URL'),timeout=120,max_retries=0)
def parse_json(s):
 if not isinstance(s,str) or not s.strip(): raise ValueError('The model returned an empty response instead of JSON.')
 s=s.strip().replace('```json','').replace('```','').strip(); start=s.find('{'); end=s.rfind('}')
 if start<0 or end<start: raise ValueError('The model response contained no JSON object.')
 return json.loads(s[start:end+1])
def relevant_link(url,host):
 p=urlparse(url); path=p.path.lower()
 if p.netloc.lower()!=host or any(x in path for x in ['/login','/secure','/privacy','/legal','/cookie','/jobs','/contact']): return False
 keys=['particul','personal','retail','product','produit','banking','account','compte','rekening','pack','plan','saving','epargn','sparen','loan','credit','hypoth','mortgage','card','carte','kaart','invest','insurance','assurance','verzekering']
 return path in ('','/') or any(k in path for k in keys)

def analyze_bank(bank,urls=None,settings=None,visual=True,progress=None,max_pages=8):
 init_db(); seeds=urls or BANKS[bank]; pages=[]; seen=set(); queue=list(seeds); seed_results={u:False for u in seeds}
 host=urlparse(seeds[0]).netloc.lower()
 while queue and len(pages)<max_pages:
  u=queue.pop(0)
  if u in seen: continue
  seen.add(u)
  if progress: progress(f'Exploring page {len(pages)+1}/{max_pages}: {u}')
  page=scrape(u,bank,force_browser=visual); pages.append(page)
  if page.get('text') and page.get('page_state')!='maintenance':
   for seed in seeds:
    if u==seed: seed_results[seed]=True
   now=datetime.now(timezone.utc).isoformat(); h=hashlib.sha256(page['text'].encode()).hexdigest()
   with sqlite3.connect(DB) as c: c.execute('INSERT INTO snapshots(bank,url,captured_at,content_hash,text) VALUES(?,?,?,?,?)',(bank,page['url'],now,h,page['text']))
   candidates=[x for x in page.get('links',[]) if relevant_link(x,host) and x not in seen]
   queue.extend(candidates[:30])
 successful=[p for p in pages if p.get('text') and p.get('page_state')!='maintenance']
 consumer=[p for p in successful if relevant_link(p.get('url',''),host)]
 if not successful: raise RuntimeError(f'Analysis stopped: no page was collected for {bank}. No report was saved.')
 if not any(seed_results.values()): raise RuntimeError(f'Analysis stopped: none of the requested starting pages was collected for {bank}. No report was saved.')
 if progress: progress(f'Collected {len(successful)} pages; sending evidence to the AI modelâ€¦')
 prompt=(ROOT/'prompts'/'bank_analysis.md').read_text(encoding='utf8').replace('{bank}',bank)
 coverage={'requested_seeds':seeds,'seed_success':seed_results,'pages_attempted':len(pages),'pages_collected':len(successful),'consumer_or_product_pages':len(consumer),'complete':all(seed_results.values())}
 payload=[{k:v for k,v in page.items() if k!='links'} for page in pages]
 content=[{'type':'text','text':json.dumps({'coverage':coverage,'pages':payload},ensure_ascii=False)}]
 if visual:
  for p in successful:
   if p.get('screenshot'):
    part=image_part(p['screenshot'])
    if part: content.append(part)
 response=client(settings).chat.completions.create(model=(settings or {}).get('model') or os.getenv('NAVY_MODEL','gpt-5.6-luna'),messages=[{'role':'system','content':prompt},{'role':'user','content':content}],response_format={'type':'json_object'})
 result=parse_json(response.choices[0].message.content); result['_coverage']=coverage; result['_collection']=[{k:p.get(k) for k in ('requested_url','url','collector','screenshot','robots','page_state','error','fallback_reason') if p.get(k)} for p in pages]; now=datetime.now(timezone.utc).isoformat()
 with sqlite3.connect(DB) as c: c.execute('INSERT INTO analyses(bank,created_at,result) VALUES(?,?,?)',(bank,now,json.dumps(result)))
 (REPORTS/f'{now[:10]}-{bank.lower().replace(" ","-")}.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8'); return result

def latest_analyses():
 init_db(); out={}
 with sqlite3.connect(DB) as c:
  for bank,result in c.execute('SELECT bank,result FROM analyses ORDER BY id DESC'):
   if bank not in out: out[bank]=json.loads(result)
 return out
def compare(settings=None):
 summaries=latest_analyses()
 if len(summaries)<2: raise ValueError('Run at least two independent bank analyses first.')
 prompt=(ROOT/'prompts'/'comparison.md').read_text(encoding='utf8'); response=client(settings).chat.completions.create(model=(settings or {}).get('model') or os.getenv('NAVY_MODEL','gpt-5.6-luna'),messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(summaries,ensure_ascii=False)}],response_format={'type':'json_object'}); result=parse_json(response.choices[0].message.content); now=datetime.now(timezone.utc).isoformat()
 with sqlite3.connect(DB) as c: c.execute('INSERT INTO comparisons(created_at,result) VALUES(?,?)',(now,json.dumps(result)))
 (REPORTS/f'{now[:10]}-comparison.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8'); return result
def timeline(bank):
 init_db()
 with sqlite3.connect(DB) as c: return c.execute('SELECT captured_at,url,content_hash FROM snapshots WHERE bank=? ORDER BY captured_at DESC',(bank,)).fetchall()
def latest_comparison():
 init_db()
 with sqlite3.connect(DB) as c: row=c.execute('SELECT result FROM comparisons ORDER BY id DESC LIMIT 1').fetchone()
 return json.loads(row[0]) if row else None
def chat(question,settings=None):
 context={'analyses':latest_analyses(),'comparison':latest_comparison()}; response=client(settings).chat.completions.create(model=(settings or {}).get('model') or os.getenv('NAVY_MODEL','gpt-5.6-luna'),messages=[{'role':'system','content':'Answer as a concise competitive intelligence analyst. Use only supplied evidence, cite source URLs, and say when evidence is missing.'},{'role':'user','content':json.dumps(context,ensure_ascii=False)+'\nQUESTION: '+question}]); return response.choices[0].message.content



def save_analysis(bank,result,pages=None):
 init_db(); now=datetime.now(timezone.utc).isoformat()
 for page in pages or []:
  if page.get('text'):
   h=hashlib.sha256(page['text'].encode()).hexdigest()
   with sqlite3.connect(DB) as c: c.execute('INSERT INTO snapshots(bank,url,captured_at,content_hash,text) VALUES(?,?,?,?,?)',(bank,page.get('url',''),now,h,page['text']))
 with sqlite3.connect(DB) as c: c.execute('INSERT INTO analyses(bank,created_at,result) VALUES(?,?,?)',(bank,now,json.dumps(result)))
 (REPORTS/f'{now[:10]}-{bank.lower().replace(" ","-")}.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
 return result

