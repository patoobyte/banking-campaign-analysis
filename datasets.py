from __future__ import annotations
import json, shutil, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from config import CLEAN, BACKUPS, RUNS, ROOT, bank_dir, slug
from collector import load_raw_records
from ai import classify_cleaning_batch, classify_campaign, provider_preflight, configure_ai_pacing

def clean_path(bank): return bank_dir(CLEAN,bank)/'dataset.json'
def load_clean(bank):
    path=clean_path(bank)
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else None

def backup_clean(bank):
    source=bank_dir(CLEAN,bank)
    if not (source/'dataset.json').exists(): return None
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S'); target=bank_dir(BACKUPS,bank)/f'{stamp}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in source.rglob('*'):
            if file.is_file(): archive.write(file,file.relative_to(source))
    return target

def restore_backup(bank, backup: str):
    target=bank_dir(CLEAN,bank)
    for file in target.iterdir():
        if file.is_file(): file.unlink()
        elif file.is_dir(): shutil.rmtree(file)
    with zipfile.ZipFile(backup) as archive: archive.extractall(target)

def estimate_cleaning_tokens(bank, kept_rows, batch_size=8):
    raw=load_raw_records(bank,{r['url'] for r in kept_rows}); pages=[p for p in raw if p.get('text')]
    chars=sum(len(p.get('text','')[:24000]) for p in pages)
    # Conservative approximation: text chars / 4 plus repeated prompt and JSON overhead per page.
    input_tokens=(chars+3)//4 + len(pages)*700
    output_tokens=len(pages)*180
    return {'pages':len(pages),'text_characters':chars,'estimated_input_tokens':input_tokens,'estimated_output_tokens':output_tokens,'estimated_total_tokens':input_tokens+output_tokens,'batches':(len(pages)+batch_size-1)//batch_size}

def cleaning_record_has_error(record):
    reason=str(record.get('exclusion_reason') or '')
    return bool(record.get('ai_error') or record.get('error') or reason.startswith('AI batch failed:') or reason=='AI response missing URL')

def count_cleaning_errors(clean):
    return sum(cleaning_record_has_error(record) for record in (clean or {}).get('records',[]))

def build_clean_dataset(bank, kept_rows, batch_size=8, rebuild=False, progress=None, concurrent_calls=5, request_spacing=1.0, custom_instruction="", retry_failed=False):
    configure_ai_pacing(request_spacing)
    old=load_clean(bank)
    backup=str(backup_clean(bank)) if (rebuild or retry_failed) and old else None
    raw=load_raw_records(bank,{r['url'] for r in kept_rows}); previous={r['url']:r for r in (old or {}).get('records',[])} if not rebuild else {}
    records=[]; pending=[]
    for page in raw:
        existing=previous.get(page['url'])
        if existing and not (retry_failed and cleaning_record_has_error(existing)):
            records.append(existing)
        elif page.get('text'):
            pending.append(page)
    batches=[pending[i:i+batch_size] for i in range(0,len(pending),batch_size)]
    if not batches:
        remaining_errors=sum(cleaning_record_has_error(record) for record in records)
        final={'bank':bank,'created_at':datetime.now(timezone.utc).isoformat(),'status':'complete_with_failures' if remaining_errors else 'complete','backup_created':backup,'failed_records':remaining_errors,'records':sorted(records,key=lambda x:x['url'])}
        clean_path(bank).write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf8')
        return final
    if progress: progress('Checking provider connectivity before starting AI batches...')
    probe=provider_preflight()
    if progress: progress(f"Provider {probe['model']} connected in {probe['seconds']}s. Starting {len(batches):,} batches with {min(concurrent_calls,len(batches))} concurrent calls...")
    completed=0; failed_batches=0
    def process(batch):
        classified=classify_cleaning_batch(bank,batch,custom_instruction); by_url={x.get('url'):x for x in classified}; output=[]
        for page in batch:
            decision=by_url.get(page['url'],{'eligible':False,'exclusion_reason':'AI response missing URL','audience_categories':['Not identifiable'],'confidence':'Low','ai_error':True})
            output.append({**{k:page.get(k) for k in ['url','language','last_modified','captured_at','status','html_file','text_file','text_chars','structure']},**decision})
        return output
    # Submit only one bounded wave at a time. This starts requests immediately without queuing all 318 futures.
    workers=min(max(1,concurrent_calls),50,len(batches))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for offset in range(0,len(batches),workers):
            wave=batches[offset:offset+workers]; futures={pool.submit(process,b):b for b in wave}
            for future in as_completed(futures):
                try: records.extend(future.result())
                except Exception as exc:
                    failed_batches+=1
                    batch=futures[future]
                    for page in batch:
                        records.append({**{k:page.get(k) for k in ['url','language','last_modified','captured_at','status','html_file','text_file','text_chars','structure']},'eligible':False,'exclusion_reason':f'AI batch failed: {type(exc).__name__}: {exc}','audience_categories':['Not identifiable'],'confidence':'Low','ai_error':True})
                completed+=1
                partial={'bank':bank,'created_at':datetime.now(timezone.utc).isoformat(),'status':'building','completed_batches':completed,'total_batches':len(batches),'failed_batches':failed_batches,'records':records}
                clean_path(bank).write_text(json.dumps(partial,ensure_ascii=False,indent=2),encoding='utf8')
                if progress: progress(f'AI batches complete {completed:,}/{len(batches):,} ? pages saved {len(records):,} ? failed batches {failed_batches:,}')
    # Collapse by URL defensively and calculate failure state from the resulting dataset.
    by_url={record['url']:record for record in records if record.get('url')}
    final_records=sorted(by_url.values(),key=lambda x:x['url'])
    remaining_errors=sum(cleaning_record_has_error(record) for record in final_records)
    final={'bank':bank,'created_at':datetime.now(timezone.utc).isoformat(),'status':'complete_with_failures' if remaining_errors else 'complete','backup_created':backup,'failed_batches':failed_batches,'failed_records':remaining_errors,'records':final_records}
    clean_path(bank).write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf8'); return final

def backups(bank): return sorted(bank_dir(BACKUPS,bank).glob('*.zip'),reverse=True)

def _next_run(bank):
    folder=bank_dir(RUNS,bank); nums=[]
    for path in folder.glob('*campaign-*.json'):
        m=path.stem.rsplit('-',1)[-1]
        if m.isdigit(): nums.append(int(m))
    code={'ING':'ING','BNP Paribas Fortis':'BNP','Revolut':'REV'}.get(bank,slug(bank).upper()[:3]); return folder/f'{code}-campaign-{max(nums,default=0)+1:02d}.json'

def estimate_campaign_tokens(bank, languages):
    clean=load_clean(bank) or {}; chosen=[r for r in clean.get('records',[]) if r.get('eligible') and (not languages or r.get('language') in languages)]
    pages={x['url']:x for x in load_raw_records(bank,{r['url'] for r in chosen})}; definitions=(ROOT/'prompts'/'campaign_features_v01.md').read_text(encoding='utf8')
    chars=sum(len(pages.get(r['url'],{}).get('text','')[:70000])+len(definitions) for r in chosen)
    return {'pages':len(chosen),'estimated_input_tokens':(chars+3)//4,'estimated_output_tokens':len(chosen)*1800,'estimated_total_tokens':(chars+3)//4+len(chosen)*1800}

def run_campaign_coding(bank, languages, progress=None, concurrent_calls=35, request_spacing=1.0, resume_path=None, custom_instruction=""):
    clean=load_clean(bank)
    if not clean or clean.get('status') not in ('complete','complete_with_failures'): raise RuntimeError('Build the clean dataset first.')
    chosen=[r for r in clean['records'] if r.get('eligible') and (not languages or r.get('language') in languages)]
    pages={x['url']:x for x in load_raw_records(bank,{r['url'] for r in chosen})}; definitions=(ROOT/'prompts'/'campaign_features_v01.md').read_text(encoding='utf8')
    configure_ai_pacing(request_spacing)
    path=Path(resume_path) if resume_path else _next_run(bank)
    if resume_path and path.exists():
        output=json.loads(path.read_text(encoding='utf8')); by_url={r.get('source_url'):r for r in output.get('records',[]) if r.get('source_url')}
        # Retry errors only; successful records remain immutable and duplicate URLs collapse to one record.
        chosen=[r for r in chosen if r['url'] not in by_url or by_url[r['url']].get('error')]
        output['records']=[r for r in by_url.values() if not r.get('error')]
        output.update({'status':'running','completed_pages':len(output['records']),'failed_pages':0,'retrying_failed':True})
    else:
        output={'schema_version':'v01','bank':bank,'created_at':datetime.now(timezone.utc).isoformat(),'languages':languages or ['all'],'status':'running','model':None,'total_pages':len(chosen),'completed_pages':0,'failed_pages':0,'records':[]}
    if progress: progress('Checking provider connectivity before campaign coding...')
    probe=provider_preflight(); output['model']=probe['model']; path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    if progress: progress(f"Provider {probe['model']} connected in {probe['seconds']}s. Coding {len(chosen):,} pages independently with {min(concurrent_calls,len(chosen))} concurrent calls...")
    def process(row):
        page=dict(pages.get(row['url'],{})); page.update({'bank':bank,'capture_date':(row.get('captured_at') or '')[:10],'channel':'Website','viewport_dimensions':'Not captured','signature_color':'See bank configuration','audience_categories':row.get('audience_categories',[])})
        return {'source_url':row['url'],'features':classify_campaign(bank,page,definitions,custom_instruction)}
    completed=len(output['records']); failed=0; workers=min(max(1,int(concurrent_calls)),50,max(1,len(chosen)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Bounded waves preserve one-page-per-call while respecting the chosen concurrency/RPM ceiling.
        for offset in range(0,len(chosen),workers):
            wave=chosen[offset:offset+workers]; futures={pool.submit(process,row):row for row in wave}
            for future in as_completed(futures):
                row=futures[future]
                try: output['records'].append(future.result())
                except Exception as exc: failed+=1; output['records'].append({'source_url':row['url'],'error':f'{type(exc).__name__}: {exc}'})
                completed+=1; output['completed_pages']=completed; output['failed_pages']=failed
                path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
                if progress: progress(f"Campaign pages coded {completed:,}/{output.get('total_pages',len(chosen)):,} - successful {completed-failed:,} - failed {failed:,}")
    deduped={r.get('source_url'):r for r in output['records'] if r.get('source_url')}; output['records']=list(deduped.values())
    output['failed_pages']=sum(bool(r.get('error')) for r in output['records']); output['completed_pages']=len(output['records'])
    output['status']='complete_with_failures' if output['failed_pages'] else 'complete'; path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8'); return path,output

def list_runs(): return sorted(RUNS.glob('*/*campaign-*.json'),reverse=True)
