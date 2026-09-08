import csv, io, json, os, secrets, sqlite3, time, hashlib, threading, argparse
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from contextlib import contextmanager
from content import CARDS, QUESTIONS

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('MEDIA_DATA', str(ROOT/'data'))); DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'scores.sqlite3'
LOCK=threading.RLock()
KEYFILE=DATA/'teacher-key.txt'
KEY=os.environ.get('TEACHER_KEY','').strip()
if not KEY:
 if os.environ.get('MEDIA_PRODUCTION')=='1': raise RuntimeError('Set TEACHER_KEY in the hosting environment before starting.')
 if not KEYFILE.exists(): KEYFILE.write_text(secrets.token_urlsafe(24),encoding='utf-8')
 KEY=KEYFILE.read_text(encoding='utf-8').strip()
if len(KEY)<24: raise RuntimeError('TEACHER_KEY must contain at least 24 characters.')
@contextmanager
def db():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row
 try:
  with c: yield c
 finally: c.close()
with db() as c:
 c.executescript('CREATE TABLE IF NOT EXISTS rooms(code TEXT PRIMARY KEY, state TEXT, deadline REAL); CREATE TABLE IF NOT EXISTS players(token TEXT PRIMARY KEY, room TEXT, student TEXT, nickname TEXT, idx INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, score INTEGER DEFAULT 0, attempts TEXT DEFAULT \'{}\', answers TEXT DEFAULT \'[]\', UNIQUE(room,student));')
FORMS='https://forms.cloud.microsoft/Pages/ResponsePage.aspx'
FORM_ID='gnzLDoQbNkut7yCBtcESW4n4816a8PBCjVoi3DfBlG1URTFPNlgxRDFIMVRJSDMxRFkzWjZCS0hKOCQlQCNjPTEu'
def room(c,code):
 r=c.execute('SELECT * FROM rooms WHERE code=?',(code,)).fetchone()
 if not r: raise ValueError('ไม่พบรหัสห้อง')
 if r['state']=='playing' and time.time()>=r['deadline']:
  c.execute("UPDATE rooms SET state='closed' WHERE code=?",(code,)); r=c.execute('SELECT * FROM rooms WHERE code=?',(code,)).fetchone()
 return r
def released(c,r):
 return r['state']=='closed' or (r['state']=='playing' and c.execute('SELECT COUNT(*) FROM players WHERE room=? AND idx<?',(r['code'],len(QUESTIONS))).fetchone()[0]==0)
def public_q(q, token):
 out={k:v for k,v in q.items() if k not in ('correct','why')}
 # Stable per-player option order; option IDs remain canonical on server.
 for name in ('actions','reasons'):
  out[name]=sorted([{'id':i,'text':s} for i,s in enumerate(q[name])], key=lambda x:hashlib.sha256((token+q['id']+name+str(x['id'])).encode()).hexdigest())
 return out
