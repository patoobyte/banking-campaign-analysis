from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from ai import provider_settings, read_prompt
from demo_backend import (DEMO_BANKS,COMMUNICATION_DIMENSIONS,METRIC_LABELS,QUANTITATIVE_METRIC_LABELS,load_demo_urls,save_demo_urls,capture_status,run_demo_capture,stop_demo_capture,refresh_quantitative_html_metrics,load_demo_records,run_demo_coding,comparison_profile,radar_chart,metric_chart,demo_chat)

def _records(): return load_demo_records()
def _campaign_label(row): return f"{row.get('campaign_id')} - {row.get('campaign',{}).get('name') or row.get('url')}"
def _campaign_export(records,scope,banks):
    selected=[r for r in records if r.get('communication_scores') and r.get('bank') in set(banks)]
    return selected,json.dumps({'schema_version':'demo-v1','bank_scope':scope,'records':selected},ensure_ascii=False,indent=2)

def render_demo_builder():
    st.title('Demo dataset builder')
    st.caption('Curated presentation scope only: editable URLs -> rendered Camoufox capture -> full-page screenshot -> deterministic metrics. No sitemap or eligibility scan.')
    data=load_demo_urls(); bank=st.selectbox('Bank',list(DEMO_BANKS),key='demo_capture_bank'); urls=data['banks'].get(bank,[])
    text=st.text_area('Curated URLs - one URL per line',value='\n'.join(urls),height=250,key=f'demo_urls_{bank}',help='These pages are already campaign/product pages. Saving changes only the isolated demo scope.')
    c1,c2=st.columns(2)
    if c1.button('Save curated URL list',use_container_width=True):
        try: saved=save_demo_urls(bank,text); st.success(f'Saved {len(saved):,} {bank} URLs.')
        except Exception as exc: st.error(str(exc))
    if c2.button('Stop capture safely',use_container_width=True): stop_demo_capture(); st.warning('Stop requested. Current page will finish and completed captures remain cached.')
    if st.button('Refresh quantitative HTML metrics from cached pages',use_container_width=True,help='Re-runs the team HTML extractor adapter against cached HTML. No browser or AI calls are made.'):
        result=refresh_quantitative_html_metrics([bank]); st.success(f"Updated {result['updated']:,} captured pages with {result['extractor_version']}. Missing HTML: {result['missing_html']:,}.")
    status=capture_status(bank,urls); a,b,c,d=st.columns(4); a.metric('Curated URLs',status['total']); b.metric('Captured',status['captured']); c.metric('With screenshot',status['screenshots']); d.metric('Remaining',status['remaining'])
    if data.get('import_warnings'):
        with st.expander('Imported URL corrections and warnings'): st.write(data['import_warnings'])
    visible=st.checkbox('Show Camoufox browser while capturing',value=True,help='Recommended for N26 and other visual/protection-sensitive pages. Scripts and images remain enabled.')
    if st.button('Capture missing demo pages and screenshots',type='primary',use_container_width=True,disabled=not urls):
        panel=st.status(f'Capturing {bank} demo pages...',expanded=True); line=panel.empty()
        try:
            result=run_demo_capture(bank,urls,visible,line.write); panel.update(label=f"Capture complete: {result['new']:,} processed, {result['reused']:,} reused, {result['failed']:,} failed.",state='complete',expanded=True)
        except Exception as exc: panel.update(label='Demo capture failed',state='error',expanded=True); line.error(f'{type(exc).__name__}: {exc}')
    records=[r for r in _records() if r.get('bank')==bank]
    if records:
        st.subheader('Captured evidence')
        table=[{'campaign':r.get('campaign_id'),'URL':r.get('url'),'text characters':r.get('metrics',{}).get('text_characters'),'images':r.get('metrics',{}).get('image_count'),'visible images':r.get('metrics',{}).get('visible_image_count'),'screenshot':bool(r.get('screenshot_file')),'capture error':r.get('capture_error')} for r in records]
        st.dataframe(pd.DataFrame(table),use_container_width=True,hide_index=True)
        selected=st.selectbox('Preview captured campaign',records,format_func=_campaign_label,index=None)
        if selected:
            left,right=st.columns([2,1]); left.write(selected.get('url')); left.json(selected.get('metrics',{})); shot=Path(selected.get('screenshot_path') or selected.get('screenshot_file',''))
            if shot.exists(): right.image(str(shot),caption=selected.get('campaign_id'))
            st.markdown('#### Deterministic rendered/screenshot metrics'); st.json(selected.get('deterministic_metrics',{}))
            st.markdown('#### Team quantitative HTML metrics'); st.caption(f"Extractor: {selected.get('quantitative_extractor_version','unknown')}"); st.json(selected.get('quantitative_html_metrics',{}))
            if selected.get('visual_assessment'):
                st.markdown('#### AI screenshot-based visual assessment'); st.json(selected.get('visual_assessment',{}))

