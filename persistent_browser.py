from __future__ import annotations
import hashlib, queue, threading
from datetime import datetime, timezone
from urllib.parse import urlparse
import backend

class PersistentBrowser:
 """Persistent Chrome whose Playwright objects live exclusively on one worker thread."""
 def __init__(self,bank,allowed_hosts,headless=True):
  self.bank=bank; self.allowed_hosts=set(allowed_hosts); self.headless=headless
  self.jobs=queue.Queue(); self.thread=None; self.ready=threading.Event(); self.start_error=None; self.captures=[]; self.current_url=''
 def start(self):
  if self.thread and self.thread.is_alive(): return self
  self.thread=threading.Thread(target=self._worker,name='market-signal-browser',daemon=True); self.thread.start(); self.ready.wait(45)
  if self.start_error: raise RuntimeError(f'Chrome start failed: {self.start_error}')
  if not self.ready.is_set(): raise RuntimeError('Chrome worker did not start within 45 seconds.')
  return self
 def _worker(self):
  pw=context=page=None
  try:
   from playwright.sync_api import sync_playwright
   backend.CHROME_PROFILE.mkdir(parents=True,exist_ok=True); pw=sync_playwright().start()
   context=pw.chromium.launch_persistent_context(user_data_dir=str(backend.CHROME_PROFILE),channel='chrome',headless=self.headless,viewport={'width':1440,'height':1000},locale='fr-BE',timezone_id='Europe/Brussels',extra_http_headers={'Accept-Language':'fr-BE,fr;q=0.9,nl-BE;q=0.8,en;q=0.6'},args=['--disable-blink-features=AutomationControlled'])
   page=context.pages[0] if context.pages else context.new_page(); self.ready.set()
   while True:
    job=self.jobs.get()
    if job is None: break
    method,args,kwargs,result=job
    try: result.put((True,getattr(self,'_do_'+method)(page,*args,**kwargs)))
    except BaseException as e: result.put((False,e))
  except BaseException as e:
   self.start_error=e; self.ready.set()
  finally:
   try:
    if context: context.close()
   except Exception: pass
   try:
    if pw: pw.stop()
   except Exception: pass
 def _call(self,method,*args,**kwargs):
  if not self.thread or not self.thread.is_alive(): raise RuntimeError('Browser worker is not running.')
  result=queue.Queue(maxsize=1); self.jobs.put((method,args,kwargs,result)); ok,value=result.get(timeout=120)
  if not ok: raise value
  if isinstance(value,dict) and value.get('url'): self.current_url=value['url']
  return value
 def close(self):
  if self.thread and self.thread.is_alive(): self.jobs.put(None); self.thread.join(timeout=20)
 def guard(self,url):
  host=urlparse(url).netloc.lower()
  if host not in self.allowed_hosts: raise ValueError(f'Domain not allowed: {host}. Allowed: {sorted(self.allowed_hosts)}')
  ok,note=backend.allowed(url)
  if not ok: raise ValueError(f'Blocked by robots.txt: {url}')
  return note
 def navigate(self,url):
  note=self.guard(url); data=self._call('navigate',url); data['robots']=note; return data
 def click(self,text): return self._call('click',text)
 def back(self): return self._call('back')
 def scroll(self,direction='down',amount=900): return self._call('scroll',direction,amount)
 def snapshot(self,requested=None): return self._call('snapshot',requested)
 def _dismiss(self,page):
  for label in ['Refuser les cookies optionnels','Les cookies essentiels','Continuer sans accepter','Reject optional cookies','Only necessary cookies','Alleen noodzakelijke cookies','Accepter tout','Accept all']:
   try: page.get_by_role('button',name=label,exact=True).click(timeout=900); return label
   except Exception: pass
 def _do_navigate(self,page,url):
  page.goto(url,wait_until='domcontentloaded',timeout=60000)
  try: page.wait_for_load_state('networkidle',timeout=8000)
  except Exception: pass
  self._dismiss(page); return self._do_snapshot(page,url)
 def _do_click(self,page,text):
  last=None; before=page.url
  candidates=[page.get_by_role('button',name=text,exact=False),page.get_by_role('link',name=text,exact=False),page.get_by_text(text,exact=False),page.locator('a,button,[role=button],[role=tab]').filter(has_text=text)]
  for loc in candidates:
   try:
    if loc.count()<1: continue
    target=loc.first; target.scroll_into_view_if_needed(timeout=2500); target.click(timeout=5000); page.wait_for_timeout(1200); self._dismiss(page); data=self._do_snapshot(page); data['interaction']={'action':'click','text':text,'success':True,'previous_url':before}; return data
   except Exception as e: last=e
  # If text corresponds to a known link, direct navigation is a safe equivalent.
  try:
   matches=page.eval_on_selector_all('a[href]',"(els,q)=>els.map(a=>({t:(a.innerText||a.getAttribute('aria-label')||'').trim(),u:a.href})).filter(x=>x.t.toLowerCase().includes(q.toLowerCase()))",text)
   if matches:
    page.goto(matches[0]['u'],wait_until='domcontentloaded',timeout=60000); data=self._do_snapshot(page); data['interaction']={'action':'link_fallback','text':text,'success':True,'previous_url':before}; return data
  except Exception as e: last=e
  # Failed interaction is evidence, not a fatal browser error.
  data=self._do_snapshot(page); data['interaction']={'action':'click','text':text,'success':False,'error':str(last),'current_url':page.url}; return data
 def _do_back(self,page): page.go_back(wait_until='domcontentloaded',timeout=30000); return self._do_snapshot(page)
 def _do_scroll(self,page,direction,amount): page.mouse.wheel(0,abs(amount) if direction=='down' else -abs(amount)); page.wait_for_timeout(500); return self._do_snapshot(page)
 def _do_snapshot(self,page,requested=None):
  page.wait_for_timeout(400); title=page.title(); url=page.url
  try: text=' '.join(page.locator('body').inner_text(timeout=10000).split())[:90000]
  except Exception: text=''
  links=page.eval_on_selector_all('a[href]',"els=>els.map(a=>({text:(a.innerText||a.getAttribute('aria-label')||'').trim(),url:a.href})).filter(x=>x.url)")
  controls=page.eval_on_selector_all('a,button,input,select,[role=button],[role=tab]',"els=>els.slice(0,250).map((e,i)=>({index:i,tag:e.tagName,role:e.getAttribute('role'),text:(e.innerText||e.getAttribute('aria-label')||e.getAttribute('placeholder')||'').trim().slice(0,180),href:e.href||null}))")
  stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'); slug=hashlib.sha1((url+stamp).encode()).hexdigest()[:8]; shot=backend.SHOTS/f'{stamp}-{self.bank.lower().replace(" ","-")}-{slug}.jpg'; page.screenshot(path=str(shot),full_page=True,type='jpeg',quality=78)
  state='maintenance' if any(x in (title+' '+text[:2000]).lower() for x in ['maintenance','temporarily unavailable','momentanément indisponible','tijdelijk niet beschikbaar']) else 'normal'
  data={'requested_url':requested or url,'url':url,'title':title,'text':text,'links':[x['url'] for x in links],'link_map':links[:180],'controls':controls,'screenshot':str(shot),'collector':'Persistent installed Google Chrome (dedicated worker)','page_state':state}; self.captures.append(data); return data
