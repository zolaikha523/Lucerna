import os, sys, time, json, re, hashlib
from pathlib import Path
from collections import Counter, defaultdict
from dotenv import load_dotenv
import streamlit as st

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env', override=True)

from core.ingest import read_file, make_chunks, source_hash
from core.llm import analyze_segments, answer_question
from core.validator import validate_candidate, validate_open_codes, validate_themes
from core import security
from exporters.reports import export_excel, export_csv, export_docx, export_markdown

security.init_db()
st.set_page_config(page_title='EvidenceQDA Enterprise',page_icon='◈',layout='wide',initial_sidebar_state='expanded')

# --------------------------- styling ---------------------------
st.markdown("""
<style>
:root{--ink:#17212b;--teal:#2b3d41;--muted:#6b7785;--line:#e5e9ed;--bg:#f7f9fb;--white:#fff;--green:#2f7d63;--amber:#b7791f;--red:#b42318;}
.stApp{background:var(--bg);color:var(--ink)}
.block-container{max-width:1450px;padding-top:1.2rem}
.brand{background:linear-gradient(135deg,#2b3d41,#1d2c30);color:white;padding:22px 26px;border-radius:18px;margin-bottom:18px;box-shadow:0 12px 30px rgba(23,33,43,.12)}
.brand h1{margin:0;font-size:30px;letter-spacing:-.5px}.brand p{margin:5px 0 0;opacity:.78}
.kpi{background:white;border:1px solid var(--line);border-radius:16px;padding:17px 18px;min-height:100px}.kpi .v{font-size:29px;font-weight:750}.kpi .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.card{background:white;border:1px solid var(--line);border-radius:16px;padding:18px;margin:8px 0}.small{color:var(--muted);font-size:13px}.pill{display:inline-block;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:650;margin:2px}
.code-card{background:white;border:1px solid var(--line);border-left:7px solid #2b3d41;border-radius:13px;padding:13px 15px;margin:8px 0}.quote{background:#f4f7f6;border-left:4px solid #2b3d41;padding:12px 14px;border-radius:8px;margin:8px 0}
.chat-user{background:#2b3d41;color:#fff;border-radius:16px 16px 4px 16px;padding:12px 15px;margin:7px 0 7px 12%;}.chat-ai{background:#fff;border:1px solid var(--line);border-radius:16px 16px 16px 4px;padding:12px 15px;margin:7px 12% 7px 0}
.security-ok{background:#e9f6f0;color:#176b4c;border-radius:12px;padding:10px 12px}.security-warn{background:#fff6e5;color:#8a5a00;border-radius:12px;padding:10px 12px}
footer{visibility:hidden}
</style>
""",unsafe_allow_html=True)

# --------------------------- helpers ---------------------------
def esc(x):
    return str(x).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def fingerprint(files):
    h=hashlib.sha256()
    for f in files: h.update(f.name.encode()); h.update(f.getvalue())
    return h.hexdigest()

def local_evidence(question,segments,k=8):
    terms=[x.lower() for x in re.findall(r'\w+',question) if len(x)>2]
    scored=[]
    for s in segments:
        txt=s['text'].lower(); score=sum(txt.count(t) for t in terms)
        scored.append((score,s))
    scored.sort(key=lambda x:x[0],reverse=True)
    chosen=[s for score,s in scored[:k] if score>0]
    return chosen or [s for _,s in scored[:min(k,len(scored))]]

def color_for(i):
    palette=['#2B3D41','#2F6F73','#557C55','#8A6F3D','#6A5D7B','#9B4D5C','#3E6B89','#7A674A','#4E7A67','#7C5B5B','#5C7080','#6C6A3D']
    return palette[i%len(palette)]

