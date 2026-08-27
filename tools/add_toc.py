#!/usr/bin/env python3
"""Add a sticky contents rail to long-form pages.

Builds itself from the h2 elements on screen, so headings never drift out of
sync with the list. Sits in the left margin on wide screens, hides below 1340 px
where there is no margin to sit in.

Some demos live as panels inside one page and toggle with display:none, so the
rail watches for that and rebuilds against whichever panel is showing. Pass
--scope to point it at those panels instead of the whole page:

    python3 tools/add_toc.py research/*/index.html demo/index.html
    python3 tools/add_toc.py --scope '#demo-tg,#demo-hk' index.html

Idempotent. Re-running replaces the existing rail rather than stacking a second
one, so it is safe to re-point at pages that already have it.
"""
import re
import sys

MARK = "rheality-toc"

CSS = """
  /* %s: sticky contents rail, built from the h2 elements on screen */
  html{scroll-behavior:smooth}
  h2{scroll-margin-top:26px}
  .toc{position:fixed;top:98px;left:calc(50%% - 658px);width:190px;z-index:20;
    max-height:calc(100vh - 140px);overflow-y:auto}
  .toc::-webkit-scrollbar{width:0}
  .toc-h{font-family:var(--disp,Georgia,serif);font-weight:700;font-size:10.5px;
    letter-spacing:.1em;text-transform:uppercase;color:var(--mut,#6F6488);
    margin:0 0 10px 13px}
  .toc a{display:block;font-size:12.6px;line-height:1.38;color:var(--mut,#6F6488);
    text-decoration:none;padding:6px 0 6px 13px;
    border-left:2px solid var(--line,#E4DDF1);
    transition:color .14s ease,border-color .14s ease}
  .toc a:hover{color:var(--plum,#33254E);border-left-color:var(--mut,#6F6488)}
  .toc a.on{color:var(--plum,#33254E);font-weight:600;
    border-left-color:var(--terra,#CD5A1F)}
  @media (max-width:1340px){.toc{display:none}}
""" % MARK

JS = """
<script>
/* %s */
(function(){
  var SCOPE=%s;
  var nav=document.createElement('nav');
  nav.className='toc';
  nav.setAttribute('aria-label','Contents');
  document.body.appendChild(nav);
  var hs=[],links=[];
  function vis(el){
    return !!(el.offsetWidth||el.offsetHeight||el.getClientRects().length);
  }
  function top(el){
    return el.getBoundingClientRect().top+window.pageYOffset;
  }
  function build(){
    var root=null,cands=document.querySelectorAll(SCOPE);
    for(var i=0;i<cands.length;i++){if(vis(cands[i])){root=cands[i];break;}}
    hs=root?[].slice.call(root.querySelectorAll('h2')).filter(vis):[];
    if(hs.length<3){nav.style.display='none';links=[];return;}
    nav.style.display='';
    nav.innerHTML='<div class="toc-h">Contents</div>';
    links=hs.map(function(h,i){
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
    update();
  }
  function update(){
    if(!links.length)return;
    var y=window.pageYOffset+140,cur=0;
    for(var i=0;i<hs.length;i++){if(top(hs[i])<=y)cur=i;}
    for(var j=0;j<links.length;j++){
      if(j===cur)links[j].classList.add('on');else links[j].classList.remove('on');
    }
  }
  window.addEventListener('scroll',update,{passive:true});
  window.addEventListener('resize',update);
  /* panels toggle with display:none, so rebuild when one does */
  var t=null;
  function later(){clearTimeout(t);t=setTimeout(build,70);}
  if(window.MutationObserver){
    var mo=new MutationObserver(later),c2=document.querySelectorAll(SCOPE);
    for(var k=0;k<c2.length;k++){
      mo.observe(c2[k],{attributes:true,attributeFilter:['style','class']});
    }
  }
  document.addEventListener('click',later);
  window.addEventListener('hashchange',later);
  build();
})();
</script>
"""


def strip(html):
    """Remove a previously injected rail so re-running replaces rather than stacks."""
    html = re.sub(r"\n  /\* %s.*?@media \(max-width:1340px\)\{\.toc\{display:none\}\}\n"
                  % MARK, "\n", html, flags=re.S)
    html = re.sub(r"\n<script>\n/\* %s \*/.*?</script>\n" % MARK, "\n", html, flags=re.S)
    return html


def inject(path, scope):
    html = open(path, encoding="utf-8").read()
    had = MARK in html
    if had:
        html = strip(html)
        if MARK in html:
            print(f"  {path}: existing rail did not strip cleanly, skipped")
            return False
    if "</style>" not in html or "</body>" not in html:
        print(f"  {path}: no <style> or <body> to hook into, skipped")
        return False
    html = html.replace("</style>", CSS + "</style>", 1)
    html = html.replace("</body>", (JS % (MARK, repr(scope).replace("'", '"'))) + "</body>", 1)
    open(path, "w", encoding="utf-8").write(html)
    print(f"  {path}: {'replaced' if had else 'added'}  scope={scope}")
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    scope = ".wrap"
    if "--scope" in args:
        i = args.index("--scope")
        scope = args[i + 1]
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    n = sum(inject(p, scope) for p in args)
    print(f"{n} page(s) updated")
