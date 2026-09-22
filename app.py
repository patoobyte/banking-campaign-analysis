import json, traceback
from pathlib import Path
import pandas as pd
import streamlit as st
from config import BANKS, LANGUAGES, RUNS
from collector import gather_sitemaps, load_inventory, deterministic_filter, run_scrape_pages, load_filter_settings, save_filter_settings, load_raw_records, is_scrape_running, request_scrape_stop, audit_and_deduplicate_raw
from ai import provider_settings, read_prompt
from analysis_workspace import run_label, load_runs, feature_names, unique_values, filter_records, chat_answer, mass_replace, suggest_normalisation, available_languages
from datasets import load_clean, build_clean_dataset, estimate_cleaning_tokens, backups, restore_backup, run_campaign_coding, estimate_campaign_tokens, list_runs, count_cleaning_errors

st.set_page_config(page_title='Campaign Dataset Builder',page_icon='DB',layout='wide')
st.markdown('''<style>
:root{--bg:#17191d;--panel:#22252b;--ink:#eef1f5;--muted:#aeb6c2;--accent:#ff6b22;--line:#3a3f48}
.stApp{background:var(--bg);color:var(--ink)} [data-testid="stSidebar"]{background:#111317;border-right:1px solid var(--line)}
[data-testid="stHeader"]{background:transparent}.block-container{padding-top:2rem}.hero{background:linear-gradient(120deg,#262a31,#33251f);border:1px solid #4a403a;border-radius:16px;padding:26px;margin-bottom:20px}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}.muted{color:var(--muted)}
.stButton button,.stDownloadButton button{border-radius:8px} h1,h2,h3,label,p,li,span{color:var(--ink)} [data-testid="stMetric"]{background:var(--panel);border:1px solid var(--line);padding:12px;border-radius:10px}
[data-baseweb="tag"]{background:#9f2d35!important;color:white!important;border:1px solid #e15b64!important}</style>''',unsafe_allow_html=True)
with st.sidebar:
    st.title('DATASET BUILDER')
    st.caption('Bank campaign communication research')
    page=st.radio('Workspace',['Overview','Dataset builder','Run campaign coding','Dataset normalisation','Chat & graphs'])

if page=='Overview':
    st.markdown('<div class="hero"><h1>Campaign Dataset Builder</h1><p class="muted">Collect once. Clean once. Recode campaigns into versioned analytical datasets.</p></div>',unsafe_allow_html=True)
    cols=st.columns(3)
    for col,bank in zip(cols,BANKS):
        clean=load_clean(bank); eligible=sum(x.get('eligible',False) for x in (clean or {}).get('records',[])); total=len((clean or {}).get('records',[]))
        with col: st.subheader(bank); st.metric('Clean eligible pages',eligible); st.caption(f'{total} AI-reviewed pages')
    runs=list_runs(); st.subheader('Versioned campaign outputs')
    if runs:
        rows=[]
        for path in runs:
            data=json.loads(path.read_text(encoding='utf8')); rows.append({'file':str(path.relative_to(RUNS)),'bank':data.get('bank'),'created_at':data.get('created_at'),'records':len(data.get('records',[])),'successful':sum(not r.get('error') for r in data.get('records',[])),'failed':sum(bool(r.get('error')) for r in data.get('records',[])),'status':data.get('status')})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    else: st.info('No campaign coding runs yet.')

