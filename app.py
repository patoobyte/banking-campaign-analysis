import streamlit as st
import pandas as pd
from agent_backend import AgentRequest, run_agentic_bank
from backend import BANKS, analyze_bank, compare, latest_analyses, latest_comparison, timeline, chat, init_db
st.set_page_config(page_title='Market Signal',page_icon='◉',layout='wide')
st.markdown('''<style>:root{--ink:#17251e;--orange:#ff6200}.stApp{background:#f6f3ed;color:var(--ink)}[data-testid="stSidebar"]{background:#15251e}.hero{padding:25px 30px;border-radius:18px;background:linear-gradient(115deg,#15382c,#1e5a43);color:white;margin-bottom:20px}.eyebrow{color:#f8ad73;text-transform:uppercase;letter-spacing:2px;font-size:12px}.alert{background:white;border-left:5px solid #ff6200;padding:14px 18px;border-radius:8px;margin:8px 0;box-shadow:0 3px 14px #15382c12}.muted{color:#63716a}.stButton>button{border-radius:9px}</style>''',unsafe_allow_html=True)
init_db()
with st.sidebar:
 st.markdown('<h2 style="color:white">◉ MARKET SIGNAL</h2><p style="color:#a8bbb2">Competitive campaign intelligence</p>',unsafe_allow_html=True)
 page=st.radio('Workspace',['Command center','Bank profiles','Run analysis','Timeline','Ask intelligence'])
 st.divider(); st.caption('MODEL SETTINGS')
 base=st.text_input('API base URL','https://api.navy/v1'); model=st.text_input('Model','gpt-5.6-luna'); key=st.text_input('API key',type='password',placeholder='Loaded from .env'); settings={'base':base,'model':model,'key':key}
if page=='Command center':
 st.markdown('<div class="hero"><div class="eyebrow">ING Belgium · Proof of concept</div><h1>See the market move.<br>Before it becomes noise.</h1><p>Campaign, product and messaging signals from traditional and challenger banks.</p></div>',unsafe_allow_html=True)
 data=latest_analyses(); comp=latest_comparison(); alerts=(comp or {}).get('alerts',[])
 a,b,c,d=st.columns(4); a.metric('Banks monitored',len(data),'of 3'); b.metric('Campaigns found',sum(len(x.get('campaigns',[])) for x in data.values())); c.metric('Priority alerts',len([x for x in alerts if x.get('severity') in ['Critical','High']])); d.metric('Evidence snapshots',sum(len(timeline(x)) for x in BANKS))
 st.subheader('Immediate attention')
 if not alerts: st.info('No comparison yet. Analyze banks independently, then run comparison.')
 for x in alerts[:5]: st.markdown(f'''<div class="alert"><b>{x.get('severity','Signal')} · {x.get('title','Untitled')}</b><br><span class="muted">{x.get('bank','')} — {x.get('reason','')}</span><br><small>Action: {x.get('recommended_action','')}</small></div>''',unsafe_allow_html=True)
 st.subheader('Market overview'); cols=st.columns(3)
 for col,(bank,item) in zip(cols,data.items()):
  with col: st.markdown(f'### {bank}'); st.write(item.get('executive_summary','')); st.caption(f"{len(item.get('campaigns',[]))} campaigns detected")
 if comp:
  st.subheader('Recommended moves')
  for r in comp.get('recommendations',[]): st.write('→',r if isinstance(r,str) else r.get('recommendation',str(r)))