def snapshot(c,p):
 r=room(c,p['room']); done=p['idx']>=len(QUESTIONS); reveal=released(c,r)
 result={'room':p['room'],'student':p['student'],'nickname':p['nickname'],'index':p['idx'],'total':len(QUESTIONS),'xp':p['xp'] if reveal else p['xp']-p['score']*100,'state':r['state'],'deadline':r['deadline'],'done':done,'released':reveal,'cards':CARDS}
 if r['state']=='playing' and not done: result['question']=public_q(QUESTIONS[p['idx']],p['token'])
 if done or reveal:
  result['waiting']=not reveal
 if reveal:
  result['score']=p['score']
  result['review']=[{'title':q['title'],'why':q['why'],'law':CARDS[q['card']]['law'],'action':q['actions'][q['correct'][0]],'reason':q['reasons'][q['correct'][1]],'earned':next((a['points'] for a in json.loads(p['answers']) if a['id']==q['id']),0)} for q in QUESTIONS if q['phase']=='ประเมิน']
  result['forms']=FORMS+'?'+urlencode({'id':FORM_ID,'rf3e987bb0a78489893ef3ffd18583225':p['student'],'rc3482652eb70493cb348b6ae23fa8a4f':p['nickname'],'r8c0b4335a7724aa2bb8a137f6e12a608':p['score']})
 rows=[dict(x) for x in c.execute('SELECT nickname,xp,score FROM players WHERE room=?',(p['room'],))]
 for x in rows:
  if not reveal: x['xp']-=x['score']*100
 rows.sort(key=lambda x:(-x['xp'],x['nickname']))
 result['leaderboard']=[{'nickname':x['nickname'],'xp':x['xp'],'rank':1+sum(y['xp']>x['xp'] for y in rows)} for x in rows]
 return result
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def send(self,data,status=200,ctype='application/json; charset=utf-8'):
  raw=json.dumps(data,ensure_ascii=False).encode() if isinstance(data,(dict,list)) else data
  self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer'); self.end_headers(); self.wfile.write(raw)
 def auth(self):
  if not secrets.compare_digest(self.headers.get('X-Teacher-Key',''),KEY): raise PermissionError('รหัสอาจารย์ไม่ถูกต้อง')
 def do_GET(self):
  try:
   path=urlparse(self.path).path
   if path=='/healthz':
    with db() as c: c.execute('SELECT 1').fetchone()
    return self.send({'status':'ok'})
   if path in ('/','/admin'):
    return self.send((ROOT/'index.html').read_bytes(),ctype='text/html; charset=utf-8')
   if path in ('/app.js','/style.css','/background.js'):
    return self.send((ROOT/path[1:]).read_bytes(),ctype='text/css' if path.endswith('.css') else 'text/javascript')
   with LOCK, db() as c:
    if path=='/api/state':
     p=c.execute('SELECT * FROM players WHERE token=?',(self.headers.get('Authorization',''),)).fetchone()
     if not p: raise PermissionError('กรุณาเข้าห้องเกมอีกครั้ง')
     return self.send(snapshot(c,p))
    if path in ('/api/admin','/api/export'):
     self.auth()
     for r in c.execute('SELECT * FROM rooms').fetchall(): room(c,r['code'])
     rows=[dict(x) for x in c.execute('SELECT room,student,nickname,idx,xp,score FROM players ORDER BY room,score DESC')]
     if path.endswith('export'):
      s=io.StringIO(); w=csv.writer(s); w.writerow(['room','student','nickname','progress','game_points','grade_out_of_10'])
      for r in rows: w.writerow([("'"+str(v)) if str(v).startswith(('=','+','-','@','\t','\r')) else v for v in r.values()])
      return self.send(('\ufeff'+s.getvalue()).encode(),ctype='text/csv; charset=utf-8')
     return self.send({'rooms':[dict(x) for x in c.execute('SELECT * FROM rooms')],'players':rows})
   self.send({'error':'ไม่พบหน้า'},404)
  except PermissionError as e: self.send({'error':str(e)},403)
  except ValueError as e: self.send({'error':str(e)},400)
 def do_POST(self):
  try:
   origin=self.headers.get('Origin')
   if origin and urlparse(origin).netloc!=self.headers.get('Host'): raise PermissionError('คำขอต่างเว็บไซต์ไม่ได้รับอนุญาต')
   if not self.headers.get('Content-Type','').startswith('application/json'): raise ValueError('ต้องเป็น JSON')
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<16000: raise ValueError('คำขอไม่ถูกต้อง')
   b=json.loads(self.rfile.read(length)); path=urlparse(self.path).path
   if not isinstance(b,dict): raise ValueError('ต้องเป็น JSON object')
   with LOCK, db() as c:
    if path=='/api/join':
     code=str(b.get('room','')).strip().upper(); sid=str(b.get('student','')).strip(); nick=str(b.get('nickname','')).strip()
     if not sid or not nick or len(sid)>40 or len(nick)>32: raise ValueError('กรอกรหัสนักศึกษาและชื่อเล่นไม่เกิน 32 ตัวอักษร')
     r=room(c,code)
     if r['state']!='lobby': raise ValueError('ห้องเริ่มแล้วหรือปิดแล้ว ให้อาจารย์สร้างรอบใหม่')
     token=secrets.token_urlsafe(32)
     try: c.execute('INSERT INTO players(token,room,student,nickname) VALUES(?,?,?,?)',(token,code,sid,nick))
     except sqlite3.IntegrityError: raise ValueError('รหัสนักศึกษานี้เข้าห้องแล้ว โปรดใช้เครื่องเดิม หรือให้อาจารย์ช่วยกู้สิทธิ์')
     return self.send({'token':token})
    if path=='/api/answer':
     p=c.execute('SELECT * FROM players WHERE token=?',(self.headers.get('Authorization',''),)).fetchone()
     if not p: raise PermissionError('กรุณาเข้าห้องเกม')
     r=room(c,p['room'])
     if r['state']!='playing' or p['idx']>=len(QUESTIONS): raise ValueError('รอบนี้ไม่รับคำตอบแล้ว')
     q=QUESTIONS[p['idx']]
     if b.get('id')!=q['id']: raise ValueError('คำตอบนี้บันทึกแล้ว กรุณาโหลดสถานะล่าสุด')
     a=b.get('action'); reason=b.get('reason')
     if type(a)!=int or type(reason)!=int or not 0<=a<len(q['actions']) or not 0<=reason<len(q['reasons']): raise ValueError('เลือกคำตอบทั้งสองขั้น')
     ac=a==q['correct'][0]; rc=reason==q['correct'][1]; points=int(ac)+int(rc)
     attempts=json.loads(p['attempts']); count=attempts.get(q['id'],0); attempts[q['id']]=count+1
     exam=q['phase']=='ประเมิน'; advance=exam or points==2
     xp=(points*100 if exam else (150 if count==0 else 100) if advance else 0)
     answers=json.loads(p['answers'])
     if advance: answers.append({'id':q['id'],'action':a,'reason':reason,'points':points,'tries':count+1})
     c.execute('UPDATE players SET idx=?,xp=xp+?,score=score+?,attempts=?,answers=? WHERE token=?',(p['idx']+int(advance),xp,points if exam else 0,json.dumps(attempts),json.dumps(answers),p['token']))
     result={'saved':True,'advance':advance}
     if not exam: result.update({'actionCorrect':ac,'reasonCorrect':rc,'why':q['why'],'law':CARDS[q['card']]['law'],'xp':xp})
     return self.send(result)
    if path.startswith('/api/admin/'):
     self.auth()
     if path.endswith('create'):
      code=secrets.token_hex(3).upper(); c.execute("INSERT INTO rooms VALUES(?,'lobby',0)",(code,)); return self.send({'room':code})
     code=str(b.get('room','')); r=room(c,code)
     if path.endswith('start'):
      if r['state']!='lobby': raise ValueError('ห้องนี้เริ่มแล้ว')
      if c.execute('SELECT COUNT(*) FROM players WHERE room=?',(code,)).fetchone()[0]==0: raise ValueError('รอให้นักศึกษาเข้าห้องก่อน')
      minutes=int(b.get('minutes',40))
      if minutes not in (30,40,45): raise ValueError('เวลาไม่ถูกต้อง')
      c.execute("UPDATE rooms SET state='playing',deadline=? WHERE code=?",(time.time()+minutes*60,code))
     elif path.endswith('close'): c.execute("UPDATE rooms SET state='closed' WHERE code=?",(code,))
     elif path.endswith('recover'):
      sid=str(b.get('student','')); newtoken=secrets.token_urlsafe(32)
      updated=c.execute('UPDATE players SET token=? WHERE room=? AND student=?',(newtoken,code,sid))
      if not updated.rowcount: raise ValueError('ไม่พบรหัสนักศึกษา')
      return self.send({'token':newtoken})
     else: raise ValueError('ไม่พบคำสั่ง')
     return self.send({'ok':True})
   self.send({'error':'ไม่พบคำสั่ง'},404)
  except PermissionError as e: self.send({'error':str(e)},403)
  except (ValueError,TypeError,KeyError) as e: self.send({'error':str(e)},400)
  except Exception: self.send({'error':'ระบบบันทึกไม่สำเร็จ โปรดลองอีกครั้ง'},500)
if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--host',default='127.0.0.1'); ap.add_argument('--port',type=int,default=int(os.environ.get('PORT','8765'))); a=ap.parse_args()
 print(f'Media Mission: http://{a.host}:{a.port} | Teacher: /admin',flush=True)
 print('Teacher key is stored in data/teacher-key.txt (not served by HTTP).',flush=True)
 ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