elif page=='Dataset builder':
    st.title('Build a reusable clean bank dataset')
    st.caption(f"Active AI model: {provider_settings()['model']}")
    st.caption('Pipeline: recursive sitemaps → deterministic URL exclusions → Camoufox scrape → AI eligibility and audience coding. Campaign feature coding is separate.')
    bank=st.selectbox('Bank',list(BANKS)); languages=st.multiselect('Languages',list(LANGUAGES),default=['French','Dutch / Flemish','English']); selected=[LANGUAGES[x] for x in languages]
    if bank=='Revolut':
        workers=1
        st.number_input('Camoufox workers (fixed for Revolut)',value=1,disabled=True,help='Revolut protection rejects HTTP-style concurrent downloads. This bank uses one persistent visible rendered browser.')
        st.info('Revolut protection mode: Belgium locales only (en-BE, fr-BE, nl-BE), rendered sequentially in one visible humanized Camoufox browser with scripts and images enabled. Keep its browser window open; complete a challenge manually if one appears.')
    else:
        workers=st.slider("Camoufox workers",1,20,10,help="Concurrent request-context workers for ING and BNP. Temporary blocks trigger shared cooldown and retries.")
    batch_size=st.slider('AI cleaning batch size',1,20,8)
    clean_instruction=st.text_area('Optional cleaning instruction override',value=read_prompt('cleaning_boss_default.md'),height=110,help='Added after prompts/dataset_cleaning_system.md. Edit that prompt file for permanent team-wide rules; this box is a run-specific addition.')
    ai_calls=st.slider('Simultaneous AI API calls',1,50,35); ai_spacing=st.slider('Seconds between new AI request starts',0.0,5.0,0.3,0.1,help='Delay between request starts, not a one-at-a-time mode. Calls overlap up to the selected concurrency. 0.3 seconds starts about 3.3 calls/second while completed calls continuously free worker slots; retries back off automatically.')
    settings=load_filter_settings(bank)
    st.subheader('Bank-specific URL cleaning rules')
    st.caption('One literal URL term per line. Matches complete URL path segments separated by /, - or _. These rules run before scraping and AI.')
    banned_text=st.text_area('Banned URL words or phrases',value='\n'.join(settings['banned_terms']),height=230,key=f'banned_terms_{bank}')
    st.caption('One product-root URL per line. The root product page remains included; every deeper child URL is rejected.')
    roots_text=st.text_area('Reject every child URL below these roots',value='\n'.join(settings['descendant_roots']),height=140,key=f'descendant_roots_{bank}')
    if st.button('Save URL cleaning rules',use_container_width=True):
        settings=save_filter_settings(bank,banned_text.splitlines(),roots_text.splitlines()); st.success(f"Saved {len(settings['banned_terms'])} banned terms and {len(settings['descendant_roots'])} descendant roots for {bank}.")
    else:
        settings={'banned_terms':[x.strip() for x in banned_text.splitlines() if x.strip()],'descendant_roots':[x.strip() for x in roots_text.splitlines() if x.strip()]}
    inventory=load_inventory(bank)
    if st.button('1. Gather recursive sitemaps',type='primary',use_container_width=True):
        status=st.empty()
        try: inventory=gather_sitemaps(bank,BANKS[bank]['seeds'],status.info); status.success(f"Collected {len(inventory['rows']):,} URLs.")
        except Exception as exc: status.error(str(exc))
    if inventory:
        kept,rejected=deterministic_filter(inventory['rows'],selected,bank,settings)
        a,b,c,d=st.columns(4); a.metric('Sitemap URLs',len(inventory['rows'])); b.metric('After code filter',len(kept)); c.metric('Code rejected',len(rejected)); d.metric('Languages',len(selected))
        if bank=='Revolut': st.caption('Only Belgian market routes are retained. Other country routes such as en-AR and en-AU are reported as market_out_of_scope in the URL decisions table.')
        with st.expander('Review deterministic URL decisions'):
            st.dataframe(pd.DataFrame(kept+rejected),use_container_width=True,height=350,hide_index=True)
            st.download_button('Download URL decisions',json.dumps(kept+rejected,ensure_ascii=False,indent=2),f'{bank}-url-decisions.json','application/json')
        scrape_active=is_scrape_running(bank)
        scrape_col,stop_col=st.columns([3,1])
        start_scrape=scrape_col.button('2. Scrape filtered pages with Camoufox',use_container_width=True,disabled=scrape_active)
        if stop_col.button('Stop active scrape',use_container_width=True,disabled=not scrape_active):
            if request_scrape_stop(bank): st.warning(f'Stop requested for {bank}. Workers will finish their current request, save the cache, and stop. Reload in a few seconds to change the worker count.')
            else: st.info('No active scrape was found.')
        if scrape_active: st.info(f'A {bank} scrape is running in the background. Stop it before starting another run or changing its worker count.')
        if start_scrape:
            status=st.status(f'Scraping {len(kept):,} filtered pages with Camoufox. Keep this page open...',expanded=True)
            progress_line=status.empty(); progress_line.write('Camoufox is running in a dedicated browser thread. Previously cached pages will be reused.')
            try:
                result=run_scrape_pages(bank,kept,workers,progress_line.write)
                status.update(label=(f"Scrape stopped safely: cache preserved; {result['successful_text_pages']:,} new text pages saved." if result.get('cancelled') else f"Scrape complete: {result['successful_text_pages']:,} pages with text, {result['failed']:,} failed, {result['reused']:,} reused."),state='complete',expanded=True)
            except Exception as exc:
                message=f'{type(exc).__name__}: {exc!r}'
                status.update(label='Camoufox scrape failed',state='error',expanded=True)
                progress_line.error(message)
                with status.expander('Technical traceback'): st.code(traceback.format_exc())
        audit_col,threshold_col=st.columns([3,1])
        minimum_chars=threshold_col.number_input('Minimum useful text characters',50,2000,200,50)
        if audit_col.button('Audit cache: exclude exact duplicates and incomplete pages',use_container_width=True):
            report=audit_and_deduplicate_raw(bank,{r['url'] for r in kept},minimum_chars)
            st.success(f"Audit complete: {report['valid_unique']:,} unique valid pages; {report['exact_duplicates']:,} exact duplicates; {report['incomplete_or_missing']:,} incomplete or missing. Raw files were preserved.")
        estimate=estimate_cleaning_tokens(bank,kept,batch_size)
        cached_records=load_raw_records(bank,{r['url'] for r in kept},include_text=False)
        cached_with_text=sum(bool(r.get('text_file')) for r in cached_records)
        st.subheader('AI cleaning estimate after scrape')
        e1,e2,e3,e4=st.columns(4); e1.metric('Scraped pages ready',estimate['pages'],help=f'{cached_with_text:,} scoped index records point to saved text files. Successful cache entries survive refreshes and later scrape runs.'); e2.metric('Text characters',f"{estimate['text_characters']:,}"); e3.metric('Estimated tokens',f"{estimate['estimated_total_tokens']:,}"); e4.metric('Estimated batches',estimate['batches'])
        st.caption('Token estimate is approximate: retained text characters ? 4 plus prompt/JSON overhead. Actual provider accounting can differ.')
        rebuild=st.checkbox('Rebuild from scratch. Create ZIP backup of the current clean dataset first.')
        ai_disabled=estimate['pages']==0
        if st.button('3. AI-clean pages and assign target audiences',use_container_width=True,disabled=ai_disabled):
            status=st.status(f"Starting AI cleaning for {estimate['pages']:,} scraped pages in {estimate['batches']:,} batches...",expanded=True)
            progress_line=status.empty()
            try:
                result=build_clean_dataset(bank,kept,batch_size,rebuild,progress_line.write,ai_calls,ai_spacing,clean_instruction)
                eligible=sum(x.get('eligible',False) for x in result['records'])
                status.update(label=f'AI cleaning complete: {eligible:,} eligible of {len(result["records"]):,} reviewed.',state='complete',expanded=True)
            except Exception as exc:
                status.update(label='AI cleaning failed',state='error',expanded=True)
                progress_line.error(f'{type(exc).__name__}: {exc!r}')
                with status.expander('Technical traceback'): st.code(traceback.format_exc())
    clean=load_clean(bank)
    if clean:
        st.subheader('Permanent clean dataset'); records=clean.get('records',[]); eligible=[x for x in records if x.get('eligible')]; clean_errors=count_cleaning_errors(clean)
        a,b,c,d=st.columns(4); a.metric('Reviewed',len(records)); b.metric('Eligible',len(eligible)); c.metric('Excluded by AI',len(records)-len(eligible)-clean_errors); d.metric('AI errors to retry',clean_errors)
        if clean_errors:
            st.warning(f'{clean_errors:,} pages contain an AI error. Successful reviews will be preserved; retry processes only these failed pages and creates a ZIP backup first.')
            if st.button(f'Retry {clean_errors:,} failed AI-cleaning pages',type='primary',use_container_width=True):
                retry_status=st.status(f'Retrying {clean_errors:,} failed cleaning pages...',expanded=True); retry_line=retry_status.empty()
                try:
                    repaired=build_clean_dataset(bank,kept,batch_size,False,retry_line.write,ai_calls,ai_spacing,clean_instruction,retry_failed=True)
                    remaining=count_cleaning_errors(repaired); recovered=clean_errors-remaining
                    retry_status.update(label=f'Retry complete: {recovered:,} recovered; {remaining:,} errors remain.',state='complete' if not remaining else 'error',expanded=True)
                    st.rerun()
                except Exception as exc:
                    retry_status.update(label='Cleaning retry failed',state='error',expanded=True); retry_line.error(f'{type(exc).__name__}: {exc!r}')
                    with retry_status.expander('Technical traceback'): st.code(traceback.format_exc())
        st.dataframe(pd.DataFrame(records),use_container_width=True,height=420,hide_index=True)
        st.download_button('Export clean dataset JSON',json.dumps(clean,ensure_ascii=False,indent=2),f'{bank}-clean-dataset.json','application/json')
    saved=backups(bank)
    if saved:
        st.subheader('Restore backup'); selected_backup=st.selectbox('Backup ZIP',[str(x) for x in saved])
        if st.button('Restore selected backup'):
            restore_backup(bank,selected_backup); st.success('Backup restored. Reloading.'); st.rerun()