def make_downloads(title, themes, quotes, chat_msgs=None, analysis=None, docs=None, segments=None, codes=None, metadata=None):
    out=ROOT/'data'/'outputs'; out.mkdir(parents=True,exist_ok=True)
    stamp=time.strftime('%Y%m%d_%H%M%S'); base=f'{title.replace(" ","_")}_{stamp}'
    paths={'Word':out/f'{base}.docx','Markdown':out/f'{base}.md','Excel':out/f'{base}.xlsx','CSV':out/f'{base}.csv'}
    analysis=analysis or {}; docs=docs or []; segments=segments or []; codes=codes or []
    quotes=[q for q in (quotes or []) if q.get('verified') is True and q.get('verified_quote')]
    warnings=analysis.get('analysis_warnings', [])
    rejected=analysis.get('rejected_quotes', [])
    export_docx(title,themes or [],quotes,paths['Word'],chat_msgs,metadata=metadata,docs=docs,segments=segments,codes=codes,rejected_quotes=rejected,analysis_status=analysis.get('analysis_status','not run'),warnings=warnings)
    export_markdown(title,themes or [],quotes,paths['Markdown'],chat_msgs,metadata=metadata,docs=docs,segments=segments,codes=codes,rejected_quotes=rejected,analysis_status=analysis.get('analysis_status','not run'),warnings=warnings)
    evidence_rows=[{'document_id':q.get('document_id',''),'segment_id':q.get('segment_id',''),'theme':q.get('theme','Unclassified'),'code':q.get('code',''),'verified_quote':q.get('verified_quote',''),'verification_method':q.get('verification_method','')} for q in quotes]
    source_rows=[{'document_id':d.get('document_id',''),'filename':d.get('filename',''),'characters':d.get('characters',0),'sha256':d.get('sha256','')} for d in docs]
    code_rows=[{'code':c.get('code',''),'description':c.get('description',''),'segment_ids':', '.join(c.get('segment_ids') or [])} for c in codes]
    theme_rows=[{'theme':t.get('theme',''),'description':t.get('description',''),'codes':', '.join(t.get('codes') or [])} for t in (themes or [])]
    export_excel(evidence_rows,paths['Excel'],sheets={'Sources':source_rows,'Open Codes':code_rows,'Axial Themes':theme_rows,'QA Summary':[{'analysis_status':analysis.get('analysis_status','not run'),'source_documents':len(docs),'segments':len(segments),'open_codes':len(codes),'themes':len(themes or []),'verified_quotes':len(quotes),'rejected_candidates':len(rejected),'warnings':' | '.join(warnings)}]})
    export_csv(evidence_rows,paths['CSV'])
    return paths

# --------------------------- authentication ---------------------------
if 'auth_user' not in st.session_state: st.session_state.auth_user=None

if not st.session_state.auth_user:
    st.markdown('<div class="brand"><h1>EvidenceQDA Enterprise</h1><p>Privacy-first evidence-grounded qualitative data analysis</p></div>',unsafe_allow_html=True)
    if security.user_count()==0:
        st.subheader('Create the local administrator account')
        st.info('This account is stored locally in the project database. No cloud identity provider is required.')
        u=st.text_input('Username',value='admin'); p=st.text_input('Password',type='password'); p2=st.text_input('Confirm password',type='password')
        if st.button('Create administrator',type='primary'):
            if len(p)<10: st.error('Use a password of at least 10 characters.'); st.stop()
            if p!=p2: st.error('Passwords do not match.'); st.stop()
            security.create_user(u,p); security.audit(u,'ACCOUNT_CREATED','Initial local administrator created'); st.success('Administrator created. Please sign in.'); st.rerun()
    else:
        st.subheader('Secure sign in')
        u=st.text_input('Username'); p=st.text_input('Password',type='password')
        if st.button('Sign in',type='primary'):
            user=security.get_user(u)
            if not user or not security.verify_password(p,user['password_hash']): st.error('Invalid username or password.'); st.stop()
            if user.get('mfa_secret'):
                st.session_state.pending_user=u; st.session_state.pending_mfa=True; st.rerun()
            sid=security.create_session(u,'Browser session',st.context.headers.get('User-Agent','') if hasattr(st,'context') else '', 'local')
            st.session_state.auth_user=u; st.session_state.session_id=sid; security.audit(u,'LOGIN','Successful local sign-in'); st.rerun()
        st.caption('Local-only deployment: transcript content remains on this computer by default.')
    if st.session_state.get('pending_mfa'):
        st.divider(); st.subheader('Multi-factor authentication')
        code=st.text_input('6-digit authenticator code',max_chars=6)
        if st.button('Verify MFA'):
            user=security.get_user(st.session_state.pending_user)
            if security.verify_totp(user.get('mfa_secret'),code):
                u=st.session_state.pending_user; sid=security.create_session(u,'Browser session','', 'local'); st.session_state.auth_user=u; st.session_state.session_id=sid; st.session_state.pending_mfa=False; security.audit(u,'MFA_LOGIN','Successful MFA verification'); st.rerun()
            else: st.error('Invalid MFA code.')
    st.stop()

