#!/usr/bin/env python3
"""Regenerate the offline comparison gallery from the current renderer."""

import html
import json

from render_stitch_article import Renderer
from build_stitch_themes import load
from build_stitch_comparison import build as build_comparison
from stitch_themes import ROOT, LAYOUTS, LAYOUT_NAMES, catalog


def build():
    output = ROOT / "docs/gallery"
    source = (ROOT / "assets/sample-article.md").read_text(encoding="utf-8")
    for theme in catalog():
        for layout in LAYOUTS:
            content = Renderer(theme["id"], layout).render(source)
            # The browser shell is not copied. Charset/viewport are essential when
            # opening a fragment as a standalone file, particularly on mobile.
            page = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>%s · %s</title></head><body style="margin:0;background:#FFFFFF;">%s</body></html>') % (
                        html.escape(theme["name"]), LAYOUT_NAMES[layout], content)
            (output / (theme["id"] + "-" + layout + ".html")).write_text(page, encoding="utf-8")
    data = json.dumps(catalog(), ensure_ascii=False)
    page = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>gzh-article-layout · 公众号主题库</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#F5F5F3;color:#27272A;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}
header{max-width:1440px;margin:auto;padding:40px 24px 20px}h1{font-size:28px;letter-spacing:-1px;margin:0 0 12px}
p{font-size:14px;line-height:1.8;color:#626262;margin:6px 0}.controls{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
button,a{font:inherit}button{cursor:pointer;border:1px solid #D4D4D0;border-radius:6px;padding:8px 12px;background:#fff;color:#333}
button[aria-pressed=true]{background:#27272A;color:white;border-color:#27272A}
.grid{max-width:1440px;margin:auto;padding:0 24px 40px;display:flex;flex-wrap:wrap;gap:24px}
.card{flex:1 1 360px;min-width:0;max-width:440px;background:white;border:1px solid #E4E4E0;border-radius:12px;overflow:hidden}
.bar{display:flex;align-items:center;gap:8px;padding:16px;border-bottom:1px solid #eee}.dot{width:10px;height:10px;border-radius:50%}
.name{font-weight:600;font-size:14px}.slug{font-size:10px;font-family:monospace;color:#777;margin-left:auto}
.row{display:flex;align-items:center;gap:6px;padding:10px 12px;flex-wrap:wrap}.row button{font-size:12px;padding:6px 8px}.row a{font-size:12px;color:#555;margin-left:auto}
iframe{display:block;border:0;width:100%;height:650px;background:white}.scene{padding:12px 16px;font-size:12px;color:#666;border-top:1px solid #eee}
.notice{font-size:12px;color:#777}.status{min-height:22px;color:#444;font-size:12px}
@media(max-width:600px){header{padding-top:24px}.grid{padding:0 12px 24px}.card{max-width:none}h1{font-size:24px}}
</style></head><body>
<header><h1>gzh-article-layout · 公众号排版主题库</h1>
<p>15 套内置配色，3 种章节版式。同一篇原文，比较公众号兼容输出。</p>
<p><strong>使用方法：</strong>先按文章类型选色系，再切换墨规／浮光／素墨；确认风格后，用同一组参数生成正式文章。</p>
<p><a href="../product-guide.md">查看产品使用指南与交付检查清单 →</a></p>
<p class="notice">墨规：编号微标尺 · 浮光：透叠大数字 · 素墨：克制留白。原稿已转换为内联样式；这里不使用 Tailwind 或外部字体。</p>
<p><a href="comparison.html">查看来源设计稿逐项对照（同文同色） →</a></p>
<p class="notice">下方按当前默认规则生成：未提供作者时不显示名片；有作者时，简介和真实二维码按实际提供内容展示，不输出占位信息。</p>
<div class="controls"><button type="button" data-all="default" aria-pressed="true">色系默认版式</button>
<button type="button" data-all="ruler" aria-pressed="false">全部墨规</button>
<button type="button" data-all="overprint" aria-pressed="false">全部浮光</button>
<button type="button" data-all="pure" aria-pressed="false">全部素墨</button></div>
<p class="status" role="status" id="status"></p></header><main class="grid" id="grid"></main>
<script>
const themes=THEME_DATA;
const names={ruler:'墨规',overprint:'浮光',pure:'素墨'};
const cards=new Map();
function setLayout(theme,layout){
 const card=cards.get(theme.id);
 card.dataset.layout=layout;
 card.querySelector('iframe').src=theme.id+'-'+layout+'.html';
 card.querySelector('a').href=theme.id+'-'+layout+'.html';
 card.querySelectorAll('[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.layout===layout)));
}
function copyCard(card){
 const frame=card.querySelector('iframe');
 let content;
 try{content=frame.contentDocument&&frame.contentDocument.body;}catch(e){}
 if(!content){document.getElementById('status').textContent='无法读取本地画框：请使用本地 HTTP 服务，或打开正文后手动复制。';return;}
 const markup=content.innerHTML,text=content.innerText;
 const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.left='-9999px';
 const handler=e=>{if(e.clipboardData){e.clipboardData.setData('text/html',markup);e.clipboardData.setData('text/plain',text);e.preventDefault();}};
 document.addEventListener('copy',handler,{once:true});document.body.appendChild(area);area.select();
 let ok=false;try{ok=document.execCommand('copy');}finally{area.remove();document.removeEventListener('copy',handler);}
 document.getElementById('status').textContent=ok?'已复制当前主题正文，可以粘贴到公众号编辑器。':'复制被浏览器阻止，请打开正文后手动复制。';
}
themes.forEach(theme=>{
 const card=document.createElement('article');card.className='card';
 const bar=document.createElement('div');bar.className='bar';
 const dot=document.createElement('span');dot.className='dot';dot.style.background=theme.primary;
 const name=document.createElement('span');name.className='name';name.textContent=theme.name;
 const slug=document.createElement('span');slug.className='slug';slug.textContent=theme.id;
 bar.append(dot,name,slug);
 const row=document.createElement('div');row.className='row';
 Object.keys(names).forEach(layout=>{const b=document.createElement('button');b.type='button';b.dataset.layout=layout;b.textContent=names[layout];b.onclick=()=>setLayout(theme,layout);row.append(b);});
 const copy=document.createElement('button');copy.type='button';copy.textContent='复制正文';copy.onclick=()=>copyCard(card);row.append(copy);
 const link=document.createElement('a');link.textContent='打开正文 ↗';link.target='_blank';row.append(link);
 const frame=document.createElement('iframe');frame.title=theme.name;frame.loading='lazy';
 const scene=document.createElement('div');scene.className='scene';scene.textContent=theme.scene;
 card.append(bar,row,frame,scene);cards.set(theme.id,card);document.getElementById('grid').append(card);setLayout(theme,theme.layout);
});
document.querySelectorAll('[data-all]').forEach(button=>button.onclick=()=>{
 document.querySelectorAll('[data-all]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
 themes.forEach(theme=>setLayout(theme,button.dataset.all==='default'?theme.layout:button.dataset.all));
});
</script></body></html>
""".replace("THEME_DATA", data)
    (output / "index.html").write_text(page, encoding="utf-8")
    build_comparison()
    print("Generated 45 validated article fragments and offline theme comparison gallery.")


if __name__ == "__main__":
    build()
