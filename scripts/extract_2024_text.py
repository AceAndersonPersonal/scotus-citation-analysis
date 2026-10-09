"""Extract majority text from cached official PDFs; requires requirements-data.txt.

Uses page-order text for footnotes and a supplementary body flow for page breaks.
This is specific to the cached preliminary-print PDF layout, not a generic parser.
"""
import json,re
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]/'data/term_2024'
out=ROOT/'raw/text';out.mkdir(exist_ok=True)
results=[]
for item in json.loads((ROOT/'raw/term-roster.json').read_text()):
 sid=item['scdb']['caseId'];p=out/(sid+'.json')
 if p.exists():pages=json.loads(p.read_text())
 else:
  pages=[page.extract_text() for page in PdfReader(ROOT/'raw/pdf'/(sid+'.pdf')).pages]
  p.write_text(json.dumps(pages,ensure_ascii=False))
 parts=[];headers=[]
 for n,text in enumerate(pages):
  text=text.replace('Page Proof Pending Publication','')
  lines=text.strip().splitlines()
  header=''
  for i,line in enumerate(lines[:8]):
   if re.search(r'^(?:Opinion of |Per Curiam$|Syllabus$|Appendix to opinion of the Court$|[A-Z][a-z]+, (?:J\.|C\. J\.),|Reporter’s Note)',line.strip()):
    header=line.strip();lines=lines[i+1:];break
  headers.append(header)
  parts.append('\n'.join(lines))
 full=re.sub(r'(?<=[A-Za-z])[-\u00ad]\s*\n\s*(?=[A-Za-z])', '', '\n'.join(parts))
 start=re.search(r'(?:Justice|Chief Justice)\s+[A-Z][a-z]+\s+(?:delivered|announced)\s+(?:the|an)\s+opinion[^.]*\.',full)
 if start is None: start=re.search(r'(?m)^Per Curiam\.',full)
 ending=None
 if start:
  endings=list(re.finditer(r'(?m)^(?:Justice|Chief Justice)\s+[A-Z][a-z]+\b[^.]{0,350}?\b(?:concurring|dissenting)\b',full[start.end():]))
  if endings: ending=start.end()+endings[0].start()
  else:
   end=full.find('The attached opinion has been revised',start.end());ending=end if end!=-1 else len(full)
  selected=full[start.start():ending]
 else:selected=''
 joins=[]
 for m in re.finditer(r'\b[A-Z][a-z]+, (?:J\.|C\. J\.), (?:delivered|announced)',full):joins.append(full[m.start():m.start()+1000])
 record={'scdb_id':sid,'name':item['official']['name'],'start':start[0] if start else None,'end_preview':full[ending:ending+200] if ending else None,'majority_text':selected,'page_headers':headers,'join_statements':joins,'full_text':full}
 (out/(sid+'-sections.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
 results.append({k:record[k] for k in ['scdb_id','name','start','end_preview','join_statements']})
 print(sid,item['official']['name'],len(pages),'pages',len(selected),'chars',repr(record['start']),flush=True)
(ROOT/'raw/section-review.json').write_text(json.dumps(results,indent=2))

import json,re
from pathlib import Path
import pdfplumber
ROOT=Path(__file__).resolve().parents[1]/'data/term_2024'
for item in json.loads((ROOT/'raw/term-roster.json').read_text()):
 s=item['scdb'];sid=s['caseId'];dest=ROOT/'raw/text'/(sid+'-body.json')
 if not s['dateArgument'] or s['decisionType'] not in ['1','6'] or sid=='2024-024':continue
 pages=[]
 with pdfplumber.open(ROOT/'raw/pdf'/(sid+'.pdf')) as pdf:
  for n,page in enumerate(pdf.pages):
   text=page.filter(lambda c:c.get('object_type')=='char' and 10<float(c.get('size',0))<14 and c.get('top',0)>155).extract_text() or ''
   pages.append(text)
 full=re.sub(r'(?<=[A-Za-z])[-\u00ad]\s*\n\s*(?=[A-Za-z])','','\n'.join(pages))
 start=re.search(r'(?:Justice|Chief Justice)\s+[A-Z][a-z]+\s+delivered\s+the\s+opinion\s+of\s+the\s+Court\.',full)
 if not start:start=re.search(r'(?m)^Per Curiam\.',full)
 if not start:raise ValueError('No body start '+sid)
 tail=full[start.start():]
 ends=list(re.finditer(r'(?m)^(?:Justice|Chief Justice)\s+[A-Z][a-z]+\b[^.]{0,350}?\b(?:concurring|dissenting)\b',tail[start.end()-start.start():]))
 if ends:tail=tail[:start.end()-start.start()+ends[0].start()]
 # Body flow excludes footnotes: trim post-opinion counsel and back matter.
 ends=list(re.finditer(r'It is so ordered\.',tail))
 if ends:tail=tail[:ends[-1].end()]
 dest.write_text(json.dumps({'majority_body_text':tail,'pages':pages,'method':'pdfplumber body font size >10 and <14, top>155; separate opinion and disposition boundaries'},ensure_ascii=False))
 print(sid,len(tail),flush=True)
