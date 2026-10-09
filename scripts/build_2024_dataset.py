"""Build a binary SCOTUS graph from the cached official 2024 opinions.

The acquisition and extraction scripts create raw inputs; this build is offline.
It does not change the student's graph algorithms or the 2004 dataset.
"""
import csv,io,json,re,zipfile,hashlib
from collections import defaultdict,Counter
from datetime import datetime,timezone
from html import unescape
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
OUT=PROJECT/'data/term_2024'
RAW=OUT/'raw'
OUT.mkdir(parents=True,exist_ok=True)
US=re.compile(r'\b(\d{1,3})\s+U\.\s*S\.\s+(\d+)\b')
NOM=re.compile(r'\b(\d+)\s+(Dall\.|Cranch|Wheat\.|Pet\.|How\.|Black|Wall\.)\s*(\d+)\b')
OFFSETS={'Dall.':0,'Cranch':4,'Wheat.':13,'Pet.':25,'How.':41,'Black':65,'Wall.':67}
def normalize(t):return re.sub(r'\s+',' ',t).strip()
def cite_key(t):
 m=US.search(t)
 return ':'.join(m.groups()) if m else None
def cite_text(k):return k.replace(':',' U.S. ')
def refs(t):
 for m in US.finditer(t):yield ':'.join(m.groups()),m
 for m in NOM.finditer(t):yield f'{int(m[1])+OFFSETS[m[2]]}:{m[3]}',m
def clean(x):return normalize(unescape(re.sub('<[^>]*>','',x)))
def index_rows(text,term):
 for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',text,re.S):
  cells=re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)
  if len(cells)!=6:continue
  link=re.search(r"href=['\"](/opinions/[^'\"]+\.pdf)",cells[3])
  if not link:continue
  vals=list(map(clean,cells));k=cite_key(vals[5])
  if not k:continue
  yield {'key':k,'case_name':vals[3],'date_filed':datetime.strptime(vals[1],'%m/%d/%y').date().isoformat(),'docket':vals[2],'url':'https://www.supremecourt.gov'+link[1],'term':term}
with zipfile.ZipFile(PROJECT/'data/term_2004/raw/scdb.zip') as z:
 SCDB=list(csv.DictReader(io.StringIO(z.read(next(n for n in z.namelist() if n.endswith('.csv'))).decode('utf-8-sig'))))
roster=json.loads((RAW/'term-roster.json').read_text())
metadata=defaultdict(list)
legacy={}
for r in csv.DictReader((PROJECT/'data/term_2004/cases.csv').open()):
 k=cite_key(r['us_citation']);legacy[k]=r
for r in SCDB:
 k=cite_key(r['usCite'])
 if k:metadata[k].append({'case_name':r['caseName'],'date_filed':datetime.strptime(r['dateDecision'],'%m/%d/%Y').date().isoformat(),'url':'https://scdb.la.psu.edu/','provenance':'scdb_2025_01','identity':r['caseId'],'cap_id':''})
# Authoritative term indexes supplement the SCDB release's missing newer US cites.
for y in range(2016,2025):
 f=RAW/'indexes'/f'official-{y}.html' if y!=2024 else RAW/'official2024.html'
 for r in index_rows(f.read_text(),y):
  metadata[r['key']]=[{**r,'provenance':'official_opinion_index','identity':r['url'],'cap_id':''}]
# Archive metadata supplies early precedents and orders absent from the modern SCDB.
for f in sorted((RAW/'indexes').glob('cap-*.json')):
 for r in json.loads(f.read_text()):
  if r['court']['id']!=9009:continue
  c=next((c['cite'] for c in r['citations'] if c['type']=='official'),'');k=cite_key(c)
  if not k:continue
  metadata[k].append({'case_name':r['name_abbreviation'],'date_filed':r['decision_date'],'url':f'https://cite.case.law/us/{k.split(":")[0]}/{r["first_page"]}/','provenance':'harvard_cap_metadata','identity':str(r['id']),'cap_id':str(r['id'])})
# Search results are used only when the exact reporter citation matches and the court is SCOTUS.
api_file=RAW/'target-search-results.json'
if api_file.exists():
 api_meta=defaultdict(dict)
 for r in json.loads(api_file.read_text()):
  if r['court_id']!='scotus':continue
  for c in r['citation']:
   k=cite_key(c)
   if k:api_meta[k][r['cluster_id']]={'case_name':r['caseName'],'date_filed':r['dateFiled'],'url':'https://www.courtlistener.com'+r['absolute_url'],'identity':str(r['cluster_id']),'cap_id':'','provenance':'courtlistener_exact_citation_search'}
 for k,rows in api_meta.items():
  if not metadata[k]:metadata[k]=list(rows.values())
