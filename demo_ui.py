from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from ai import provider_settings, read_prompt
from demo_visual_schema import VISUAL_SCHEMA_VERSION, VISUAL_CATEGORIES, PROFILE_TAGS, valid_label
from demo_backend import (DEMO_BANKS,COMMUNICATION_DIMENSIONS,METRIC_LABELS,QUANTITATIVE_METRIC_LABELS,load_demo_urls,parse_demo_urls,save_demo_urls,capture_status,run_demo_capture,stop_demo_capture,refresh_quantitative_html_metrics,load_demo_records,run_demo_coding,comparison_profile,radar_chart,metric_chart,category_chart,demo_chat)

def _records(): return load_demo_records()
def _campaign_label(row): return f"{row.get('campaign_id')} - {row.get('campaign',{}).get('name') or row.get('url')}"
def _campaign_export(records,scope,banks):
    selected=[r for r in records if r.get('communication_scores') and r.get('bank') in set(banks)]
    return selected,json.dumps({'schema_version':'demo-v1','bank_scope':scope,'records':selected},ensure_ascii=False,indent=2)

def _csv_value(value):
    return json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else value

def _campaign_csv(records,scope,banks):
    selected,_=_campaign_export(records,scope,banks); rows=[]
    metric_fields=['text_characters','word_count','sentence_count','mean_sentence_words','paragraph_count','heading_count','image_count','visible_image_count','button_count','link_count','page_width','page_height','viewport_width','viewport_height','text_image_ratio','screenshot_width','screenshot_height','screenshot_aspect_ratio','screenshot_brightness','screenshot_contrast','screenshot_warmth','screenshot_colourfulness']
    quantitative_fields=['word_count','heading_count','paragraph_count','list_count','list_item_count','average_list_length','sentence_count','average_paragraph_length','average_sentence_length','primary_headline_length','has_table','cta_count','price_mention_count','date_mention_count','question_count','link_count','text_volume','paragraph_length_category']
    campaign_fields=['language','communication_format','name','product_family','target_audience','objective','offer','primary_cta','summary']
    visual_fields=list(VISUAL_CATEGORIES)
    for record in selected:
        source_url=record.get('source_url') or record.get('url'); campaign=record.get('campaign',{}); metrics=record.get('deterministic_metrics') or record.get('metrics',{}); quantitative=record.get('quantitative_html_metrics',{}); visual=record.get('visual_assessment',{})
        row={'schema_version':'demo-v1','bank_scope':scope,'campaign_id':record.get('campaign_id'),'bank':record.get('bank'),'source_url':source_url,'url':record.get('url') or source_url,'title':record.get('title'),'status':record.get('status'),'capture_date':record.get('capture_date'),'captured_at':record.get('captured_at'),'html_file':record.get('html_file'),'text_file':record.get('text_file'),'screenshot_file':record.get('screenshot_file'),'screenshot_path':record.get('screenshot_path') or record.get('screenshot_file'),'campaign_bank':record.get('bank'),'campaign_source_url':source_url,'campaign_capture_date':record.get('capture_date')}
        row.update({f'campaign_{field}':_csv_value(campaign.get(field)) for field in campaign_fields})
        row.update({f'metrics_{field}':metrics.get(field) for field in metric_fields})
        row.update({f'quantitative_{field}':quantitative.get(field) for field in quantitative_fields})
        row['quantitative_extractor_version']=record.get('quantitative_extractor_version') or quantitative.get('extractor_version')
        row['visual_schema_version']=record.get('visual_schema_version')
        for dimension in COMMUNICATION_DIMENSIONS:
            key=dimension.lower().replace(' ','_'); item=record.get('communication_scores',{}).get(dimension,{})
            row[f'{key}_score']=item.get('score'); row[f'{key}_justification']=item.get('justification'); row[f'{key}_evidence_quote']=item.get('evidence_quote')
        for field in visual_fields:
            value=visual.get(field); row[f'visual_{field}']=valid_label(value,VISUAL_CATEGORIES[field]) if record.get('visual_schema_version')==VISUAL_SCHEMA_VERSION else None
            row[f'visual_{field}_evidence']=visual.get(f'{field}_evidence') or (value if isinstance(value,str) and row[f'visual_{field}'] is None else None)
        row['visual_evidence']=_csv_value(visual.get('evidence'))
        traits=record.get('dominant_characteristics') or []
        row['dominant_characteristics']=_csv_value(traits) if record.get('visual_schema_version')==VISUAL_SCHEMA_VERSION and isinstance(traits,list) and all(valid_label(x,PROFILE_TAGS) for x in traits) else None
        row['dominant_characteristics_evidence']=_csv_value(record.get('dominant_characteristics_evidence') or (traits if traits else None))
        profile=record.get('overall_communication_profile'); row['overall_communication_profile']=valid_label(profile,PROFILE_TAGS) if record.get('visual_schema_version')==VISUAL_SCHEMA_VERSION else None
        row['overall_communication_profile_evidence']=record.get('overall_communication_profile_evidence') or (profile if isinstance(profile,str) and row['overall_communication_profile'] is None else None)
        row['evidence_quality_rating']=valid_label(record.get('evidence_quality',{}).get('rating'),('High','Medium','Low'))
        row['evidence_quality_explanation']=record.get('evidence_quality',{}).get('explanation'); rows.append(row)
    return selected,pd.DataFrame(rows).to_csv(index=False)

