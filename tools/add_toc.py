#!/usr/bin/env python3
"""Add a sticky contents rail to long-form pages.

Builds itself from the h2 elements at load, so headings never go out of sync
with the list. Sits in the left margin on wide screens and hides below 1340 px,
where there is no margin to sit in.

Idempotent: re-running on a page that already has it does nothing, so it is safe
to point at a whole directory.

    python3 tools/add_toc.py research/*/index.html
"""
import sys

MARK = "rheality-toc"

CSS = """
  /* %s: sticky contents rail, built from the h2 elements at load */
  html{scroll-behavior:smooth}
  .wrap h2{scroll-margin-top:26px}
  .toc{position:fixed;top:98px;left:calc(50%% - 658px);width:190px;z-index:20;
    max-height:calc(100vh - 140px);overflow-y:auto}
  .toc::-webkit-scrollbar{width:0}
  .toc-h{font-family:var(--disp);font-weight:700;font-size:10.5px;letter-spacing:.1em;
    text-transform:uppercase;color:var(--mut);margin:0 0 10px 13px}
  .toc a{display:block;font-size:12.6px;line-height:1.38;color:var(--mut);
    text-decoration:none;padding:6px 0 6px 13px;border-left:2px solid var(--line);
    transition:color .14s ease,border-color .14s ease}
  .toc a:hover{color:var(--plum);border-left-color:var(--mut)}
  .toc a.on{color:var(--plum);font-weight:600;border-left-color:var(--terra)}
  @media (max-width:1340px){.toc{display:none}}
""" % MARK

JS = """
<script>
/* %s */
(function(){
  var hs=[].slice.call(document.querySelectorAll('.wrap h2'));
  if(hs.length<3)return;
  var nav=document.createElement('nav');
  nav.className='toc';
  nav.setAttribute('aria-label','Contents');
  nav.innerHTML='<div class="toc-h">Contents</div>';
  var links=hs.map(function(h,i){
    if(!h.id)h.id='sec-'+i;
    /* headings may carry an eyebrow label; the rail wants the heading itself */
    var c=h.cloneNode(true),eb=c.querySelector('.eyebrow');
    if(eb)eb.parentNode.removeChild(eb);
    var a=document.createElement('a');
    a.href='#'+h.id;
    a.textContent=c.textContent.trim();
    nav.appendChild(a);
    return a;
  });
  document.body.appendChild(nav);
  function update(){
    var y=window.scrollY+140,cur=0;
    for(var i=0;i<hs.length;i++){if(hs[i].offsetTop<=y)cur=i;}
    for(var j=0;j<links.length;j++){
      if(j===cur)links[j].classList.add('on');else links[j].classList.remove('on');
    }
  }
  window.addEventListener('scroll',update,{passive:true});
  window.addEventListener('resize',update);
  update();
})();
</script>
""" % MARK


def inject(path):
    html = open(path, encoding="utf-8").read()
    if MARK in html:
        print(f"  {path}: already has it")
        return False
    if "</style>" not in html or "</body>" not in html:
        print(f"  {path}: no <style> or <body> to hook into, skipped")
        return False
    html = html.replace("</style>", CSS + "</style>", 1)
    html = html.replace("</body>", JS + "</body>", 1)
    open(path, "w", encoding="utf-8").write(html)
    print(f"  {path}: added")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    n = sum(inject(p) for p in sys.argv[1:])
    print(f"{n} page(s) updated")
