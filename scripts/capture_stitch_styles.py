#!/usr/bin/env python3
"""Optional local QA: capture original computed styles via isolated Chrome.
Requires websocket-client and Chrome; does not read MCP credentials.
Run --viewport 390, then --viewport 677; refresh frozen provenance afterwards.
"""
import json, subprocess, tempfile, time, urllib.request, threading, http.server, pathlib, websocket, argparse, os
args=argparse.ArgumentParser()
args.add_argument('--viewport',type=int,choices=(390,677),default=390)
args=args.parse_args()
width=args.viewport
suffix='-desktop' if width==677 else ''
ROOT=pathlib.Path(__file__).resolve().parent.parent
class H(http.server.SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
 def log_message(self,*a):pass
s=http.server.ThreadingHTTPServer(('127.0.0.1',8765),H);threading.Thread(target=s.serve_forever,daemon=True).start()
p=subprocess.Popen(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--proxy-server='+os.environ.get('STITCH_HTTPS_PROXY','http://127.0.0.1:7897'),'--remote-debugging-port=9227','--remote-allow-origins=http://localhost:9227','--user-data-dir='+tempfile.mkdtemp(),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for i in range(100):
  try: tabs=json.load(urllib.request.urlopen('http://localhost:9227/json'));break
  except:time.sleep(.1)
 ws=websocket.create_connection(tabs[0]['webSocketDebuggerUrl'],origin='http://localhost:9227');seq=0
 def call(method,params={}):
  global seq
  seq+=1;ws.send(json.dumps(dict(id=seq,method=method,params=params)))
  while True:
   r=json.loads(ws.recv())
   if r.get('id')==seq:return r.get('result',{})
 def ev(js):return call('Runtime.evaluate',dict(expression=js,returnByValue=True)).get('result',{}).get('value')
 call('Page.enable')
 for slug in ['ruler','overprint','pure','components']:
  call('Emulation.setDeviceMetricsOverride',dict(width=width,height=844,deviceScaleFactor=1,mobile=True))
  call('Page.navigate',dict(url='http://127.0.0.1:8765/assets/stitch/'+slug+'.html'))
  for i in range(120):
   time.sleep(.5)
   if ev("document.querySelector('main')&&getComputedStyle(document.querySelector('main')).display==='flex'&&document.fonts.status==='loaded'"):break
  print(slug,ev("({ready:document.readyState,styles:document.styleSheets.length,fonts:document.fonts.status,primary:getComputedStyle(document.querySelector('.bg-primary')).backgroundColor})"),flush=True)
  js="""JSON.stringify(Array.from(document.querySelectorAll('main, main *')).map(e=>{let s=getComputedStyle(e);let props=['color','background-color','background-image','font-size','line-height','letter-spacing','font-weight','font-family','display','flex-direction','flex','flex-shrink','align-items','justify-content','gap','padding-top','padding-right','padding-bottom','padding-left','margin-top','margin-bottom','border-radius','border-top-width','border-top-color','border-right-width','border-right-color','border-bottom-width','border-bottom-color','border-left-width','border-left-color','box-shadow','opacity'];return {tag:e.tagName.toLowerCase(),class:e.getAttribute('class')||'',inline:e.getAttribute('style')||'',text:e.textContent.trim().slice(0,80),css:Object.fromEntries(props.map(p=>[p,s.getPropertyValue(p)])),rect:{width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}}}))"""
  (ROOT/'assets/stitch'/('resolved-'+slug+suffix+'.json')).write_text(ev(js),encoding='utf8')
  # Generated stylesheet, excluding external fonts, for reproducible cascade inspection.
  css=ev("Array.from(document.querySelectorAll('style')).map(s=>s.textContent).join('\\n')")
  (ROOT/'assets/stitch'/('resolved-'+slug+suffix+'.css')).write_text(css,encoding='utf8')
  import base64
  shot=call('Page.captureScreenshot',dict(format='png',captureBeyondViewport=True))
  pathlib.Path('/tmp/source-'+slug+suffix+'.png').write_bytes(base64.b64decode(shot['data']))
 p_manifest=ROOT/'assets/stitch/resolved-manifest.json'
 audit=json.loads(p_manifest.read_text())
 import hashlib
 for slug in ['ruler','overprint','pure','components']:
  for ext in ['json','css']:
   f=ROOT/'assets/stitch'/('resolved-'+slug+suffix+'.'+ext)
   audit['sources'][slug][f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
 p_manifest.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
finally:p.terminate();s.shutdown()
