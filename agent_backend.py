from __future__ import annotations
import json, os, traceback
from pathlib import Path
from urllib.parse import urlparse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import backend
from persistent_browser import PersistentBrowser

ROOT=Path(__file__).parent
class AgentRequest(BaseModel):
 bank:str; seed_urls:list[str]; max_steps:int=30; max_pages:int=15; visual:bool=True

class ResearchSession:
 def __init__(self,req,progress=None):
  self.req=req; self.progress=progress; self.steps=0; self.pages={}; self.allowed_hosts={urlparse(x).netloc.lower() for x in req.seed_urls}; self.browser=PersistentBrowser(req.bank,self.allowed_hosts)
 def guard_step(self):
  if self.steps>=self.req.max_steps: raise ValueError('Tool-step budget exhausted')
  self.steps+=1
 def store(self,page):
  self.pages[page['url']]=page
  return json.dumps({'url':page.get('url'),'title':page.get('title'),'page_state':page.get('page_state'),'screenshot':page.get('screenshot'),'links':page.get('link_map',[])[:120],'controls':page.get('controls',[])[:150],'visible_text':page.get('text','')[:22000]},ensure_ascii=False)
 def tools(self):
  s=self
  @tool
  def navigate(url:str,reason:str='Research')->str:
   '''Navigate the persistent Chrome tab to an allowed public URL and return text, links, controls and screenshot path.'''
   s.guard_step()
   if len(s.pages)>=s.req.max_pages and url not in s.pages: return 'Page budget exhausted.'
   return s.store(s.browser.navigate(url))
  @tool
  def click_visible(text:str,reason:str='Interact')->str:
   '''Click a visible link, button, tab, accordion or menu by accessible text. A failed click returns current controls and does not end research.'''
   try:
    s.guard_step(); page=s.browser.click(text); result=json.loads(s.store(page)); result['interaction']=page.get('interaction'); result['guidance']='If success is false, inspect controls/links, navigate by discovered URL, or continue with another route.'; return json.dumps(result,ensure_ascii=False)
   except Exception as e: return json.dumps({'interaction':{'action':'click','text':text,'success':False,'error':f'{type(e).__name__}: {e}'},'guidance':'Do not stop. Inspect current page or navigate using a discovered URL.'},ensure_ascii=False)
  @tool
  def scroll_page(direction:str='down',amount:int=900)->str:
   '''Scroll the current page while preserving browser state, then return updated evidence.'''
   s.guard_step(); return s.store(s.browser.scroll(direction,amount))
  @tool
  def go_back()->str:
   '''Go back in the same persistent browser tab.'''
   s.guard_step(); return s.store(s.browser.back())
  @tool
  def inspect_current()->str:
   '''Return current page text, links, accessible controls and a fresh screenshot.'''
   s.guard_step(); return s.store(s.browser.snapshot())
  @tool
  def readiness()->str:
   '''Audit collected evidence for prices and core retail categories.'''
   s.guard_step(); text=' '.join(p.get('text','').lower() for p in s.pages.values())
   checks={k:any(x in text for x in v) for k,v in {'pricing':['€','eur','par mois','tarif','fee'],'accounts':['compte','account','pack'],'savings':['épargn','saving'],'cards':['carte','card'],'loans':['crédit','loan','hypoth'],'insurance':['assur','insurance'],'investing':['invest','placer']}.items()}
   return json.dumps({'pages':len(s.pages),'checks':checks,'current_url':s.browser.page.url})
  return [navigate,click_visible,scroll_page,go_back,inspect_current,readiness]

def run_agentic_bank(req:AgentRequest,settings=None,progress=None):
 session=ResearchSession(req,progress); settings=settings or {}; api_key=settings.get('key') or os.getenv('NAVY_API_KEY'); base=settings.get('base') or os.getenv('NAVY_BASE_URL'); model=settings.get('model') or os.getenv('NAVY_MODEL','gpt-5.6-luna'); prompt=(ROOT/'prompts'/'bank_analysis.md').read_text(encoding='utf8').replace('{bank}',req.bank)
 try:
  session.browser.start(); tools=session.tools()
  for seed in req.seed_urls:
   try: tools[0].invoke({'url':seed,'reason':'Required seed'})
   except Exception: pass
  llm=ChatOpenAI(model=model,api_key=api_key,base_url=base,temperature=0,timeout=120,max_retries=1)
  agent=create_react_agent(llm,tools)
  mission=f'''Investigate {req.bank} in the already-open persistent Chrome session. Seeds: {req.seed_urls}. A failed tool interaction is recoverable and must never end the investigation. Use navigate for discovered URLs and click_visible for menus, tabs, accordions, cookie controls, comparison widgets and JavaScript navigation. Scroll when content is lazy. Inspect accounts/packs, prices/fees, cards, savings, loans, investments, insurance, account-opening journey, language and visual design. Screenshots are reliable evidence. Allowed hosts: {sorted(session.allowed_hosts)}. Budgets: {req.max_pages} pages, {req.max_steps} tool steps. Call readiness before finishing.'''
  agent.invoke({'messages':[SystemMessage(content=prompt),HumanMessage(content=mission)]},{'recursion_limit':req.max_steps+12})
  pages=list(session.pages.values()); usable=[p for p in pages if p.get('page_state')!='maintenance' and (p.get('text') or p.get('screenshot'))]
  if not usable: raise RuntimeError('Persistent browser collected no usable evidence.')
  evidence=[{k:v for k,v in p.items() if k not in ('links','link_map','controls','screenshot','text')}|{'visible_text':p.get('text','')[:45000]} for p in usable]
  content=[{'type':'text','text':'Create the required JSON profile from all evidence. Screenshots are observed evidence; transcribe visible prices/products/CTAs.\n'+json.dumps(evidence,ensure_ascii=False)[:170000]}]
  if req.visual:
   for p in usable:
    if p.get('screenshot'):
     content.append({'type':'text','text':'Screenshot for '+p['url']}); part=backend.image_part(p['screenshot'])
     if part: content.append(part)
  response=backend.client(settings).chat.completions.create(model=model,messages=[{'role':'system','content':prompt+'\nReturn JSON only.'},{'role':'user','content':content}],response_format={'type':'json_object'},timeout=240)
  raw=response.choices[0].message.content or ''; (ROOT/'last_agent_final.txt').write_text(raw,encoding='utf8'); profile=backend.parse_json(raw)
  profile['_coverage']={'requested_seeds':req.seed_urls,'pages_collected':len(usable),'screenshot_pages':sum(bool(p.get('screenshot')) for p in usable),'agent_tool_steps':session.steps,'persistent_session':True,'allowed_hosts':sorted(session.allowed_hosts)}
  profile['_collection']=[{k:p.get(k) for k in ('requested_url','url','title','collector','screenshot','page_state','robots','error') if p.get(k)} for p in pages]
  return backend.save_analysis(req.bank,profile,[p for p in usable if p.get('text')])
 except Exception as e:
  (ROOT/'agent_error.log').write_text(traceback.format_exc(),encoding='utf8'); raise RuntimeError(f'Persistent agent failed: {type(e).__name__}: {e}. See agent_error.log') from e
 finally:
  session.browser.close()
