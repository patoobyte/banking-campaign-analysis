from __future__ import annotations
import json, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import matplotlib.pyplot as plt
from config import RUNS, GRAPHS
from ai import client, provider_settings, _wait_request_slot, json_call, read_prompt

BANK_CODES={'ING':'ING','BNP Paribas Fortis':'BNP','Revolut':'REV'}

def run_label(path: Path):
    try: bank=json.loads(path.read_text(encoding='utf8')).get('bank') or path.parent.name
    except Exception: bank=path.parent.name
    return f"{BANK_CODES.get(bank,bank.upper()[:3])} · {path.name}"

def load_runs(paths):
    output=[]
    for raw in paths:
        path=Path(raw); data=json.loads(path.read_text(encoding='utf8'))
        for record in data.get('records',[]):
            if record.get('features'):
                output.append({'bank':data.get('bank',path.parent.name),'run':path.name,'source_url':record.get('source_url'),'features':record['features']})
    return output

LANGUAGE_ALIASES={'fr':'French','french':'French','fran?ais':'French','francais':'French','nl':'Dutch','dutch':'Dutch','nederlands':'Dutch','en':'English','english':'English'}
def canonical_language(value): return LANGUAGE_ALIASES.get(str(value).strip().lower(),str(value).strip())
def available_languages(records): return sorted({canonical_language(row['features'].get('Language','')) for row in records if row['features'].get('Language')})

def scalar_values(value):
    if isinstance(value,list): return [str(x) for x in value if x not in (None,'')]
    if isinstance(value,dict): return [json.dumps(value,ensure_ascii=False,sort_keys=True)]
    return [] if value in (None,'') else [str(value)]

def feature_names(records): return sorted({key for row in records for key in row['features']})

def unique_values(records,feature):
    return sorted({value for row in records for value in scalar_values(row['features'].get(feature))},key=str.lower)

def filter_records(records,languages=None,filters=None,include_all=False):
    if not include_all and not filters: return []
    languages={str(x).lower() for x in (languages or [])}; filters=filters or {}; out=[]
    for row in records:
        lang=canonical_language(row['features'].get('Language','')).lower()
        if languages and lang not in languages: continue
        if all(set(scalar_values(row['features'].get(feature))) & set(values) for feature,values in filters.items() if values): out.append(row)
    return out

def context_json(records,max_chars=1600000):
    payload=json.dumps(records,ensure_ascii=False,separators=(',',':'))
    if len(payload)>max_chars: raise ValueError(f'Selected context is about {len(payload)//4:,} tokens. Add filters or select fewer runs (limit about {max_chars//4:,} estimated tokens).')
    return payload

def _extract_graph_directive(answer: str):
    match=re.search(r'<graphs>\s*(\{.*?\})\s*</graphs>',answer,re.S)
    if not match: return answer.strip(),[]
    visible=(answer[:match.start()]+answer[match.end():]).strip()
    try: specs=json.loads(match.group(1)).get('charts',[])[:3]
    except (json.JSONDecodeError,AttributeError): specs=[]
    return visible,specs