def render_demo_builder():
    st.title('Demo dataset builder')
    st.caption('Curated presentation scope only: editable URLs -> rendered Camoufox capture -> full-page screenshot -> deterministic metrics. No sitemap or eligibility scan.')
    data=load_demo_urls(); bank=st.selectbox('Bank',list(DEMO_BANKS),key='demo_capture_bank'); urls=data['banks'].get(bank,[])
    if st.button('Reload saved URL list into editor',key=f'demo_reload_{bank}',help='Replace unsaved draft edits with the latest saved list.'):
        st.session_state[f'demo_urls_{bank}']='\n'.join(urls)
    text=st.text_area('Curated URLs - one URL per line',value='\n'.join(urls),height=250,key=f'demo_urls_{bank}',help='The draft is previewed below. Capture saves it automatically. URLs for another supported bank are added to that bank, never filed under the selected bank. The source .txt files are not changed.')
    try:
        grouped=parse_demo_urls(bank,text)
    except ValueError as exc:
        grouped=None; st.error(str(exc))
    missing_saved=[url for url in urls if grouped is not None and url not in grouped[bank]]
    allow_removal=False
    if missing_saved:
        st.warning(f'{len(missing_saved)} saved {bank} URL(s) are absent from this draft. Reload to include externally added URLs, or explicitly confirm removal before saving/capturing.')
        allow_removal=st.checkbox('Confirm removing saved URLs from this bank list',value=False)
    can_save=grouped is not None and (not missing_saved or allow_removal)
    if grouped is not None:
        draft_banks={other: (grouped[other] if other==bank else list(dict.fromkeys(data['banks'][other]+grouped[other]))) for other in grouped}
        if any(other!=bank for other in draft_banks):
            st.info('URLs for another bank were detected. Saving will add them to the correct bank; capturing this draft will capture missing pages for both banks.')
        for other,proposed in draft_banks.items():
            stat=capture_status(other,proposed)
            label='Selected bank draft' if other==bank else 'Also routed to this bank'
            st.caption(f"{label}: {other} - {stat['total']} URLs, {stat['remaining']} needing capture (text and screenshot).")
        status=capture_status(bank,draft_banks[bank])
    else:
        status=capture_status(bank,urls)
    c1,c2=st.columns(2)
    if c1.button('Save curated URL list',use_container_width=True,disabled=not can_save):
        try:
            saved=save_demo_urls(bank,text)
            st.success(f'Saved {len(saved):,} {bank} URLs.' + (f' Other bank URLs were added to their own lists.' if len(grouped)>1 else ''))
        except Exception as exc: st.error(str(exc))
    if c2.button('Stop capture safely',use_container_width=True): stop_demo_capture(); st.warning('Stop requested. Current page will finish and completed captures remain cached.')
    if st.button('Refresh quantitative HTML metrics from cached pages',use_container_width=True,help='Re-runs the team HTML extractor adapter against cached HTML. No browser or AI calls are made.'):
        result=refresh_quantitative_html_metrics([bank]); st.success(f"Updated {result['updated']:,} captured pages with {result['extractor_version']}. Missing HTML: {result['missing_html']:,}.")
    a,b,c,d=st.columns(4); a.metric('Draft URLs',status['total']); b.metric('Captured text',status['captured']); c.metric('With screenshot',status['screenshots']); d.metric('Still need capture',status['remaining'])
    if data.get('import_warnings'):
        with st.expander('Imported URL corrections and warnings'): st.write(data['import_warnings'])
    visible=st.checkbox('Show Camoufox browser while capturing',value=True,help='Recommended for N26 and other visual/protection-sensitive pages. Scripts and images remain enabled.')
    if st.button('Save draft and capture missing pages',type='primary',use_container_width=True,disabled=not can_save or not any(grouped.values() if grouped else [])):
        try:
            # Save before opening the browser so new URLs remain resumable even if capture fails.
            save_demo_urls(bank,text)
            for other in draft_banks:
                current=load_demo_urls()['banks'][other]
                if other!=bank and not grouped[other]: continue
                panel=st.status(f'Capturing missing {other} demo pages...',expanded=True); line=panel.empty()
                try:
                    result=run_demo_capture(other,current,visible,line.write)
                    remaining=capture_status(other,current)['remaining']
                    state='complete' if not remaining and not result['cancelled'] else 'error'
                    panel.update(label=f"{other}: {result['new']} processed, {result['reused']} reused, {result['failed']} failed; {remaining} still need capture.",state=state,expanded=True)
                    if result['cancelled']: break
                except Exception as exc:
                    panel.update(label=f'{other} capture failed',state='error',expanded=True)
                    line.error(f'{type(exc).__name__}: {exc}')
                    break
            st.caption('Capture status refreshes on the next rerun. New captured pages are eligible for DEMO - Campaign run.')
        except Exception as exc: st.error(f'{type(exc).__name__}: {exc}')
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
    coded=[r for r in records if r.get('communication_scores')]; errors=[r for r in records if r.get('error') or r.get('recode_error')]
    a,b,c=st.columns(3); a.metric('Ready to code',len(captured)); b.metric('Coded',len(coded)); c.metric('Coding/recode errors',len(errors))
    st.caption(f"Active model: {provider_settings()['model']}")
    instruction=st.text_area('Optional demo coding instruction',value=read_prompt('demo_boss_default.md'),height=100)
    col1,col2=st.columns(2); calls=col1.slider('Concurrent AI calls',1,20,5); spacing=col2.slider('Seconds between starts',0.0,5.0,0.5,0.1)
    retry=st.checkbox('Retry records with coding errors',value=True)
    recode=st.checkbox('Recode all captured campaigns in the selected scope with the current prompt',value=False,help='Needed to turn earlier prose-only visual values into short graphable categories with separate evidence. Uses cached URL-specific screenshots and makes a new paid AI request for each selected page. Other banks remain preserved.')
    legacy=sum(r.get('visual_schema_version')!=VISUAL_SCHEMA_VERSION for r in coded)
    if legacy: st.info(f'{legacy} coded campaign(s) in this scope still have older prose-only visual values. Enable recoding to get graphable labels. CSV retains that prose in evidence columns but leaves their old category cells empty.')
    if not captured: st.info(f'No captured pages are ready for {scope}. Capture this bank first in DEMO - Dataset builder.')
    if st.button('Build or resume selected demo campaign dataset',type='primary',use_container_width=True,disabled=not captured):
        panel=st.status(f'Coding {scope} demo campaigns from text and screenshots...',expanded=True); line=panel.empty()
        try:
            result=run_demo_coding(selected_banks,line.write,calls,spacing,instruction,retry,recode); panel.update(label=f"{scope} coding complete: {result['successful']:,} successful; {result['failed']:,} failed. Other banks were preserved.",state='complete',expanded=True)
        except Exception as exc: panel.update(label='Demo coding failed',state='error',expanded=True); line.error(f'{type(exc).__name__}: {exc}')
    all_records=_records(); all_coded=[r for r in all_records if r.get('communication_scores')]
    scoped_coded,scoped_payload=_campaign_export(all_records,scope,selected_banks)
    if scoped_coded:
        st.subheader(f'{scope} presentation dataset')
        st.caption('The table and first export follow the selected bank scope. Legacy prose remains intact in JSON; CSV keeps its explanation in evidence columns and leaves non-graphable legacy category cells empty until recoded.')
        st.dataframe(pd.DataFrame([{'campaign':r['campaign_id'],'bank':r['bank'],'name':r.get('campaign',{}).get('name'),'product':r.get('campaign',{}).get('product_family'),'evidence quality':r.get('evidence_quality',{}).get('rating')} for r in scoped_coded]),use_container_width=True,hide_index=True)
        scope_slug='all-banks' if scope=='All captured banks' else scope.lower().replace(' ','-')
        scoped_csv_records,scoped_csv=_campaign_csv(all_records,scope,selected_banks)
        export_json,export_csv=st.columns(2)
        export_json.download_button(f'Download {scope} JSON',scoped_payload,f'demo-campaigns-{scope_slug}.json','application/json',use_container_width=True)
        export_csv.download_button(f'Download {scope} CSV',scoped_csv,f'demo-campaigns-{scope_slug}.csv','text/csv',use_container_width=True)
    elif all_coded:
        st.info(f'No coded campaigns are available for {scope} yet.')
    if all_coded and scope!='All captured banks':
        combined_payload=json.dumps({'schema_version':'demo-v1','bank_scope':'All captured banks','records':all_coded},ensure_ascii=False,indent=2)
        _,combined_csv=_campaign_csv(all_records,'All captured banks',list(DEMO_BANKS))
        combined_json_col,combined_csv_col=st.columns(2)
        combined_json_col.download_button('Download all banks JSON',combined_payload,'demo-campaigns-all-banks.json','application/json',use_container_width=True)
        combined_csv_col.download_button('Download all banks CSV',combined_csv,'demo-campaigns-all-banks.csv','text/csv',use_container_width=True)