# Reuse existing node IDs for every shared reporter citation across the two terms.
for k,r in legacy.items():metadata[k]=[{**r,'identity':r['case_id'],'provenance':'verified_2004_node_metadata'}]
for k,r in json.loads((RAW/'metadata-overrides.json').read_text()).items():metadata[k]=[r]
def resolve(k):
 rows=metadata[k]
 # Parallel SCDB/CAP records are the same case only when date matches and CAP resolves uniquely.
 caps={r['cap_id']:r for r in rows if r.get('cap_id')}
 if len(caps)>1:return None,'ambiguous_target'
 if len(caps)==1:
  cap=next(iter(caps.values()))
  if any(r['date_filed']!=cap['date_filed'] for r in rows):return None,'conflicting_target_dates'
  return cap,None
 unique={r['identity']:r for r in rows}
 if not unique:return None,'unresolved_target'
 if len(unique)>1:return None,'ambiguous_target'
 return next(iter(unique.values())),None
source_rows={};case_review=[];opinion_audit=[];reviews=[];evidence=[];edges=set();nodes={};needed_volumes=set()
for item in roster:
 r,o=item['scdb'],item['official'];sid=r['caseId'];key=cite_key(o['citation']);cid=legacy.get(key,{}).get('case_id','us:'+key)
 status='included';reason='Argued SCDB decision type 1 or 6; whole majority/per-curiam text separable.'
 if not r['dateArgument']:status,reason='excluded','No oral argument in SCDB.'
 elif r['decisionType'] not in ('1','6'):status,reason='excluded','Outside selected majority/per-curiam SCDB decision types.'
 elif sid=='2024-024':status,reason='needs_review','Hewitt has majority Parts I–III and plurality Parts IV–V; section-level review required.'
 section=json.loads((RAW/'text'/(sid+'-sections.json')).read_text())
 text=section['majority_text']
 if status=='included' and (not text or section['start'] is None):raise ValueError('Missing majority '+sid)
 if sid in ('2024-013','2024-016','2024-063'):
  text=text[:text.index('It is so ordered.')+len('It is so ordered.')]
 source={'case_id':cid,'case_name':o['name'],'date_filed':datetime.strptime(r['dateDecision'],'%m/%d/%Y').date().isoformat(),'is_source':'True','is_sample_source':'True','us_citation':cite_text(key),'cap_id':'','id_namespace':'us_reports','url':o['url'],'term':'2024','scdb_id':sid,'issue_area':r['issueArea'],'decision_type':r['decisionType']}
 case_review.append({'scdb_id':sid,'case_id':cid,'case_name':o['name'],'status':status,'reason':reason,'decision_type':r['decisionType'],'date_argument':r['dateArgument'],'us_citation':o['citation'],'url':o['url']})
 if status!='included':continue
 nodes[cid]=source;source_rows[sid]=source
 bodyfile=RAW/'text'/(sid+'-body.json')
 body=json.loads(bodyfile.read_text())['majority_body_text'] if bodyfile.exists() else ''
 streams=[('page_order',text),('body_flow',body)]
 found=[]
 for method,t in streams:
  for k,m in refs(t):
   found.append((k,m,method,t))
  for m in re.finditer(r'\b\d{1,3}\s+U\.\s*S\.\s+[_—–]{2,}',t):
   reviews.append({'source_case_id':cid,'source_case_name':o['name'],'citation_text':normalize(m[0]),'reason':'unpaginated_citation_needs_review','context':normalize(t[max(0,m.start()-180):m.end()+120]),'method':method})
 for k,m,method,t in found:
  correction=None
  if sid=='2024-062' and k=='599:799' and 'Hui' in t[max(0,m.start()-60):m.start()]:
   correction='Hui v. Castaneda is 559 U.S. 799 (2010); official source prints 599. Verified against 559 bound-volume index and Justia case.'
   k='559:799'
  if k==key:continue
  context=normalize(t[max(0,m.start()-200):m.end()+100])
  target,problem=resolve(k)
  if not problem and target['date_filed']>source['date_filed']:problem='target_date_after_source'
  if problem:
   reviews.append({'source_case_id':cid,'source_case_name':o['name'],'citation_text':cite_text(k),'reason':problem,'context':context,'method':method})
   if int(k.split(':')[0])<580 and not (RAW/'indexes'/('cap-'+k.split(':')[0]+'.json')).exists():needed_volumes.add(int(k.split(':')[0]))
   continue
  tid=legacy.get(k,{}).get('case_id','us:'+k)
  if tid not in nodes:
   nodes[tid]={'case_id':tid,'case_name':target['case_name'],'date_filed':target['date_filed'],'is_source':'False','is_sample_source':'False','us_citation':cite_text(k),'cap_id':target.get('cap_id',''),'id_namespace':legacy.get(k,{}).get('id_namespace','us_reports'),'url':target['url'],'term':'','scdb_id':'','issue_area':'','decision_type':''}
  edges.add((cid,tid))
  evidence.append({'citing_case':cid,'cited_case':tid,'source_scdb_id':sid,'citation_text':normalize(m[0]),'canonical_citation':cite_text(k),'extraction_stream':method,'character_offset':m.start(),'context':context,'target_metadata_source':target['provenance'],'citation_correction':correction})
 opinion_audit.append({'scdb_id':sid,'case_id':cid,'majority_start':section['start'],'next_section':section['end_preview'],'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'body_flow_available':bool(body),'join_statements':section['join_statements'],'majority_characters':len(text)})
# Ensure source flags survive being added as an earlier precedent.
for r in source_rows.values():nodes[r['case_id']]=r
# Keep review entries for distinct source/citation/reason, retaining one context.
reviews=list({(r['source_case_id'],r['citation_text'],r['reason']):r for r in reviews}.values())
def write_csv(name,fields,rows):
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
fields=['case_id','case_name','date_filed','is_source','is_sample_source','us_citation','cap_id','id_namespace','url','term','scdb_id','issue_area','decision_type']
write_csv('cases.csv',fields,sorted(nodes.values(),key=lambda r:r['case_id']))
write_csv('citations.csv',['citing_case','cited_case'],[dict(citing_case=a,cited_case=b) for a,b in sorted(edges)])
write_csv('case_review.csv',list(case_review[0]),case_review)
write_csv('citation_review.csv',['source_case_id','source_case_name','citation_text','reason','context','method'],reviews)
for name,value in [('edge_evidence.json',evidence),('opinion_audit.json',opinion_audit),('needed_volumes.json',sorted(needed_volumes))]:(OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
manifest={'term':2024,'built_at':datetime.now(timezone.utc).isoformat(),'scdb_release':'2025_01','scdb_term_cases':len(roster),'included_source_cases':len(source_rows),'case_review_counts':dict(Counter(r['status'] for r in case_review)),'nodes':len(nodes),'binary_edges':len(edges),'citation_review_counts':dict(Counter(r['reason'] for r in reviews)),'sources_without_edges':[r['case_name'] for r in source_rows.values() if r['case_id'] not in {a for a,b in edges}],'scope':'Same SCDB argued decision types {1,6} as 2004; whole majority/per-curiam opinions only; Hewitt held for mixed majority/plurality sections. Directed binary links to SCOTUS cases, including majority footnotes.','input_method':'Official preliminary-print PDFs; pypdf page-order text plus pdfplumber body flow to bridge page breaks interrupted by footnotes. US Reports and nominative citations resolved via SCDB, official term indexes, and Harvard reporter metadata.','limitations':['Citation parsing and PDF segmentation require audits; unresolved or ambiguous references are logged, not guessed.','Different extraction method from 2004 Harvard opinion_index links; comparisons require source-method sensitivity checks.','Binary edges do not measure agreement, importance, or number of mentions.',
'Only complete US Reports/nominative citations are recognized; short forms alone cannot establish new target identities.','Cited-only nodes have no outgoing citations collected.','DIG per-curiam decisions are included under the same SCDB type/argument rule, and can have zero edges.','Procedural history references are not globally removed; unresolved order citations must be distinguished from missing substantive precedents.'],'source_urls':['https://www.supremecourt.gov/opinions/slipopinion/24','https://scdb.la.psu.edu/data/2025-release-01/','https://static.case.law/'],'input_sha256':{'scdb.zip':hashlib.sha256((PROJECT/'data/term_2004/raw/scdb.zip').read_bytes()).hexdigest(),'term-roster.json':hashlib.sha256((RAW/'term-roster.json').read_bytes()).hexdigest()},'id_policy':'Existing 2004 IDs preserved on exact US citation matches; new nodes use us:volume:first_page. Treat IDs as opaque strings.'}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert len(nodes)==len(set(nodes))
assert all(a in nodes and b in nodes and a!=b for a,b in edges)
assert { (r['citing_case'],r['cited_case']) for r in evidence}==edges
print(json.dumps({k:manifest[k] for k in ['included_source_cases','nodes','binary_edges','case_review_counts','citation_review_counts','sources_without_edges']},indent=2));print('Need older volume metadata:',sorted(needed_volumes))
