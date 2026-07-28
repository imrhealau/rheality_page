/* Rheality portal widget.
   Injects a click-anywhere coverage checker into #portal-widget: Leaflet map
   (lazy-loaded when the widget scrolls near), live queries against the public
   Sentinel archives (ASF radar, Earth Search optical), a monitoring plan sized
   from the archive, and an order mailto carrying the coordinates.
   Self-contained: styles under .ptw-, page provides CSS vars + .btn. */
(function(){
  var root=document.getElementById('portal-widget');
  if(!root||root.dataset.booted) return;
  root.dataset.booted='1';

  var style=document.createElement('style');
  style.textContent=[
    '.ptw-map{height:460px;border-radius:var(--radius);border:1px solid var(--line);',
    '  box-shadow:0 12px 36px rgba(46,31,74,0.12);background:var(--plum-deep);z-index:1}',
    '@media(max-width:640px){.ptw-map{height:360px}}',
    '.ptw-presets{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 4px}',
    '.ptw-chip{font-family:var(--body);font-weight:600;font-size:0.82rem;color:var(--plum);',
    '  background:var(--white);border:1.5px solid var(--line);border-radius:100px;padding:7px 15px;',
    '  cursor:pointer;transition:border-color .15s ease,color .15s ease}',
    '.ptw-chip:hover{border-color:var(--brand);color:var(--brand-deep)}',
    '.ptw-chip:focus-visible{outline:3px solid var(--brand-deep);outline-offset:2px}',
    '.ptw-hint{font-size:0.85rem;color:var(--muted);margin:8px 0 0}',
    '.ptw-results{display:none;margin-top:26px}',
    '.ptw-coords{font-size:0.88rem;color:var(--muted);margin:0 0 14px}',
    '.ptw-coords code{background:rgba(51,37,78,0.06);padding:1px 7px;border-radius:6px;font-size:0.94em}',
    '.ptw-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:0 0 18px}',
    '.ptw-stat{background:var(--white);border:1px solid var(--line);border-radius:16px;padding:18px 20px}',
    '.ptw-stat strong{display:block;font-family:var(--disp);font-weight:700;font-size:1.45rem;',
    '  color:var(--brand-deep);line-height:1.15}',
    '.ptw-stat span{font-size:0.82rem;color:var(--muted);display:block;margin-top:4px}',
    '.ptw-plan-card{background:var(--white);border:1px solid var(--line);border-radius:var(--radius);padding:26px 24px}',
    '.ptw-plan-card h3{font-family:var(--disp);font-size:1.15rem;color:var(--plum);margin:0 0 4px}',
    '.ptw-plan{margin:12px 0 4px;padding-left:20px}',
    '.ptw-plan li{margin-bottom:9px;color:var(--muted);font-size:0.97rem}',
    '.ptw-plan li strong{color:var(--ink)}',
    '.ptw-cta{margin-top:16px}'
  ].join('\n');
  document.head.appendChild(style);

  root.innerHTML=
    '<div class="ptw-map" id="ptw-map" role="application" aria-label="World map. Click a location to check satellite coverage over it."></div>'+
    '<div class="ptw-presets" aria-label="Example sites">'+
      '<button class="ptw-chip" data-lat="30.826" data-lon="111.003">Three Gorges Dam</button>'+
      '<button class="ptw-chip" data-lat="-20.1194" data-lon="-44.1219">Brumadinho tailings dam</button>'+
      '<button class="ptw-chip" data-lat="22.3080" data-lon="113.9185">Hong Kong airport reclamation</button>'+
    '</div>'+
    '<p class="ptw-hint" id="ptw-hint">Or click anywhere on the map. The dashed box is the area one monitoring order covers, about 10 km across.</p>'+
    '<div class="ptw-results" id="ptw-results">'+
      '<p class="ptw-coords" id="ptw-coords"></p>'+
      '<div class="ptw-stats" id="ptw-stats"></div>'+
      '<div class="ptw-plan-card"><h3>What a monitoring order here looks like</h3>'+
      '<ul class="ptw-plan" id="ptw-plan"></ul>'+
      '<div class="ptw-cta"><a class="btn" id="ptw-order" href="#">Request this monitor</a></div></div>'+
    '</div>';

  var booted=false, map=null, dot=null, box=null;

  function boot(){
    if(booted) return; booted=true;
    var css=document.createElement('link');
    css.rel='stylesheet'; css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);
    var js=document.createElement('script');
    js.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload=init;
    js.onerror=function(){ document.getElementById('ptw-hint').textContent='The map library failed to load. Email us coordinates instead and we will run the check for you.'; };
    document.head.appendChild(js);
  }

  // boot when the widget scrolls near (or straight away without IO support)
  if('IntersectionObserver' in window){
    var io=new IntersectionObserver(function(es){
      es.forEach(function(e){ if(e.isIntersecting){ io.disconnect(); boot(); } });
    },{rootMargin:'500px'});
    io.observe(root);
  } else { boot(); }

  function init(){
    map=L.map('ptw-map',{scrollWheelZoom:false,worldCopyJump:true}).setView([23.5,110],4);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {maxZoom:17,attribution:'Imagery &copy; Esri, Maxar, Earthstar Geographics'}).addTo(map);
    map.on('click',function(e){ pick(e.latlng.lat,e.latlng.lng,null); });
    root.querySelectorAll('.ptw-chip').forEach(function(b){
      b.addEventListener('click',function(){
        var la=parseFloat(b.dataset.lat), lo=parseFloat(b.dataset.lon);
        map.setView([la,lo],11);
        pick(la,lo,b.textContent);
      });
    });
  }

  function pick(lat,lon,name){
    var dLat=0.045, dLon=0.045/Math.max(0.2,Math.cos(lat*Math.PI/180));
    if(dot) map.removeLayer(dot);
    if(box) map.removeLayer(box);
    dot=L.circleMarker([lat,lon],{radius:7,color:'#CD5A1F',weight:3,fillColor:'#fff',fillOpacity:1}).addTo(map);
    box=L.rectangle([[lat-dLat,lon-dLon],[lat+dLat,lon+dLon]],
      {color:'#CD5A1F',weight:2,fillOpacity:0.08,dashArray:'6 6'}).addTo(map);

    var res=document.getElementById('ptw-results');
    res.style.display='block';
    document.getElementById('ptw-coords').innerHTML=
      (name?('<strong>'+name+'</strong> &middot; '):'')+
      'Selected point: <code>'+lat.toFixed(4)+', '+lon.toFixed(4)+'</code>';
    document.getElementById('ptw-stats').innerHTML=
      '<div class="ptw-stat"><strong>&hellip;</strong><span>querying the archives over this point</span></div>';
    document.getElementById('ptw-plan').innerHTML='<li>Checking coverage&hellip;</li>';
    res.scrollIntoView({behavior:'smooth',block:'nearest'});

    var s1=fetch('https://api.daac.asf.alaska.edu/services/search/param?platform=SENTINEL-1&processingLevel=SLC'+
        '&start=2023-01-01T00:00:00Z&output=jsonlite&maxResults=400'+
        '&intersectsWith='+encodeURIComponent('POINT('+lon.toFixed(4)+' '+lat.toFixed(4)+')'))
      .then(function(r){ if(!r.ok) throw 0; return r.json(); });
    var since=new Date(); since.setMonth(since.getMonth()-24);
    var s2=fetch('https://earth-search.aws.element84.com/v1/search',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({collections:['sentinel-2-l2a'],
          intersects:{type:'Point',coordinates:[lon,lat]},
          datetime:since.toISOString().slice(0,10)+'T00:00:00Z/..',
          query:{'eo:cloud_cover':{lt:60}},
          sortby:[{field:'properties.datetime',direction:'desc'}],limit:100})})
      .then(function(r){ if(!r.ok) throw 0; return r.json(); });

    Promise.allSettled([s1,s2]).then(function(out){ render(out,lat,lon,name); });
  }

  function render(out,lat,lon,name){
    var stats=[], plan=[], radar=null, optical=null;

    if(out[0].status==='fulfilled'){
      var passes=(out[0].value.results||[]);
      var byTrack={};
      passes.forEach(function(p){
        var k=(p.flightDirection||'?')+' track '+(p.path!=null?p.path:'?');
        (byTrack[k]=byTrack[k]||[]).push(p.startTime||'');
      });
      var bestK=null,bestN=0;
      Object.keys(byTrack).forEach(function(k){ if(byTrack[k].length>bestN){bestN=byTrack[k].length;bestK=k;} });
      var months={};
      (byTrack[bestK]||[]).forEach(function(t){ if(t) months[t.slice(0,7)]=1; });
      var lastYear=(byTrack[bestK]||[]).filter(function(t){
        return t && (new Date()-new Date(t))<366*864e5; }).length;
      radar={total:passes.length,bestK:bestK,bestN:bestN,months:Object.keys(months).length,
             cadence:lastYear?Math.round(365/lastYear):null};
    }
    if(out[1].status==='fulfilled'){
      var d=out[1].value, feats=d.features||[];
      var matched=(d.context&&d.context.matched)!=null?d.context.matched:
                  (d.numberMatched!=null?d.numberMatched:feats.length);
      optical={matched:matched,capped:matched===feats.length&&feats.length===100,
               latest:feats.length?feats[0].properties.datetime.slice(0,10):null};
    }

    if(radar&&radar.total){
      stats.push('<div class="ptw-stat"><strong>'+radar.total+'</strong><span>Sentinel-1 radar passes here since Jan 2023</span></div>');
      stats.push('<div class="ptw-stat"><strong>'+(radar.bestK||'&mdash;')+'</strong><span>best orbit for interferometry ('+radar.bestN+' passes)</span></div>');
      if(radar.cadence) stats.push('<div class="ptw-stat"><strong>~'+radar.cadence+' days</strong><span>current revisit on that orbit</span></div>');
    } else if(radar){
      stats.push('<div class="ptw-stat"><strong>0</strong><span>Sentinel-1 SLC passes found here; radar monitoring needs another data source at this spot</span></div>');
    } else {
      stats.push('<div class="ptw-stat"><strong>?</strong><span>radar archive query failed in-browser; we can run it for you by email</span></div>');
    }
    if(optical){
      stats.push('<div class="ptw-stat"><strong>'+optical.matched+(optical.capped?'+':'')+'</strong><span>Sentinel-2 optical scenes, last 24 months, under 60% cloud</span></div>');
      if(optical.latest) stats.push('<div class="ptw-stat"><strong>'+optical.latest+'</strong><span>most recent optical pass</span></div>');
    } else {
      stats.push('<div class="ptw-stat"><strong>?</strong><span>optical archive query failed in-browser; we can run it for you by email</span></div>');
    }
    document.getElementById('ptw-stats').innerHTML=stats.join('');

    if(radar&&radar.months>=3){
      var epochs=Math.min(radar.months,36), pairs=2*epochs-3;
      plan.push('<li><strong>Radar network:</strong> '+epochs+' monthly epochs on the best orbit, '+pairs+' small-baseline interferograms, processed in the cloud.</li>');
      plan.push('<li><strong>First result:</strong> a millimetre line-of-sight deformation history and velocity for every coherent point in the box, about a day after the order.</li>');
      plan.push('<li><strong>Then:</strong> a new epoch with every pass, delivered as a monthly update with anomaly flags a human has looked at.</li>');
      plan.push('<li><strong>Alongside it:</strong> the optical water and surface-change monitor, which runs in minutes and fills the gaps radar cannot see.</li>');
    } else {
      plan.push('<li>Not enough archived radar passes for a deformation history at this exact spot. Email us the coordinates and we will scope alternatives honestly, including saying no.</li>');
    }
    document.getElementById('ptw-plan').innerHTML=plan.join('');

    try{
      var addr=['rhea.lau','rheality.space'].join('@');
      var sub='Monitoring request: '+lat.toFixed(4)+', '+lon.toFixed(4)+(name?(' ('+name+')'):'');
      var body='Site: '+lat.toFixed(4)+', '+lon.toFixed(4)+'%0A'+
               (radar&&radar.bestK?('Best orbit: '+radar.bestK+', '+radar.bestN+' passes since 2023%0A'):'')+
               'What I want monitored: %0A';
      document.getElementById('ptw-order').href=
        'mailto:'+addr+'?subject='+encodeURIComponent(sub)+'&body='+body;
    }catch(e){}
  }
})();