def create_graph(records,feature,chart_type='bar',title='',group_by=None):
    available=set(feature_names(records))|{'Bank','Run'}
    if feature not in available: raise ValueError(f'Unknown graph feature: {feature}')
    if group_by and group_by not in available: raise ValueError(f'Unknown group feature: {group_by}')
    def get_values(row,name):
        if name=='Bank': return [row['bank']]
        if name=='Run': return [row['run']]
        return scalar_values(row['features'].get(name))
    pairs=[]
    for row in records:
        values=get_values(row,feature)
        groups=get_values(row,group_by) if group_by else ['All selected records']
        for value in values:
            for group in groups: pairs.append((str(group),str(value)))
    if not pairs: raise ValueError(f'No values exist for {feature} in the selected context.')
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f'); safe=re.sub(r'[^a-zA-Z0-9-]+','-',feature).strip('-').lower(); path=GRAPHS/f'{stamp}-{safe}.png'
    plt.style.use('dark_background'); fig,ax=plt.subplots(figsize=(12,7)); chart_type=str(chart_type).lower()
    if chart_type=='pie' and not group_by:
        counts=Counter(value for _,value in pairs); common=counts.most_common(12); ax.pie([n for _,n in common],labels=[x for x,_ in common],autopct='%1.0f%%'); ax.axis('equal')
    elif group_by:
        groups=sorted({g for g,_ in pairs}); totals=Counter(v for _,v in pairs); categories=[v for v,_ in totals.most_common(15)]
        width=0.8/max(1,len(groups)); positions=list(range(len(categories)))
        for offset,group in enumerate(groups):
            counts=Counter(v for g,v in pairs if g==group); xs=[x-0.4+width/2+offset*width for x in positions]; ax.bar(xs,[counts[c] for c in categories],width,label=group)
        ax.set_xticks(positions,labels=categories,rotation=35,ha='right'); ax.legend(title=group_by); ax.set_ylabel('Campaign records')
    else:
        counts=Counter(value for _,value in pairs); common=counts.most_common(20); ax.barh([x for x,_ in common][::-1],[n for _,n in common][::-1],color='#ff6b22'); ax.set_xlabel('Campaign records')
    ax.set_title(title or f'{feature} (n={len(records)})'); fig.tight_layout(); fig.savefig(path,dpi=160,bbox_inches='tight'); plt.close(fig)
    meta={'feature':feature,'group_by':group_by,'chart_type':chart_type,'records':len(records),'created_at':datetime.now(timezone.utc).isoformat()}; path.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf8'); return path

def chat_answer(messages,records,instruction=''):
    settings=provider_settings(); context=context_json(records)
    system=read_prompt('analyst_chat_system.md',{'ADDITIONAL_INSTRUCTION':instruction.strip() or 'None.','CONTEXT_JSON':context})
    request=[{'role':'system','content':system}]+[{k:v for k,v in message.items() if k in ('role','content')} for message in messages[-20:]]
    _wait_request_slot(); response=client().chat.completions.create(model=settings['model'],messages=request)
    visible,specs=_extract_graph_directive(response.choices[0].message.content or '')
    graphs=[]; graph_errors=[]
    for spec in specs:
        if not isinstance(spec,dict): continue
        try:
            graphs.append(str(create_graph(records,str(spec.get('feature','')),spec.get('chart_type','bar'),str(spec.get('title','')),spec.get('group_by'))))
        except Exception as exc: graph_errors.append(str(exc))
    if graph_errors: visible+='\n\n_Graph note: '+'; '.join(graph_errors)+'_'
    return visible,graphs

def suggest_normalisation(records,feature,instruction=''):
    values=unique_values(records,feature)
    system=read_prompt('normalisation_suggestions_system.md',{'BOSS_INSTRUCTION':instruction.strip() or 'None.'})
    result=json_call(system,{'feature':feature,'unique_values':values},retries=6)
    return [(str(x.get('old','')),str(x.get('new',''))) for x in result.get('replacements',[]) if x.get('old') and x.get('new')]

def normalised_path(source: Path):
    base=source.stem; candidate=source.with_name(base+'_normalised.json'); number=1
    while candidate.exists(): candidate=source.with_name(f'{base}_normalised({number}).json'); number+=1
    return candidate

def mass_replace(source: Path,replacements: list[tuple[str,str]],instructions=''):
    """Replace exact complete categorical values only; never substring-replace prose or URLs."""
    data=json.loads(source.read_text(encoding='utf8')); changed=0; replacement_map={old:new for old,new in replacements if old}
    for record in data.get('records',[]):
        features=record.get('features')
        if not isinstance(features,dict): continue
        for key,value in list(features.items()):
            if 'url' in key.lower(): continue
            def replace_value(item):
                nonlocal changed
                if isinstance(item,list): return [replace_value(x) for x in item]
                if isinstance(item,dict): return {k:replace_value(v) for k,v in item.items()}
                if isinstance(item,str) and item in replacement_map:
                    changed+=1; return replacement_map[item]
                return item
            features[key]=replace_value(value)
    data['normalisation']={'source_file':source.name,'matching':'exact whole value','instructions':instructions,'replacements':replacements,'changed_values':changed,'created_at':datetime.now(timezone.utc).isoformat()}
    path=normalised_path(source); path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8'); return path,changed

