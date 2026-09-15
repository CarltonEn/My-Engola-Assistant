(function(){
  "use strict";
  const root=document.documentElement;
  const $=s=>document.querySelector(s);
  const saved=JSON.parse(localStorage.getItem("engola-premium-ui")||"{}");
  const themes={
    mint:["#9cf6d7","#d8f99a"],violet:["#c9b8ff","#f0c8ff"],ice:["#bfe8ff","#d8f6ff"],amber:["#ffd38a","#fff0bd"]
  };
  function apply(){
    const t=themes[saved.theme||"mint"]||themes.mint;
    root.style.setProperty("--engola-accent",t[0]);
    root.style.setProperty("--engola-accent-2",t[1]);
    document.body.classList.toggle("engola-compact",!!saved.compact);
    document.body.classList.toggle("engola-reduced",!!saved.reduced);
  }
  function persist(){localStorage.setItem("engola-premium-ui",JSON.stringify(saved));apply()}
  function ambient(){
    if(saved.ambient===false)return;
    const layer=document.createElement("div");layer.id="engolaAmbient";
    for(let i=0;i<22;i++){
      const p=document.createElement("i");
      p.style.left=(Math.random()*100)+"%";p.style.top=(35+Math.random()*65)+"%";
      p.style.setProperty("--x",(Math.random()*90-45)+"px");
      p.style.setProperty("--d",(8+Math.random()*14)+"s");
      p.style.animationDelay=(-Math.random()*14)+"s";
      layer.appendChild(p);
    }
    document.body.appendChild(layer);
  }
  function customizer(){
    const panel=document.createElement("div");panel.id="engola-customizer";
    panel.innerHTML='<div class="engola-customizer-title">APPEARANCE</div>'+
      '<div class="engola-swatches">'+Object.entries(themes).map(([k,v])=>`<button class="engola-swatch" data-theme="${k}" title="${k}" style="background:linear-gradient(135deg,${v[0]},${v[1]})"></button>`).join("")+'</div>'+
      '<label class="engola-customizer-row">Ambient motion <input class="engola-toggle" id="engolaAmbientToggle" type="checkbox" '+(saved.ambient!==false?"checked":"")+'></label>'+
      '<label class="engola-customizer-row">Compact layout <input class="engola-toggle" id="engolaCompactToggle" type="checkbox" '+(saved.compact?"checked":"")+'></label>';
    document.body.appendChild(panel);
    panel.querySelectorAll("[data-theme]").forEach(b=>b.onclick=()=>{saved.theme=b.dataset.theme;persist()});
    $("#engolaAmbientToggle").onchange=e=>{saved.ambient=e.target.checked;persist();location.reload()};
    $("#engolaCompactToggle").onchange=e=>{saved.compact=e.target.checked;persist()};
    const search=$(".search"), topRight=$(".topRight");
    if(topRight){
      const b=document.createElement("button");b.className="lock";b.type="button";b.textContent="✦";
      b.title="Customize appearance";b.setAttribute("aria-label","Customize appearance");
      b.onclick=()=>panel.classList.toggle("open");topRight.insertBefore(b,topRight.firstChild);
    }
  }
  function enhance(){
    apply();ambient();customizer();
    document.querySelectorAll(".nav button,.lock,.authbtn,.mic,.send").forEach(b=>{
      b.addEventListener("pointerdown",()=>b.style.transform="scale(.97)");
      b.addEventListener("pointerup",()=>b.style.transform="");
      b.addEventListener("pointerleave",()=>b.style.transform="");
    });
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",enhance);else enhance();
})();