def _overview_chart_label(side, name, bank=None):
    """Use identifiable names on the chart without overflowing its legend."""
    if bank:
        name=f"{DEMO_BANKS[bank]['code']}: {name}"
    return f"{side}: {name[:31] + '...' if len(name)>34 else name}"

def render_demo_overview():
    st.title('Overview demo')
    st.caption('Compare individual campaigns or whole banks. Communication scores use a 1-5 radar; categorical labels show presence or bank prevalence; numeric metrics use separate scales.')
    records=[r for r in _records() if r.get('communication_scores')]
    if not records: st.info('Capture and code demo campaigns first.'); return
    mode=st.radio('Comparison level',['Individual campaigns','Whole banks'],horizontal=True)
    if mode=='Individual campaigns':
        options={_campaign_label(r):r for r in records}; left,right=st.columns(2)
        a=left.selectbox('Left campaign',list(options),index=0)
        b=right.selectbox('Right campaign',list(options),index=min(1,len(options)-1))
        selections=[(_overview_chart_label('Left',options[a].get('campaign',{}).get('name') or options[a]['campaign_id'],options[a]['bank']),[options[a]]),(_overview_chart_label('Right',options[b].get('campaign',{}).get('name') or options[b]['campaign_id'],options[b]['bank']),[options[b]])]
        st.caption(f'Orange = Left: {a}   |   Green = Right: {b}')
    else:
        banks=sorted({r['bank'] for r in records}); left,right=st.columns(2)
        a=left.selectbox('Left bank',banks,index=0)
        b=right.selectbox('Right bank',banks,index=min(1,len(banks)-1))
        selections=[(_overview_chart_label('Left',a),[r for r in records if r['bank']==a]),(_overview_chart_label('Right',b),[r for r in records if r['bank']==b])]
        st.caption(f'Orange = Left: {a} ({len(selections[0][1])} campaigns)   |   Green = Right: {b} ({len(selections[1][1])} campaigns)')
    if a==b: st.info('Choose different selections for a meaningful comparison.')
    profiles={label:comparison_profile(group) for label,group in selections}
    path=radar_chart(profiles,'Communication profile - positional scales (not quality)',mode=='Whole banks')
    st.image(str(path),width=700)
    st.caption('All radar dimensions use the same 1-5 communication scale. A larger polygon does not mean a better campaign.')
    with st.expander('Score evidence'):
        for label,profile in profiles.items():
            st.subheader(label); st.dataframe(pd.DataFrame([{'dimension':d,'score':profile['scores'].get(d),'evidence':'; '.join(profile['evidence'].get(d,[])[:3])} for d in COMMUNICATION_DIMENSIONS]),use_container_width=True,hide_index=True)
    st.subheader('Numerical page, screenshot, and team HTML metrics')
    metric_options=list(METRIC_LABELS)+[f'quantitative.{key}' for key in QUANTITATIVE_METRIC_LABELS]
    metric_labels={**METRIC_LABELS,**{f'quantitative.{key}':label for key,label in QUANTITATIVE_METRIC_LABELS.items()}}
    metrics=st.multiselect('Metrics to chart (up to 3)',metric_options,default=['text_characters','visible_image_count'],max_selections=3,format_func=lambda x:metric_labels[x],help='Each numeric measure gets its own axis. Pick up to three for a compact comparison; HTML metrics and collector metrics remain separate.')
    chart_type=st.radio('Metric chart type',['Bar','Box'],horizontal=True)
    st.caption('Each metric uses its own axis. Bar = value/mean per selection; Box = distributions for multi-campaign selections or coloured diamonds for single campaigns. Missing values are not shown as zero.')
    selected_records=[record for _,group in selections for record in group]
    if metrics:
        metric_path=metric_chart(selected_records,metrics,chart_type.lower(),selections=selections)
        st.image(str(metric_path),width=760)
    st.subheader('Categorical comparisons')
    category_options=list(VISUAL_CATEGORIES)+['overall_communication_profile','dominant_characteristics','evidence_quality_rating']
    category_field=st.selectbox('Classification to compare',category_options,index=category_options.index('evidence_quality_rating'),format_func=lambda value:value.replace('_',' ').capitalize())
    graph_rows=[]; contributing=set(); eligible={}
    for selection,group in selections:
        eligible[selection]=0
        for record in group:
            if category_field!='evidence_quality_rating' and record.get('visual_schema_version')!=VISUAL_SCHEMA_VERSION:
                continue
            if category_field in VISUAL_CATEGORIES:
                label=valid_label((record.get('visual_assessment') or {}).get(category_field),VISUAL_CATEGORIES[category_field])
                labels=[label] if label else []
            elif category_field=='dominant_characteristics':
                traits=record.get('dominant_characteristics')
                labels=[tag for tag in traits if valid_label(tag,PROFILE_TAGS)] if isinstance(traits,list) and all(valid_label(tag,PROFILE_TAGS) for tag in traits) else []
            elif category_field=='overall_communication_profile':
                label=valid_label(record.get(category_field),PROFILE_TAGS)
                labels=[label] if label else []
            else:
                label=valid_label((record.get('evidence_quality') or {}).get('rating'),('High','Medium','Low'))
                labels=[label] if label else []
            if labels: eligible[selection]+=1
            for label in labels: graph_rows.append({'Selection':selection,'Category':label})
            if labels: contributing.add((selection,record.get('source_url') or record.get('campaign_id')))
    if graph_rows:
        counts=pd.DataFrame(graph_rows).groupby(['Category','Selection']).size().unstack(fill_value=0)
        counts=counts.reindex(columns=[label for label,_ in selections],fill_value=0)
        top_categories=counts.sum(axis=1).sort_values(ascending=False).head(10).index
        plotted=[row for row in graph_rows if row['Category'] in top_categories]
        category_path=category_chart(plotted,selections,mode=mode,eligible=eligible)
        st.image(str(category_path),width=760)
        interpretation='Yes/No indicates label presence; these are not 1-5 scores.' if mode=='Individual campaigns' else 'Bars show the percentage of eligible coded campaigns within each selected bank (0-100%), not 1-5 scores.'
        st.caption(f'{interpretation} {len(contributing)} selected campaign(s) have graphable categories. Up to 10 most frequent labels shown; legacy prose and missing values excluded.')
        with st.expander('All category counts'):
            st.dataframe(counts,use_container_width=True)
    else: st.info('No graphable categories yet for these campaigns. Recode their cached screenshots in DEMO - Campaign run.')

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
