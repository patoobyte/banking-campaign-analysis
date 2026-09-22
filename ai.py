from __future__ import annotations
import json, os, re, time, random, threading
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError, InternalServerError
from dotenv import load_dotenv
from config import ROOT, PROMPTS, AUDIENCES
load_dotenv(ROOT/'.env', override=True)

_RATE_LOCK=threading.Lock()
_NEXT_REQUEST_AT=0.0
_REQUEST_SPACING_SECONDS=0.0

def configure_ai_pacing(seconds: float):
    global _REQUEST_SPACING_SECONDS
    _REQUEST_SPACING_SECONDS=max(0.0,min(5.0,float(seconds)))

def _wait_request_slot():
    global _NEXT_REQUEST_AT
    with _RATE_LOCK:
        now=time.monotonic(); wait=max(0.0,_NEXT_REQUEST_AT-now)
        _NEXT_REQUEST_AT=max(now,_NEXT_REQUEST_AT)+_REQUEST_SPACING_SECONDS
    if wait: time.sleep(wait)


def read_prompt(name: str, replacements: dict|None=None) -> str:
    """Read an editable prompt from disk on every use; Streamlit restart is unnecessary."""
    path=PROMPTS/name
    if not path.exists(): raise FileNotFoundError(f'Missing prompt file: {path}')
    text=path.read_text(encoding='utf8').strip()
    for key,value in (replacements or {}).items(): text=text.replace('{{'+key+'}}',str(value))
    unresolved=re.findall(r'{{[A-Z0-9_]+}}',text)
    if unresolved: raise ValueError(f'Unresolved prompt placeholders in {name}: {sorted(set(unresolved))}')
    return text

def provider_settings():
    # Streamlit does not restart when .env changes. Reload it before every request.
    load_dotenv(ROOT/'.env',override=True)
    return {'api_key':os.getenv('NAVY_API_KEY'),'base_url':os.getenv('NAVY_BASE_URL','https://api.navy/v1'),'model':os.getenv('NAVY_MODEL','gpt-5.6-luna').strip()}

def client():
    settings=provider_settings(); return OpenAI(api_key=settings['api_key'],base_url=settings['base_url'],timeout=120,max_retries=0)

def provider_preflight(timeout=90):
    """Fail visibly before scheduling hundreds of batches if the provider is unreachable."""
    started=time.time()
    settings=provider_settings(); probe=OpenAI(api_key=settings['api_key'],base_url=settings['base_url'],timeout=timeout,max_retries=0)
    try:
        response=probe.chat.completions.create(model=settings['model'],messages=[{'role':'user','content':read_prompt('provider_preflight_user.md')}],max_tokens=8)
        return {'ok':True,'seconds':round(time.time()-started,2),'response':response.choices[0].message.content,'model':settings['model']}
    except Exception as exc:
        raise RuntimeError(f'Provider preflight failed after {round(time.time()-started,1)}s: {type(exc).__name__}: {exc}') from exc

def parse_json(text: str):
    text=text.replace('```json','').replace('```','').strip(); decoder=json.JSONDecoder()
    for i,c in enumerate(text):
        if c in '[{':
            try: return decoder.raw_decode(text[i:])[0]
            except json.JSONDecodeError: pass
    raise ValueError('Model returned invalid JSON.')

def json_call(system: str, payload, retries=6):
    messages=[{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
    last_error=None
    for attempt in range(retries+1):
        try:
            _wait_request_slot()
            settings=provider_settings()
            response=client().chat.completions.create(model=settings['model'],messages=messages,response_format={'type':'json_object'})
            try: return parse_json(response.choices[0].message.content or '')
            except ValueError as exc:
                last_error=exc
                if attempt==retries: raise
                messages.append({'role':'user','content':read_prompt('json_repair_user.md')})
                time.sleep(min(20,2**attempt)+random.random())
        except (RateLimitError,APITimeoutError,APIConnectionError,InternalServerError) as exc:
            last_error=exc
            if attempt==retries: raise
            # Handles burst limits, transient provider errors, connection failures, and timeouts.
            time.sleep(min(90,3*(2**attempt))+random.random()*2)
    raise last_error or RuntimeError('AI request failed.')

def classify_cleaning_batch(bank: str, pages: list[dict], custom_instruction=""):
    system=read_prompt('dataset_cleaning_system.md',{'BANK':bank,'AUDIENCES':', '.join(AUDIENCES),'BOSS_INSTRUCTION':custom_instruction.strip() or 'None.'})
    payload={'pages':[{'url':p['url'],'language':p.get('language'),'title':p.get('title'),'text':p.get('text','')[:24000]} for p in pages]}
    result=json_call(system,payload); return result.get('records',[])

def classify_campaign(bank: str, page: dict, feature_definitions: str, custom_instruction=""):
    system=read_prompt('campaign_coding_system.md',{'BOSS_INSTRUCTION':custom_instruction.strip() or 'None.'})
    payload={'feature_definitions':feature_definitions,'supplied_metadata':{k:page.get(k) for k in ['bank','url','capture_date','language','channel','viewport_dimensions','signature_color','audience_categories']},'page_structure':page.get('structure',{}),'cleaned_visible_text':page.get('text','')[:70000]}
    return json_call(system,payload)