USER=st.session_state.auth_user
# --------------------------- data loading / auto analysis ---------------------------
if 'segments' not in st.session_state: st.session_state.segments=[]
if 'docs' not in st.session_state: st.session_state.docs=[]
if 'analysis' not in st.session_state: st.session_state.analysis=None
if 'report_metadata' not in st.session_state: st.session_state.report_metadata={}

with st.sidebar:
    st.markdown('### ◈ EvidenceQDA')
    st.caption(f'Signed in as **{USER}**')
    page=st.radio('Workspace',['Overview','Sources & Auto Analysis','Codebook','Clusters','Evidence Explorer','AI Chat','Reports','Security & Privacy','Audit & Incidents'],label_visibility='collapsed')
    st.divider();
    if st.button('Sign out'):
        security.audit(USER,'LOGOUT','User signed out'); st.session_state.clear(); st.rerun()

st.markdown('<div class="brand"><h1>EvidenceQDA Enterprise</h1><p>Automatic evidence-grounded QDA • Humanitarian privacy controls • Local AI by default</p></div>',unsafe_allow_html=True)

# upload is always available in Sources page; keep data through session state.
if page=='Sources & Auto Analysis':
    st.header('Sources & automatic analysis')
    st.write('Upload one or more FGD/interview files. EvidenceQDA will ingest, fingerprint, segment, code, cluster themes, verify quotations and refresh dashboards automatically.')
    files=st.file_uploader('Upload transcripts',type=['txt','docx','pdf'],accept_multiple_files=True)
    if files:
        fp=fingerprint(files)
        if st.session_state.get('fingerprint')!=fp:
            segs=[]; docs=[]
            for f in files:
                safe_name=Path(f.name).name; tmp=ROOT/'data'/'uploads'/safe_name; tmp.parent.mkdir(parents=True,exist_ok=True); tmp.write_bytes(f.getbuffer())
                text=read_file(str(tmp)); did=Path(safe_name).stem
                docs.append({'document_id':did,'filename':safe_name,'characters':len(text),'sha256':source_hash(text)})
                segs.extend(make_chunks(text,did))
            st.session_state.segments=segs; st.session_state.docs=docs; st.session_state.fingerprint=fp
            security.audit(USER,'UPLOAD',f'{len(docs)} documents, {len(segs)} evidence segments')
            st.session_state.analysis=None
            with st.spinner('Running automatic local evidence analysis...'):
                try:
                    raw=analyze_segments(segs)
                    raw["open_codes"] = validate_open_codes(raw.get("open_codes", []), segs)
                    raw["axial_themes"] = validate_themes(raw.get("axial_themes", []), raw["open_codes"])

                    # Enterprise Evidence Gate
                    validation_results = [
                        validate_candidate(q, segs)
                        for q in raw.get('candidate_quotes', [])
                    ]

                    verified = [
                        q for q in validation_results
                        if q.get('verified') is True
                    ]

                    rejected = [
                        q for q in validation_results
                        if q.get('verified') is not True
                    ]

                    final_analysis = {
                        **raw,
                        'candidate_quotes': verified,
                        'verified_quotes': verified,
                        'rejected_quotes': rejected,
                        'candidate_quote_count': len(validation_results),
                        'verified_quote_count': len(verified),
                        'rejected_quote_count': len(rejected)
                    }

                    if not final_analysis.get('open_codes') and not verified:
                        final_analysis['analysis_status'] = 'failed'
                        final_analysis.setdefault('analysis_warnings', []).append('The model returned no usable codes or source-verified quotations. Check Ollama connectivity/model availability and retry analysis.')
                    st.session_state.analysis = final_analysis

                    security.audit(
                        USER,
                        'AI_ANALYSIS',
                        f'Automatic analysis completed; '
                        f'{len(verified)} verified quotations; '
                        f'{len(rejected)} rejected quotations'
                    )

                except Exception as e:
                    st.session_state.analysis={'error':str(e)}; security.audit(USER,'AI_ANALYSIS_FAILED',str(e),'HIGH')
            st.rerun()
    if st.session_state.docs:
        st.success(f"{len(st.session_state.docs)} source documents • {len(st.session_state.segments)} evidence segments")
        st.dataframe(st.session_state.docs,use_container_width=True)
        if st.session_state.analysis and st.session_state.analysis.get('error'):
            st.error('Automatic analysis failed: '+st.session_state.analysis['error'])
            st.info('Confirm Ollama is running and the configured model is available, then use Retry analysis below.')
        elif st.session_state.analysis:
            a0=st.session_state.analysis
            st.subheader('Analysis results')
            m1,m2,m3,m4=st.columns(4)
            m1.metric('Open codes',len(a0.get('open_codes',[])))
            m2.metric('Themes',len(a0.get('axial_themes',[])))
            m3.metric('Verified quotes',len(a0.get('verified_quotes',[])))
            m4.metric('Rejected candidates',len(a0.get('rejected_quotes',[])))
            if a0.get('analysis_status')=='failed' or (not a0.get('open_codes') and not a0.get('verified_quotes')):
                st.error('No usable analysis was returned. The source file was ingested, but the local model did not produce codes or verified quotations.')
            elif a0.get('analysis_status')=='partial':
                st.warning('Analysis is partial. Review the warnings below before using any output.')
            for warning in a0.get('analysis_warnings',[]): st.warning(warning)
        if st.button('Retry analysis for current uploaded sources', key='retry_analysis'):
            if not st.session_state.segments:
                st.warning('Upload source files first.')
            else:
                with st.spinner('Retrying local analysis. The model may take several minutes on CPU...'):
                    try:
                        raw=analyze_segments(st.session_state.segments)
                        raw["open_codes"] = validate_open_codes(raw.get("open_codes", []), st.session_state.segments)
                        raw["axial_themes"] = validate_themes(raw.get("axial_themes", []), raw["open_codes"])
                        validation_results=[validate_candidate(q,st.session_state.segments) for q in raw.get('candidate_quotes',[])]
                        verified=[q for q in validation_results if q.get('verified') is True]
                        rejected=[q for q in validation_results if q.get('verified') is not True]
                        raw.update({'candidate_quotes':verified,'verified_quotes':verified,'rejected_quotes':rejected,'candidate_quote_count':len(validation_results),'verified_quote_count':len(verified),'rejected_quote_count':len(rejected)})
                        if not raw.get('open_codes') and not verified:
                            raw['analysis_status']='failed'
                            raw.setdefault('analysis_warnings',[]).append('The model returned no usable codes or source-verified quotations.')
                        st.session_state.analysis=raw
                        security.audit(USER,'AI_ANALYSIS_RETRY',f"Retry completed: {len(raw.get('open_codes',[]))} codes, {len(verified)} verified quotes")
                    except Exception as e:
                        st.session_state.analysis={'error':str(e),'analysis_status':'failed','analysis_warnings':[str(e)]}
                        security.audit(USER,'AI_ANALYSIS_FAILED',str(e),'HIGH')
                st.rerun()