def render_demo_run():
    st.title('Demo campaign coding')
    st.caption('Choose one bank or all captured banks. Each curated page is one screenshot-backed AI call; existing results from other banks remain preserved in the shared demo JSON.')
    all_records=_records(); scope=st.selectbox('Bank to code',['BNP Paribas Fortis','ING','N26','All captured banks'])
    selected_banks=list(DEMO_BANKS) if scope=='All captured banks' else [scope]
    records=[r for r in all_records if r.get('bank') in selected_banks]
    captured=[r for r in records if r.get('text_file') and r.get('screenshot_file') and not r.get('capture_error')]
    coded=[r for r in records if r.get('communication_scores')]; errors=[r for r in records if r.get('error') and not r.get('communication_scores')]
    a,b,c=st.columns(3); a.metric('Ready to code',len(captured)); b.metric('Coded',len(coded)); c.metric('Coding errors',len(errors))
    st.caption(f"Active model: {provider_settings()['model']}")
    instruction=st.text_area('Optional demo coding instruction',value=read_prompt('demo_boss_default.md'),height=100)
    col1,col2=st.columns(2); calls=col1.slider('Concurrent AI calls',1,20,5); spacing=col2.slider('Seconds between starts',0.0,5.0,0.5,0.1)
    retry=st.checkbox('Retry only records with coding errors',value=False)
    if not captured: st.info(f'No captured pages are ready for {scope}. Capture this bank first in DEMO - Dataset builder.')
    if st.button('Build or resume selected demo campaign dataset',type='primary',use_container_width=True,disabled=not captured):
        panel=st.status(f'Coding {scope} demo campaigns from text and screenshots...',expanded=True); line=panel.empty()
        try:
            result=run_demo_coding(selected_banks,line.write,calls,spacing,instruction,retry); panel.update(label=f"{scope} coding complete: {result['successful']:,} successful; {result['failed']:,} failed. Other banks were preserved.",state='complete',expanded=True)
        except Exception as exc: panel.update(label='Demo coding failed',state='error',expanded=True); line.error(f'{type(exc).__name__}: {exc}')
    all_records=_records(); all_coded=[r for r in all_records if r.get('communication_scores')]
    scoped_coded,scoped_payload=_campaign_export(all_records,scope,selected_banks)
    if scoped_coded:
        st.subheader(f'{scope} presentation dataset')
        st.caption('The table and first export follow the selected bank scope. Every JSON record retains all captured, quantitative, visual, and AI-coded fields.')
        st.dataframe(pd.DataFrame([{'campaign':r['campaign_id'],'bank':r['bank'],'name':r.get('campaign',{}).get('name'),'product':r.get('campaign',{}).get('product_family'),'evidence quality':r.get('evidence_quality',{}).get('rating')} for r in scoped_coded]),use_container_width=True,hide_index=True)
        scope_slug='all-banks' if scope=='All captured banks' else scope.lower().replace(' ','-')
        st.download_button(f'Download {scope} campaign JSON',scoped_payload,f'demo-campaigns-{scope_slug}.json','application/json',use_container_width=True)
    elif all_coded:
        st.info(f'No coded campaigns are available for {scope} yet.')
    if all_coded and scope!='All captured banks':
        combined_payload=json.dumps({'schema_version':'demo-v1','bank_scope':'All captured banks','records':all_coded},ensure_ascii=False,indent=2)
        st.download_button('Download all banks combined campaign JSON',combined_payload,'demo-campaigns-all-banks.json','application/json',use_container_width=True)