elif page=='Run campaign coding':
    st.title('Run versioned campaign feature coding')
    st.caption('This reads the permanent clean dataset. It does not recrawl, rescrape, or modify that dataset. Each run creates a new JSON version.')
    bank=st.selectbox('Bank',list(BANKS)); languages=st.multiselect('Language scope',list(LANGUAGES),default=['French','Dutch / Flemish','English']); selected=[LANGUAGES[x] for x in languages]
    st.caption(f"Active AI model: {provider_settings()['model']}")
    campaign_instruction=st.text_area('Optional campaign-coding instruction override',value=read_prompt('campaign_boss_default.md'),height=110,help='Added after prompts/campaign_coding_system.md. Edit the prompt file for permanent team-wide rules; this box applies only to this run.')
    campaign_calls=st.slider('Simultaneous campaign AI calls',1,50,35,help='Each page is one independent call.'); campaign_spacing=st.slider('Seconds between new campaign request starts',0.0,5.0,0.3,0.1,help='Delay between starts while calls overlap up to the selected concurrency. This prevents a 35-call burst without forcing calls to finish one by one. Retries use automatic backoff.')
    clean=load_clean(bank); eligible=[x for x in (clean or {}).get('records',[]) if x.get('eligible') and (not selected or x.get('language') in selected)]
    st.metric('Eligible pages to code',len(eligible))
    campaign_estimate=estimate_campaign_tokens(bank,selected) if eligible else {'estimated_total_tokens':0}
    st.caption(f"Estimated campaign-coding tokens: {campaign_estimate['estimated_total_tokens']:,}. One eligible page equals one independent model request and one final dataset record.")
    if eligible: st.dataframe(pd.DataFrame(eligible),use_container_width=True,height=320,hide_index=True)
    else: st.warning('No eligible clean pages in this scope. Build the clean dataset first.')
    if st.button('Create next campaign-XX.json',type='primary',disabled=not eligible,use_container_width=True):
        status=st.status(f'Preparing one-page campaign coding for {len(eligible):,} pages...',expanded=True); progress_line=status.empty()
        try:
            path,result=run_campaign_coding(bank,selected,progress_line.write,campaign_calls,campaign_spacing,custom_instruction=campaign_instruction)
            status.update(label=f'Saved {path.name}: {len(result["records"]):,} records, {result.get("failed_pages",0):,} failures.',state='complete',expanded=True); st.session_state['latest_run']=str(path)
        except Exception as exc:
            status.update(label='Campaign coding failed',state='error',expanded=True); progress_line.error(f'{type(exc).__name__}: {exc!r}')
            with status.expander('Technical traceback'): st.code(traceback.format_exc())
    runs=[x for x in list_runs() if x.parent.name==bank.lower().replace(' ','-')]
    if runs:
        path=Path(st.selectbox('Saved campaign run',[str(x) for x in runs])); data=json.loads(path.read_text(encoding='utf8'))
        run_records=data.get('records',[]); run_errors=sum(bool(x.get('error')) for x in run_records); run_success=len(run_records)-run_errors
        r1,r2,r3=st.columns(3); r1.metric('Run records',len(run_records)); r2.metric('Successful',run_success); r3.metric('Failed',run_errors)
        st.download_button('Download selected campaign JSON',path.read_bytes(),path.name,'application/json')
        if st.button('Retry failed pages in selected run',disabled=run_errors==0,use_container_width=True):
            retry_status=st.status(f'Retrying {run_errors:,} failed pages in {path.name}...',expanded=True); retry_line=retry_status.empty()
            try:
                _,data=run_campaign_coding(bank,selected,retry_line.write,campaign_calls,campaign_spacing,path,campaign_instruction)
                remaining=sum(bool(x.get('error')) for x in data.get('records',[])); retry_status.update(label=f'Retry complete: {remaining:,} failures remain. Successful URLs were preserved and duplicates removed.',state='complete',expanded=True)
            except Exception as exc:
                retry_status.update(label='Retry run failed',state='error',expanded=True); retry_line.error(f'{type(exc).__name__}: {exc!r}')
        flat=[{'source_url':x.get('source_url'),'status':'error' if x.get('error') else 'coded',**({'error':x.get('error')} if x.get('error') else {})} for x in data.get('records',[])]
        st.dataframe(pd.DataFrame(flat),use_container_width=True,hide_index=True)