analysis=st.session_state.analysis or {}
quotes=analysis.get('verified_quotes',[]); themes=analysis.get('axial_themes',[]); codes=analysis.get('open_codes',[]); segs=st.session_state.segments

# --------------------------- overview ---------------------------
if page=='Overview':
    st.header('Project intelligence dashboard')
    c=st.columns(6)
    vals=[len(st.session_state.docs),len(segs),len(codes),len(themes),len(quotes),len(set(q.get('document_id') for q in quotes))]
    labs=['Sources','Evidence segments','Open codes','Clusters/themes','Verified quotes','Covered sources']
    for col,v,l in zip(c,vals,labs): col.markdown(f'<div class="kpi"><div class="v">{v}</div><div class="l">{l}</div></div>',unsafe_allow_html=True)
    st.subheader('Evidence integrity')
    st.markdown('<div class="security-ok">✓ Quotations enter the report only after independent source verification. The LLM never becomes the source of truth.</div>',unsafe_allow_html=True)
    if not segs: st.info('Start in “Sources & Auto Analysis” and upload your transcripts.')
    else:
        left,right=st.columns(2)
        with left:
            st.markdown('#### Code frequency')
            freq=Counter()
            for c0 in codes: freq[c0.get('code','')]=len(c0.get('segment_ids',[]))
            st.bar_chart(freq)
        with right:
            st.markdown('#### Verified quotes by source')
            qdoc=Counter(q.get('document_id','') for q in quotes); st.bar_chart(qdoc)
        st.subheader('Theme clusters')
        for i,t in enumerate(themes):
            col=color_for(i); st.markdown(f'<div class="code-card" style="border-left-color:{col}"><b>{esc(t.get("theme","Theme"))}</b><div class="small">{esc(t.get("description",""))}</div><div>{" ".join(f"<span class=\"pill\" style=\"background:{col}15;color:{col}\">{esc(c)}</span>" for c in t.get("codes",[]))}</div></div>',unsafe_allow_html=True)