def render_demo_overview():
    st.title('Overview demo')
    st.caption('Compare one campaign, several campaigns, or whole-bank averages. Communication radar axes all share the same 1-5 scale; page metrics use separate charts.')
    records=[r for r in _records() if r.get('communication_scores')]
    if not records: st.info('Capture and code demo campaigns first.'); return
    mode=st.radio('Comparison level',['Individual campaigns','Whole banks'],horizontal=True)
    if mode=='Individual campaigns':
        options={_campaign_label(r):r for r in records}; left,right=st.columns(2)
        a=left.selectbox('Left campaign',list(options),index=0); b=right.selectbox('Right campaign',list(options),index=min(1,len(options)-1))
        profiles={a:comparison_profile([options[a]]),b:comparison_profile([options[b]])}
        influenced=None
    else:
        banks=sorted({r['bank'] for r in records}); left,right=st.columns(2); a=left.selectbox('Left bank',banks,index=0); b=right.selectbox('Right bank',banks,index=min(1,len(banks)-1))
        profiles={a:comparison_profile([r for r in records if r['bank']==a]),b:comparison_profile([r for r in records if r['bank']==b])}; influenced=True
    path=radar_chart(profiles,'Communication profile - positional scales (not quality)',influenced)
    st.image(str(path),use_container_width=True)
    st.caption('All radar dimensions use the same 1-5 communication scale. A larger polygon does not mean a better campaign.')
    with st.expander('Score evidence'):
        for label,profile in profiles.items():
            st.subheader(label); st.dataframe(pd.DataFrame([{'dimension':d,'score':profile['scores'].get(d),'evidence':'; '.join(profile['evidence'].get(d,[])[:3])} for d in COMMUNICATION_DIMENSIONS]),use_container_width=True,hide_index=True)
    st.subheader('Numerical page, screenshot, and team HTML metrics')
    metric_options=list(METRIC_LABELS)+[f'quantitative.{key}' for key in QUANTITATIVE_METRIC_LABELS]
    metric_labels={**METRIC_LABELS,**{f'quantitative.{key}':label for key,label in QUANTITATIVE_METRIC_LABELS.items()}}
    metrics=st.multiselect('Metrics to chart',metric_options,default=['text_characters','visible_image_count','text_image_ratio'],format_func=lambda x:metric_labels[x],help='Team quantitative HTML fields and collector metrics can be compared here. AI screenshot judgments remain separate in each campaign record.')
    chart_type=st.radio('Metric chart type',['Bar','Box'],horizontal=True)
    selected_records=[]
    if mode=='Individual campaigns': selected_records=[options[a],options[b]]
    else: selected_records=[r for r in records if r['bank'] in (a,b)]
    if metrics:
        metric_path=metric_chart(selected_records,metrics,chart_type.lower()); st.image(str(metric_path),use_container_width=True)

def render_demo_chat():
    st.title('AI chatbot demo')
    st.caption('Ask concise presentation or Q&A questions using only selected curated demo campaigns.')
    records=[r for r in _records() if r.get('communication_scores')]
    if not records: st.info('Code the demo dataset first.'); return
    banks=sorted({r['bank'] for r in records}); selected_banks=st.multiselect('Banks',banks,default=banks)
    available=[r for r in records if r['bank'] in selected_banks]; labels={_campaign_label(r):r for r in available}; selected=st.multiselect('Campaigns (empty means all selected banks)',list(labels))
    context=[labels[x] for x in selected] if selected else available
    st.metric('Campaigns in context',len(context))
    key='demo_chat_messages'; st.session_state.setdefault(key,[])
    if st.button('Reset conversation'): st.session_state[key]=[]; st.rerun()
    for message in st.session_state[key]:
        with st.chat_message(message['role']): st.markdown(message['content'])
    with st.form('demo_chat_form',clear_on_submit=True):
        question=st.text_area('Question',placeholder='What are the clearest differences between traditional-bank and online-bank account communication?'); ask=st.form_submit_button('Ask AI',type='primary',use_container_width=True)
    if ask and question.strip():
        st.session_state[key].append({'role':'user','content':question.strip()})
        with st.spinner('Analysing selected demo campaigns...'):
            try: answer=demo_chat(st.session_state[key],context); st.session_state[key].append({'role':'assistant','content':answer}); st.rerun()
            except Exception as exc: st.error(f'{type(exc).__name__}: {exc}')