elif page=='Bank profiles':
 st.title('Individual bank intelligence')
 data=latest_analyses()
 if not data: st.info('Run a bank analysis first.')
 else:
  bank=st.selectbox('Bank profile',list(data)); item=data[bank]; coverage=item.get('_coverage',{})
  a,b,c,d=st.columns(4); a.metric('Coverage',item.get('coverage_status','Unknown')); b.metric('Pages collected',coverage.get('pages_collected',len(item.get('pages_examined',[])))); c.metric('Product pages',coverage.get('consumer_or_product_pages',0)); d.metric('UX findings',len(item.get('ux_findings',[])))
  st.subheader('Executive profile'); st.write(item.get('executive_summary','No executive profile returned.'))
  if item.get('missing_evidence'):
   with st.expander('Evidence gaps'): st.write(item['missing_evidence'])
  tabs=st.tabs(['Communication','Visual identity','Products','Journeys','UX findings','Campaigns','Evidence'])
  with tabs[0]: st.json(item.get('customer_communication',{})); st.json(item.get('information_architecture',{}))
  with tabs[1]: st.json(item.get('visual_identity',{}))
  with tabs[2]: st.dataframe(pd.DataFrame(item.get('product_portfolio',[])),width='stretch',hide_index=True)
  with tabs[3]: st.json(item.get('acquisition_journeys',[]))
  with tabs[4]: st.json(item.get('ux_findings',[]))
  with tabs[5]: st.json(item.get('campaigns',[]))
  with tabs[6]: st.json({'pages_examined':item.get('pages_examined',[]),'collection':item.get('_collection',[]),'coverage':coverage})
elif page=='Run analysis':
 st.title('Independent analysis runs'); st.caption('Each bank is collected and interpreted separately. Comparison only receives completed summaries.')
 bank=st.selectbox('Bank',list(BANKS)); mode=st.radio('Research mode',['Agentic investigation','Simple crawler'],horizontal=True); max_pages=st.slider('Maximum pages to explore',5,30,15); max_steps=st.slider('Agent tool-step budget',10,60,30,disabled=mode!='Agentic investigation'); visual=st.checkbox('Include browser screenshots for visual analysis',value=True); urls=st.text_area('Approved URLs — one per line','\n'.join(BANKS[bank]),height=100)
 if st.button(f'Analyze {bank}',type='primary'):
  with st.status(f'Starting {bank} analysis…',expanded=True) as status:
   try:
    def progress(message): status.update(label=message,state='running')
    seed_urls=[x.strip() for x in urls.splitlines() if x.strip()]
    if mode=='Agentic investigation': result=run_agentic_bank(AgentRequest(bank=bank,seed_urls=seed_urls,max_steps=max_steps,max_pages=max_pages,visual=visual),settings,None)
    else: result=analyze_bank(bank,seed_urls,settings,visual=visual,progress=progress,max_pages=max_pages)
    status.update(label='Analysis complete',state='complete'); st.json(result)
   except Exception as e:
    status.update(label='Analysis failed',state='error'); st.error(f'{type(e).__name__}: {e}'); st.exception(e)
 st.divider(); st.subheader('Cross-bank comparison'); st.write('Available:',', '.join(latest_analyses()) or 'none')
 if st.button('Build final comparison'):
  try:
   with st.spinner('Comparing evidence-backed summaries…'): st.session_state.comparison=compare(settings)
   st.success('Comparison saved to reports/'); st.json(st.session_state.comparison)
  except Exception as e: st.error(str(e))
elif page=='Timeline':
 st.title('Evidence timeline'); bank=st.selectbox('Competitor',list(BANKS)); rows=timeline(bank)
 if not rows: st.info('No snapshots yet. Run an analysis first.')
 else:
  df=pd.DataFrame(rows,columns=['Captured','Source','Fingerprint']); df['Captured']=pd.to_datetime(df['Captured']); dates=sorted(df['Captured'].dt.date.unique()); chosen=st.select_slider('Travel through captured states',options=dates,value=dates[-1]); st.dataframe(df[df['Captured'].dt.date==chosen],width='stretch',hide_index=True)
  st.caption('A changed fingerprint indicates changed visible page content. Historical raw text remains in the local SQLite database.')
else:
 st.title('Ask market intelligence'); st.caption('Answers use saved analyses and comparisons, with URL evidence where available.')
 if 'messages' not in st.session_state: st.session_state.messages=[]
 for m in st.session_state.messages:
  with st.chat_message(m['role']): st.markdown(m['content'])
 if q:=st.chat_input('Which competitor campaign needs our attention?'):
  st.session_state.messages.append({'role':'user','content':q})
  with st.chat_message('user'): st.markdown(q)
  with st.chat_message('assistant'):
   try: ans=chat(q,settings); st.markdown(ans); st.session_state.messages.append({'role':'assistant','content':ans})
   except Exception as e: st.error(str(e))