# --------------------------- codebook ---------------------------
elif page=='Codebook':
    st.header('Automatic codebook')
    st.caption('Codes are proposed from transcript evidence. Color is assigned automatically for visual tracking; researchers can still review and refine the codebook.')
    if not codes:
        if st.session_state.docs and analysis.get('analysis_status') == 'failed': st.error('Sources are loaded, but AI analysis failed or returned no usable codes. Open Sources & Auto Analysis and review warnings, then Retry analysis.')
        else: st.info('No codes yet. Upload sources and run analysis first.')
    for i,c0 in enumerate(codes):
        col=color_for(i); st.markdown(f'<div class="code-card" style="border-left-color:{col}"><div><span class="pill" style="background:{col}15;color:{col}">CODE {i+1}</span> <b>{esc(c0.get("code",""))}</b></div><div class="small">{esc(c0.get("description",""))}</div><div class="small">Evidence segments: {len(c0.get("segment_ids",[]))}</div></div>',unsafe_allow_html=True)

# --------------------------- clusters ---------------------------
elif page=='Clusters':
    st.header('Theme / cluster dashboard')
    if not themes:
        if codes: st.warning('Open codes exist, but theme synthesis is unavailable. Review and cluster the codes manually; the report labels findings at code level.')
        else: st.info('No theme clusters yet. Run analysis first.')
    else:
        for i,t in enumerate(themes):
            related=[c for c in codes if c.get('code') in t.get('codes',[])]
            st.markdown(f'### {i+1:02d} · {t.get("theme","")}')
            st.write(t.get('description',''))
            a,b,c=st.columns(3); a.metric('Codes',len(related)); b.metric('Evidence segments',len(set(x for c0 in related for x in c0.get('segment_ids',[])))); c.metric('Verified quotes',sum(1 for q in quotes if q.get('theme')==t.get('theme')))
            for c0 in related: st.markdown(f'`{c0.get("code")}`',unsafe_allow_html=True)
            st.divider()

# --------------------------- evidence explorer ---------------------------
elif page=='Evidence Explorer':
    st.header('Evidence explorer')
    search=st.text_input('Search source evidence')
    rows=[]
    for s in segs:
        if not search or search.lower() in s['text'].lower(): rows.append({'document_id':s['document_id'],'segment_id':s['segment_id'],'text':s['text']})
    st.dataframe(rows,use_container_width=True,height=520)
    st.subheader('Verified quotations')
    for q in quotes:
        st.markdown(f'<div class="quote">“{esc(q.get("verified_quote",""))}”<br><span class="small">{esc(q.get("document_id",""))} · {esc(q.get("segment_id",""))} · {esc(q.get("verification_method",""))}</span></div>',unsafe_allow_html=True)