elif page=='Dataset normalisation':
    st.title('Optional dataset normalisation')
    st.caption('Two-step workflow: ask AI for suggestions, then review and execute exact manual replacements. The original campaign JSON is never modified.')
    st.info('Example for your Adult issue: choose Target audience; keep the suggestion instruction saying to collapse descriptive adult variants to Adult; click Ask AI; review lines such as Adults with savings seeking a low-risk investment. => Adult; then click Create normalised copy.')
    available=list_runs()
    if not available: st.info('No campaign runs are available.')
    else:
        source=Path(st.selectbox('Campaign dataset',available,format_func=run_label))
        instruction=st.text_area('AI suggestion instructions (does not edit the JSON)',value=read_prompt('normalisation_boss_default.md'),height=120,help='This guides only the Ask AI button. The AI proposes exact replacement lines; nothing changes until you review them and click Create normalised copy.')
        source_records=load_runs([source]); normalise_feature=st.selectbox('Feature to inspect or normalise',feature_names(source_records),index=None)
        if normalise_feature:
            normalise_values=unique_values(source_records,normalise_feature); st.caption(f'{len(normalise_values):,} unique values in this feature')
            with st.expander('Inspect unique values'): st.write(normalise_values)
            if st.button('Ask AI for reviewed replacement suggestions',use_container_width=True):
                with st.spinner('Generating English canonical-label suggestions...'):
                    try:
                        suggestions=suggest_normalisation(source_records,normalise_feature,instruction)
                        st.session_state['normalisation_map']='\n'.join(f'{old} => {new}' for old,new in suggestions)
                        st.rerun()
                    except Exception as exc: st.error(f'{type(exc).__name__}: {exc}')
        st.subheader('Reviewed exact replacements to execute')
        st.caption('This is the manual execution list, not an instruction box. One exact whole value per line: old value => new value. AI suggestions appear here for review. Substrings are never replaced and URLs are never changed.')
        mapping_text=st.text_area('Exact replacement rules that will be applied',value=st.session_state.get('normalisation_map',''),height=220,placeholder='Professional (entrepreneurs) => Professional\nProfessional clients/entrepreneurs seeking financing => Professional')
        replacements=[]; invalid=[]
        for line in mapping_text.splitlines():
            if not line.strip(): continue
            if '=>' not in line: invalid.append(line); continue
            old,new=line.split('=>',1); replacements.append((old.strip(),new.strip()))
        if invalid: st.warning(f'{len(invalid)} lines do not contain => and will not run.')
        if st.button('Create normalised copy',type='primary',disabled=not replacements or bool(invalid),use_container_width=True):
            try:
                target,changed=mass_replace(source,replacements,instruction); st.success(f'Created {target.name}; {changed:,} feature values changed. Original preserved.'); st.download_button('Download normalised JSON',target.read_bytes(),target.name,'application/json')
            except Exception as exc: st.error(f'{type(exc).__name__}: {exc}')

