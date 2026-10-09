"""Cache the official 2024-term PDFs matched to the SCDB citation-centered roster."""
import csv,io,json,re,zipfile,hashlib,time
from datetime import datetime,timezone
from html import unescape
from pathlib import Path
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor,as_completed
PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT/'data/term_2024'
raw=ROOT/'raw'; (raw/'pdf').mkdir(parents=True,exist_ok=True)
index_file=raw/'official2024.html'
if not index_file.exists():
 with urlopen(Request('https://www.supremecourt.gov/opinions/slipopinion/24',headers={'User-Agent':'SCOTUS citation research (educational)'}),timeout=60) as response:
  index_file.write_bytes(response.read())
with zipfile.ZipFile(PROJECT/'data/term_2004/raw/scdb.zip') as z:
 n=next(n for n in z.namelist() if n.endswith('.csv'))
 roster=[r for r in csv.DictReader(io.StringIO(z.read(n).decode('utf-8-sig'))) if r['term']=='2024']
def clean(x):return re.sub(r'\s+',' ',unescape(re.sub('<[^>]*>','',x))).strip()
index=[]
for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',(raw/'official2024.html').read_text(),re.S):
 cells=re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)
 if len(cells)!=6: continue
 link=re.search(r"href=['\"](/opinions/24pdf/[^'\"]+)",cells[3])
 if not link:continue
 index.append(dict(zip(['number','date','docket','name','author','citation'],map(clean,cells)),url='https://www.supremecourt.gov'+link[1]))
(raw/'official-index.json').write_text(json.dumps(index,indent=2))
matched=[]
for r in roster:
 hits=[i for i in index if i['docket']==r['docket'] and datetime.strptime(i['date'],'%m/%d/%y').date()==datetime.strptime(r['dateDecision'],'%m/%d/%Y').date()]
 if len(hits)!=1:raise ValueError((r['caseName'],r['docket'],hits))
 matched.append({'scdb':r,'official':hits[0]})
(raw/'term-roster.json').write_text(json.dumps(matched,indent=2))
print('Matched',len(matched),'SCDB cases to',len(index),'official opinion rows',flush=True)
def get(item):
 name=item['scdb']['caseId']; path=raw/'pdf'/(name+'.pdf');url=item['official']['url']
 if not path.exists():
  for attempt in range(3):
   try:
    with urlopen(Request(url,headers={'User-Agent':'SCOTUS citation research (educational)'}),timeout=60) as f:data=f.read()
    if not data.startswith(b'%PDF'):raise ValueError('Not a PDF')
    path.write_bytes(data);break
   except Exception:
    if attempt==2:raise
    time.sleep(3*(attempt+1))
 return {'scdb_id':name,'url':url,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
results=[]
with ThreadPoolExecutor(max_workers=3) as pool:
 for f in as_completed([pool.submit(get,r) for r in matched]):
  results.append(f.result())
  if len(results)%10==0:print('Cached',len(results),'PDFs',flush=True)
(raw/'downloads.json').write_text(json.dumps({'cache_verified_at':datetime.now(timezone.utc).isoformat(),'files':sorted(results,key=lambda r:r['scdb_id'])},indent=2))
print('Done:',len(results),'official PDFs',flush=True)