# --------------------------- chat ---------------------------
elif page=='AI Chat':
    st.header('Evidence Chat')
    st.caption('Chat stories are stored locally. Answers are restricted to retrieved transcript evidence and include segment citations.')
    chats=security.list_chats(USER)
    options={f"{x['title']} · {time.strftime('%Y-%m-%d',time.localtime(x['created_at']))}":x['id'] for x in chats}
    chosen=st.selectbox('Chat story',list(options),index=0) if options else None
    if st.button('＋ New chat story') or (not options and 'chat_id' not in st.session_state):
        cid=security.create_chat('New evidence story',USER); st.session_state.chat_id=cid; st.rerun()
    if chosen: st.session_state.chat_id=options[chosen]
    cid=st.session_state.get('chat_id')
    if cid:
        msgs=security.messages(cid)
        for m in msgs:
            cls='chat-user' if m['role']=='user' else 'chat-ai'; st.markdown(f'<div class="{cls}"><b>{m["role"].title()}</b><br>{esc(m["content"]).replace(chr(10),"<br>")}</div>',unsafe_allow_html=True)
        q=st.chat_input('Ask about the uploaded evidence…')
        if q:
            evidence=local_evidence(q,segs,8)
            security.add_message(cid,'user',q,[s['segment_id'] for s in evidence])
            with st.spinner('Checking the evidence…'):
                try:
                    ans=answer_question(q,evidence)
                    content=ans.get('answer','Insufficient evidence in the uploaded sources.')
                    cits=ans.get('citations',[])
                    verified_q=[]
                    for qq in ans.get('quotes',[]):
                        v=validate_candidate(qq,evidence)
                        if v.get('verified'): verified_q.append(v)
                    if verified_q:
                        content += '\n\nVerified quotations:\n' + '\n'.join([f'“{x["verified_quote"]}” [{x["segment_id"]}]' for x in verified_q])
                    security.add_message(cid,'assistant',content,cits)
                    security.audit(USER,'CHAT_QUERY',f'Chat {cid}; {len(evidence)} evidence segments retrieved')
                except Exception as e:
                    security.add_message(cid,'assistant',f'Unable to answer safely: {e}',[]); security.audit(USER,'CHAT_FAILED',str(e),'HIGH')
            st.rerun()
        st.divider();
        if st.button('Download this chat story'):
            msgs=security.messages(cid); paths=make_downloads('EvidenceQDA Chat Story',themes,quotes,msgs,analysis=analysis,docs=st.session_state.docs,segments=segs,codes=codes,metadata=st.session_state.report_metadata)
            for label,p in paths.items(): st.download_button(f'Download {label}',p.read_bytes(),file_name=p.name,key=f'chatdl_{label}_{cid}')