elif page=='Chat & graphs':
    st.title('Campaign analyst')
    st.caption('Select campaign data, optionally filter it, then ask the AI. The AI can create relevant charts automatically from the selected context.')
    available=list_runs()
    if not available: st.info('No campaign runs are available.')
    else:
        selected_paths=st.multiselect('Banks and campaign runs',available,format_func=run_label)
        records=load_runs(selected_paths) if selected_paths else []
        languages=available_languages(records) if records else []
        selected_languages=st.multiselect('Languages',languages,default=languages)
        if 'chat_filters' not in st.session_state: st.session_state.chat_filters={}
        include_all=st.checkbox('Use all records from the selected runs',value=False)
        with st.expander('Optional filters',expanded=not include_all):
            if st.button('Clear all filters',use_container_width=True): st.session_state.chat_filters={}; st.rerun()
            names=feature_names(records) if records else []
            feature=st.selectbox('Feature',names,index=None,placeholder='Target audience, product family, timing, etc.')
            if feature:
                values=unique_values(filter_records(records,selected_languages,{},True),feature)
                chosen_values=st.multiselect(f'Values for {feature}',values,key=f'values_{feature}')
                if st.button('Add filter',disabled=not chosen_values): st.session_state.chat_filters[feature]=chosen_values; st.rerun()
            for active,values in list(st.session_state.chat_filters.items()):
                left,right=st.columns([5,1]); left.error(f"{active}: {', '.join(values)}")
                if right.button('Remove',key=f'remove_{active}'): del st.session_state.chat_filters[active]; st.rerun()
        matched=filter_records(records,selected_languages,st.session_state.chat_filters,include_all)
        m1,m2=st.columns(2); m1.metric('Available records',len(records)); m2.metric('Records sent to AI',len(matched))
        if records and not include_all and not st.session_state.chat_filters: st.warning('Choose Use all records or add at least one filter before asking a question.')
        st.divider()
        chat_key='analyst_messages'
        if chat_key not in st.session_state: st.session_state[chat_key]=[]
        if st.session_state[chat_key]:
            heading_col,reset_col=st.columns([4,1]); heading_col.subheader('Conversation (newest first)')
            if reset_col.button('Reset conversation',use_container_width=True): st.session_state[chat_key]=[]; st.rerun()
            for message in reversed(st.session_state[chat_key]):
                with st.chat_message(message['role']):
                    st.markdown(message['content'])
                    for graph in message.get('graphs',[]):
                        graph_path=Path(graph)
                        if graph_path.exists():
                            st.image(str(graph_path)); st.download_button('Download chart',graph_path.read_bytes(),graph_path.name,'image/png',key=f"download_{graph_path.name}")
            st.divider()
        st.subheader('Ask the analyst')
        if not st.session_state[chat_key]:
            reset_col,_=st.columns([1,4])
            reset_col.button('Reset conversation',use_container_width=True,disabled=True)
        with st.expander('Optional analyst instruction'):
            chat_instruction=st.text_area('Instruction',height=70,placeholder='Focus on actionable cross-bank communication patterns.',label_visibility='collapsed')
        with st.form('analyst_question_form',clear_on_submit=True):
            question=st.text_area('Question',height=90,placeholder='Ask a question or request charts, for example: Compare target audiences and product families by bank and graph both.')
            ask=st.form_submit_button('Ask AI',type='primary',use_container_width=True,disabled=not matched)
        if ask and question.strip():
            st.session_state[chat_key].append({'role':'user','content':question.strip()})
            with st.spinner('Analysing the selected campaigns...'):
                try:
                    answer,graphs=chat_answer(st.session_state[chat_key],matched,chat_instruction)
                    st.session_state[chat_key].append({'role':'assistant','content':answer,'graphs':graphs})
                    st.rerun()
                except Exception as exc: st.error(f'{type(exc).__name__}: {exc}')