# --------------------------- reports ---------------------------
elif page=='Reports':
    st.header('Donor-ready report builder')
    st.write('Complete the study metadata below. EvidenceQDA will not invent missing sampling, consent, location, or participant details.')
    with st.form('report_metadata_form'):
        meta=st.session_state.report_metadata
        col1,col2=st.columns(2)
        with col1:
            organization=st.text_input('Organization / consortium',value=meta.get('organization',''))
            project=st.text_input('Project / assessment title',value=meta.get('project',''))
            sector=st.text_input('Sector',value=meta.get('sector',''))
            geography=st.text_input('Geographic coverage',value=meta.get('geography',''))
            study_period=st.text_input('Data collection period',value=meta.get('study_period',''))
            analyst=st.text_input('Prepared by / analyst',value=meta.get('analyst',''))
        with col2:
            purpose=st.text_area('Study purpose / key research question',value=meta.get('purpose',''),height=80)
            sampling=st.text_area('Sampling approach and sample size',value=meta.get('sampling',''),height=70)
            participant_selection=st.text_area('Participant selection / group profile (de-identified)',value=meta.get('participant_selection',''),height=70)
            fgd_details=st.text_area('FGD count, locations, participant groups',value=meta.get('fgd_details',''),height=70)
            kii_details=st.text_area('KII count and informant expertise (no names)',value=meta.get('kii_details',''),height=70)
        inclusion_criteria=st.text_area('Inclusion criteria',value=meta.get('inclusion_criteria',''))
        ethics=st.text_area('Informed consent, confidentiality and safeguarding measures',value=meta.get('ethics',''))
        limitations=st.text_area('Study limitations',value=meta.get('limitations',''))
        methodology_notes=st.text_area('Additional methodology / triangulation notes',value=meta.get('methodology_notes',''))
        save_meta=st.form_submit_button('Save report details')
    if save_meta:
        st.session_state.report_metadata={'organization':organization,'project':project,'sector':sector,'geography':geography,'study_period':study_period,'analyst':analyst,'purpose':purpose,'sampling':sampling,'participant_selection':participant_selection,'fgd_details':fgd_details,'kii_details':kii_details,'inclusion_criteria':inclusion_criteria,'ethics':ethics,'limitations':limitations,'methodology_notes':methodology_notes}
        st.success('Report details saved for this session.')
    st.divider()
    analysis=st.session_state.analysis or {}
    st.subheader('Analysis quality check')
    st.write(f"Sources: {len(st.session_state.docs)} · Segments: {len(segs)} · Codes: {len(codes)} · Themes: {len(themes)} · Verified quotes: {len(quotes)}")
    if not st.session_state.docs: st.warning('Upload at least one transcript before generating a report.')
    elif not codes and not quotes: st.error('The current project has no usable analysis. The package can be exported for diagnostics, but it is not a donor-ready findings report yet. Return to Sources & Auto Analysis and use Retry analysis.')
    if st.button('Generate report package',type='primary'):
        paths=make_downloads('EvidenceQDA Analysis',themes,quotes,analysis=analysis,docs=st.session_state.docs,segments=segs,codes=codes,metadata=st.session_state.report_metadata)
        security.audit(USER,'REPORT_EXPORT',f'Generated {len(paths)} report formats; {len(quotes)} verified quotations')
        st.session_state.report_paths={label:str(path) for label,path in paths.items()}
        st.success('Report package generated. Review the QA/limitations section before donor submission.')
    for label,path_str in st.session_state.get('report_paths',{}).items():
        p=Path(path_str)
        if p.exists(): st.download_button(f'Download {label}',p.read_bytes(),file_name=p.name,key=f'report_{label}_{p.name}')
    if quotes: st.dataframe(quotes,use_container_width=True)

# --------------------------- security/privacy ---------------------------
elif page=='Security & Privacy':
    st.header('Security & Privacy')
    p=security.privacy()
    a,b,c=st.columns(3)
    a.markdown('<div class="security-ok">✓ Local AI mode</div>',unsafe_allow_html=True)
    b.markdown('<div class="security-ok">✓ Source verification</div>',unsafe_allow_html=True)
    c.markdown('<div class="security-ok">✓ Local audit trail</div>',unsafe_allow_html=True)
    st.subheader('Organization privacy policy')
    org=st.text_input('Organization name',p['organization_name']); cls=st.selectbox('Default data classification',['Public','Internal','Confidential','Restricted'],index=['Public','Internal','Confidential','Restricted'].index(p['classification'])); ret=st.number_input('Retention period (days)',min_value=1,max_value=36500,value=int(p['retention_days'])); local=st.checkbox('Local-only processing (recommended)',value=bool(p['local_only'])); remote=st.checkbox('Remote AI endpoint approved by organization',value=bool(p['external_ai_approved']))
    if st.button('Save privacy settings'):
        security.update_privacy(organization_name=org,classification=cls,retention_days=ret,local_only=int(local),external_ai_approved=int(remote)); security.audit(USER,'PRIVACY_SETTINGS','Privacy settings updated'); st.success('Privacy settings saved.')
    st.divider(); st.subheader('Account security')
    with st.form('pw'):
        old=st.text_input('Current password',type='password'); new=st.text_input('New password',type='password'); new2=st.text_input('Confirm new password',type='password'); ok=st.form_submit_button('Change password')
        if ok:
            u=security.get_user(USER)
            if not security.verify_password(old,u['password_hash']): st.error('Current password is incorrect.')
            elif len(new)<10: st.error('Use at least 10 characters.')
            elif new!=new2: st.error('Passwords do not match.')
            else: security.set_password(USER,new); security.audit(USER,'PASSWORD_CHANGED','Password changed successfully'); st.success('Password changed.')
    u=security.get_user(USER)
    st.subheader('Multi-factor authentication')
    if not u.get('mfa_secret'):
        if st.button('Enable MFA'):
            secret=security.new_mfa_secret(); codes=security.new_recovery_codes(); security.set_mfa(USER,secret,codes); st.session_state.mfa_secret=secret; st.session_state.mfa_codes=codes; st.rerun()
    else:
        st.success('MFA is enabled for this account.')
        if st.button('Disable MFA'):
            security.clear_mfa(USER); security.audit(USER,'MFA_DISABLED','MFA disabled by account owner','HIGH'); st.warning('MFA disabled.')
    if st.session_state.get('mfa_secret'):
        secret=st.session_state.mfa_secret; st.code(f'otpauth://totp/EvidenceQDA:{USER}?secret={secret}&issuer=EvidenceQDA')
        st.caption('Add this secret to an authenticator app. Keep recovery codes offline.')
        st.code('\n'.join(st.session_state.mfa_codes))
        test=st.text_input('Verify new MFA code')
        if st.button('Confirm MFA setup'):
            if security.verify_totp(secret,test): security.audit(USER,'MFA_ENABLED','MFA setup verified'); st.session_state.pop('mfa_secret',None); st.session_state.pop('mfa_codes',None); st.success('MFA verified and enabled.')
            else: st.error('Code did not verify.')
    st.divider(); st.subheader('Device control')
    for s in security.sessions(USER):
        status='Revoked' if s['revoked'] else 'Active'; st.markdown(f'<div class="card"><b>{esc(s["device_label"])}</b> · {status}<br><span class="small">Last seen: {time.strftime("%Y-%m-%d %H:%M",time.localtime(s["last_seen"]))} · IP: {esc(s["ip"] or "local")}</span></div>',unsafe_allow_html=True)
        if not s['revoked'] and st.button('Revoke session',key='rv'+s['id']): security.revoke_session(s['id'],USER); security.audit(USER,'DEVICE_REVOKED',s['id'],'HIGH'); st.rerun()
    st.divider(); st.subheader('Data protection statement')
    st.write('By default this build uses the local Ollama server. Transcript contents are not sent to ChatGPT/OpenAI. The application does not claim that it can detect every appearance of data across the global internet; use an approved organizational DLP/SIEM integration for that requirement.')

# --------------------------- audit/incidents ---------------------------
elif page=='Audit & Incidents':
    st.header('Audit trail & incident register')
    c=security.connect(); rows=[dict(r) for r in c.execute('SELECT ts,username,action,detail,severity FROM audit ORDER BY id DESC LIMIT 500')]; c.close()
    for r in rows[:100]: st.markdown(f'<div class="card"><b>{esc(r["action"])}</b> · <span class="small">{time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(r["ts"]))} · {esc(r["username"])} · {esc(r["severity"])}</span><br>{esc(r["detail"])}</div>',unsafe_allow_html=True)
    st.divider(); st.subheader('Exposure / incident watch')
    st.warning('This is an internal incident register, not global internet surveillance. Do not upload confidential transcript contents to unapproved third-party scanners.')
    with st.form('incident'):
        title=st.text_input('Incident title'); sev=st.selectbox('Severity',['Low','Medium','High','Critical']); status=st.selectbox('Status',['Open','Investigating','Contained','Closed']); source=st.text_input('Source / URL / system'); notes=st.text_area('Notes'); submit=st.form_submit_button('Record incident')
        if submit and title:
            security.add_incident(title,sev,status,source,notes,USER); security.audit(USER,'INCIDENT_CREATED',title,sev.upper()); st.success('Incident recorded.'); st.rerun()
    for x in security.incidents(): st.markdown(f'<div class="card"><b>{esc(x["title"])}</b> · {esc(x["severity"])} · {esc(x["status"])}<br><span class="small">{esc(x["source"])} · {esc(x["notes"])}</span></div>',unsafe_allow_html=True)
