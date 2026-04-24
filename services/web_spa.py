"""Single-page React app — AlphaFutures dashboard."""

from __future__ import annotations

import pathlib

_TWEAKS_CSS = r"""
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:2147483646;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:default;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;scrollbar-width:thin}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}
  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}
  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2)}
  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;
    background:rgba(255,255,255,.9);box-shadow:0 1px 2px rgba(0,0,0,.12);transition:left .15s,width .15s}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;height:22px;border-radius:6px;cursor:default;padding:0}
  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:default;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}
  .twk-swatch{appearance:none;-webkit-appearance:none;width:56px;height:22px;
    border:.5px solid rgba(0,0,0,.1);border-radius:6px;padding:0;cursor:default;background:transparent;flex-shrink:0}
  .twk-swatch::-webkit-color-swatch-wrapper{padding:0}
  .twk-swatch::-webkit-color-swatch{border:0;border-radius:5.5px}
"""

_TWEAKS_JS = r"""
function useTweaks(defaults){
  const[values,setValues]=React.useState(defaults);
  const setTweak=React.useCallback((key,val)=>{
    setValues(prev=>({...prev,[key]:val}));
    window.parent.postMessage({type:"__edit_mode_set_keys",edits:{[key]:val}},"*");
  },[]);
  return[values,setTweak];
}

function TweaksPanel({title="Tweaks",children}){
  const[open,setOpen]=React.useState(false);
  const dragRef=React.useRef(null);
  const offsetRef=React.useRef({x:16,y:16});
  const PAD=16;
  const clamp=React.useCallback(()=>{
    const p=dragRef.current;if(!p)return;
    const w=p.offsetWidth,h=p.offsetHeight;
    const mr=Math.max(PAD,window.innerWidth-w-PAD),mb=Math.max(PAD,window.innerHeight-h-PAD);
    offsetRef.current={x:Math.min(mr,Math.max(PAD,offsetRef.current.x)),y:Math.min(mb,Math.max(PAD,offsetRef.current.y))};
    p.style.right=offsetRef.current.x+"px";p.style.bottom=offsetRef.current.y+"px";
  },[]);
  React.useEffect(()=>{
    if(!open)return;clamp();
    const ro=typeof ResizeObserver!=="undefined"?new ResizeObserver(clamp):null;
    if(ro)ro.observe(document.documentElement);else window.addEventListener("resize",clamp);
    return()=>{if(ro)ro.disconnect();else window.removeEventListener("resize",clamp);};
  },[open,clamp]);
  React.useEffect(()=>{
    const h=e=>{const t=e?.data?.type;if(t==="__activate_edit_mode")setOpen(true);else if(t==="__deactivate_edit_mode")setOpen(false);};
    window.addEventListener("message",h);
    window.parent.postMessage({type:"__edit_mode_available"},"*");
    return()=>window.removeEventListener("message",h);
  },[]);
  const dismiss=()=>{setOpen(false);window.parent.postMessage({type:"__edit_mode_dismissed"},"*");};
  const onDrag=e=>{
    const p=dragRef.current;if(!p)return;
    const r=p.getBoundingClientRect();
    const sx=e.clientX,sy=e.clientY,sr=window.innerWidth-r.right,sb=window.innerHeight-r.bottom;
    const mv=ev=>{offsetRef.current={x:sr-(ev.clientX-sx),y:sb-(ev.clientY-sy)};clamp();};
    const up=()=>{window.removeEventListener("mousemove",mv);window.removeEventListener("mouseup",up);};
    window.addEventListener("mousemove",mv);window.addEventListener("mouseup",up);
  };
  if(!open)return null;
  return(
    <>
      <style>{`""" + _TWEAKS_CSS + r"""` }</style>
      <div ref={dragRef} className="twk-panel" style={{right:offsetRef.current.x,bottom:offsetRef.current.y}}>
        <div className="twk-hd" onMouseDown={onDrag}><b>{title}</b>
          <button className="twk-x" onMouseDown={e=>e.stopPropagation()} onClick={dismiss}>✕</button>
        </div>
        <div className="twk-body">{children}</div>
      </div>
    </>
  );
}

function TweakSection({label,children}){return<><div className="twk-sect">{label}</div>{children}</>;}
function TweakRow({label,value,children,inline=false}){
  return<div className={inline?"twk-row twk-row-h":"twk-row"}>
    <div className="twk-lbl"><span>{label}</span>{value!=null&&<span className="twk-val">{value}</span>}</div>
    {children}
  </div>;
}
function TweakSlider({label,value,min=0,max=100,step=1,unit="",onChange}){
  return<TweakRow label={label} value={`${value}${unit}`}>
    <input type="range" className="twk-slider" min={min} max={max} step={step} value={value} onChange={e=>onChange(Number(e.target.value))}/>
  </TweakRow>;
}
function TweakToggle({label,value,onChange}){
  return<div className="twk-row twk-row-h">
    <div className="twk-lbl"><span>{label}</span></div>
    <button type="button" className="twk-toggle" data-on={value?"1":"0"} onClick={()=>onChange(!value)}><i/></button>
  </div>;
}
function TweakColor({label,value,onChange}){
  return<div className="twk-row twk-row-h">
    <div className="twk-lbl"><span>{label}</span></div>
    <input type="color" className="twk-swatch" value={value} onChange={e=>onChange(e.target.value)}/>
  </div>;
}
Object.assign(window,{useTweaks,TweaksPanel,TweakSection,TweakRow,TweakSlider,TweakToggle,TweakColor});
"""


def build_spa_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>AlphaFutures — Elliott Wave Engine</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
<script src="https://unpkg.com/react@18.3.1/umd/react.development.js" crossorigin="anonymous"></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js" crossorigin="anonymous"></script>
<script src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js" crossorigin="anonymous"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow-x:hidden}
:root{
  --bg:#08031a;--bg2:#0d0526;--card:rgba(255,255,255,.04);--card2:rgba(255,255,255,.07);
  --b:rgba(255,255,255,.08);--b2:rgba(255,255,255,.16);--text:#f0eeff;--text2:#a89dc8;--muted:#6b5f8a;
  --vi:#9333ea;--vi2:#a855f7;--vi3:#c084fc;--cy:#06b6d4;--cy2:#22d3ee;--mg:#e040fb;
  --green:#10b981;--red:#f43f5e;--gold:#fbbf24;--r:12px;--r2:16px;
  --font:"DM Sans",sans-serif;--mono:"JetBrains Mono",monospace;
}
body{font-family:var(--font);background:var(--bg);color:var(--text);min-height:100vh}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-thumb{background:rgba(147,51,234,.3);border-radius:2px}
body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background:radial-gradient(ellipse 70% 50% at 15% 10%,rgba(147,51,234,.15) 0%,transparent 60%),
    radial-gradient(ellipse 50% 40% at 85% 80%,rgba(6,182,212,.08) 0%,transparent 55%),
    radial-gradient(ellipse 40% 30% at 50% 50%,rgba(224,64,251,.05) 0%,transparent 60%);}
body::after{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:linear-gradient(rgba(147,51,234,.06) 1px,transparent 1px),
    linear-gradient(90deg,rgba(147,51,234,.06) 1px,transparent 1px);background-size:60px 60px;}
#root{position:relative;z-index:1}
.ticker{height:30px;background:rgba(0,0,0,.5);border-bottom:1px solid rgba(147,51,234,.2);overflow:hidden;display:flex;align-items:center}
.t-track{display:flex;white-space:nowrap;animation:tick 32s linear infinite}
.t-track:hover{animation-play-state:paused}
.t-item{display:inline-flex;align-items:center;gap:8px;padding:0 20px;font-size:11px;font-family:var(--mono);border-right:1px solid rgba(147,51,234,.15)}
@keyframes tick{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.topbar{height:56px;background:rgba(8,3,26,.8);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid rgba(147,51,234,.2);display:flex;align-items:center;padding:0 20px;gap:8px;
  position:sticky;top:0;z-index:100;}
.t-logo{display:flex;align-items:center;gap:10px;margin-right:16px;cursor:pointer}
.t-icon{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--vi),#6b21a8);
  display:flex;align-items:center;justify-content:center;font-size:18px;
  box-shadow:0 0 0 1px rgba(168,85,247,.4),0 0 20px rgba(147,51,234,.5);
  animation:icon-pulse 3s ease-in-out infinite;}
@keyframes icon-pulse{0%,100%{box-shadow:0 0 0 1px rgba(168,85,247,.4),0 0 20px rgba(147,51,234,.5)}
  50%{box-shadow:0 0 0 1px rgba(168,85,247,.6),0 0 32px rgba(147,51,234,.8),0 0 0 6px rgba(147,51,234,.08)}}
.t-name{font-size:15px;font-weight:700;letter-spacing:-.01em;background:linear-gradient(135deg,#e0d0ff,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.t-sep{width:1px;height:18px;background:rgba(147,51,234,.25);margin:0 4px}
.nb{display:inline-flex;align-items:center;gap:5px;padding:7px 13px;border-radius:8px;font-size:13px;font-weight:500;color:var(--text2);cursor:pointer;border:none;background:transparent;transition:all .15s;font-family:var(--font)}
.nb:hover{color:var(--text);background:rgba(147,51,234,.12)}
.nb.on{color:var(--vi3);background:rgba(147,51,234,.18);border:1px solid rgba(147,51,234,.25)}
.t-right{margin-left:auto;display:flex;align-items:center;gap:6px}
.pill{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid transparent;transition:all .15s;font-family:var(--font)}
.p-vi{background:rgba(147,51,234,.15);color:var(--vi3);border-color:rgba(147,51,234,.3)}
.p-vi:hover{background:rgba(147,51,234,.28);box-shadow:0 0 12px rgba(147,51,234,.25)}
.p-cy{background:rgba(6,182,212,.12);color:var(--cy2);border-color:rgba(6,182,212,.25)}
.p-cy:hover{background:rgba(6,182,212,.22)}
.p-gr{background:rgba(16,185,129,.1);color:var(--green);border-color:rgba(16,185,129,.22)}
.p-gr:hover{background:rgba(16,185,129,.2)}
.page{padding:20px;max-width:1340px;margin:0 auto}
.page-sm{padding:20px;max-width:880px;margin:0 auto}
.card{background:rgba(255,255,255,.04);border:1px solid rgba(147,51,234,.15);border-radius:var(--r2);backdrop-filter:blur(12px);position:relative;overflow:hidden}
.card::before{content:"";position:absolute;top:0;left:10%;right:10%;height:1px;background:linear-gradient(90deg,transparent,rgba(168,85,247,.5),transparent)}
.nstat{background:rgba(255,255,255,.04);border:1px solid rgba(147,51,234,.18);border-radius:var(--r2);padding:22px 24px;position:relative;overflow:hidden;transition:border-color .3s,transform .25s;backdrop-filter:blur(12px)}
.nstat:hover{transform:translateY(-2px);border-color:rgba(168,85,247,.4)}
.nstat::before{content:"";position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(168,85,247,.5),transparent)}
.nstat-cy::before{background:linear-gradient(90deg,transparent,rgba(6,182,212,.5),transparent)}
.nstat-cy{border-color:rgba(6,182,212,.18)}.nstat-cy:hover{border-color:rgba(6,182,212,.4)}
.nstat-gr::before{background:linear-gradient(90deg,transparent,rgba(16,185,129,.5),transparent)}
.nstat-gr{border-color:rgba(16,185,129,.18)}.nstat-gr:hover{border-color:rgba(16,185,129,.4)}
.nstat-re::before{background:linear-gradient(90deg,transparent,rgba(244,63,94,.5),transparent)}
.nstat-re{border-color:rgba(244,63,94,.18)}
.nstat-go::before{background:linear-gradient(90deg,transparent,rgba(251,191,36,.5),transparent)}
.nstat-go{border-color:rgba(251,191,36,.18)}
.nstat::after{content:"";position:absolute;inset:0;background:radial-gradient(ellipse 80% 80% at 50% 120%,rgba(147,51,234,.06),transparent);pointer-events:none}
.nstat-cy::after{background:radial-gradient(ellipse 80% 80% at 50% 120%,rgba(6,182,212,.06),transparent)}
.nstat-gr::after{background:radial-gradient(ellipse 80% 80% at 50% 120%,rgba(16,185,129,.06),transparent)}
.nstat-re::after{background:radial-gradient(ellipse 80% 80% at 50% 120%,rgba(244,63,94,.06),transparent)}
.shimmer{position:absolute;inset:0;background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,.025) 50%,transparent 60%);background-size:200% 100%;animation:shimmer 4.5s ease-in-out infinite}
@keyframes shimmer{0%,100%{background-position:200% 0}60%{background-position:-200% 0}}
.stat-l{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:10px;position:relative;z-index:1}
.stat-v{font-size:30px;font-weight:700;font-family:var(--mono);letter-spacing:-.02em;line-height:1;position:relative;z-index:1}
.stat-s{font-size:11px;color:var(--muted);margin-top:7px;position:relative;z-index:1}
.prog{height:2px;background:rgba(255,255,255,.06);border-radius:1px;overflow:hidden;margin-top:12px;position:relative;z-index:1}
.pf{height:100%;border-radius:1px;transition:width 1.5s cubic-bezier(.22,1,.36,1)}
.nvi{color:var(--vi3)}.ncy{color:var(--cy2)}.ngr{color:var(--green)}.nre{color:var(--red)}.ngo{color:var(--gold)}
.pos{color:var(--green);font-weight:600}.neg{color:var(--red);font-weight:600}.dim{color:var(--muted)}.mono{font-family:var(--mono)}
.badge{display:inline-flex;align-items:center;gap:3px;padding:3px 9px;border-radius:5px;font-size:11px;font-weight:700;font-family:var(--mono)}
.b-long{background:rgba(16,185,129,.12);color:var(--green);border:1px solid rgba(16,185,129,.25)}
.b-short{background:rgba(244,63,94,.12);color:var(--red);border:1px solid rgba(244,63,94,.25)}
.b-win{background:rgba(16,185,129,.12);color:var(--green);border:1px solid rgba(16,185,129,.25)}
.b-loss{background:rgba(244,63,94,.12);color:var(--red);border:1px solid rgba(244,63,94,.25)}
.b-st{background:rgba(251,191,36,.1);color:var(--gold);border:1px solid rgba(251,191,36,.2)}
.b-act{background:rgba(16,185,129,.1);color:var(--green);border:1px solid rgba(16,185,129,.2)}
.b-ina{background:rgba(255,255,255,.05);color:var(--muted);border:1px solid var(--b)}
.b-vi{background:rgba(147,51,234,.12);color:var(--vi3);border:1px solid rgba(147,51,234,.25)}
.tbl{width:100%;border-collapse:collapse}
.tbl th{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:0 14px 14px;text-align:left;border-bottom:1px solid rgba(147,51,234,.15)}
.tbl td{padding:0 14px;height:54px;border-bottom:1px solid rgba(255,255,255,.04);vertical-align:middle}
.tbl tr:last-child td{border-bottom:none}
.tbl tbody tr{transition:background .15s}.tbl tbody tr:hover{background:rgba(147,51,234,.05)}
.tw{overflow-x:auto}.tw::-webkit-scrollbar{height:3px}
.inp{width:100%;background:rgba(0,0,0,.4);border:1px solid rgba(147,51,234,.2);border-radius:var(--r);padding:12px 14px;color:var(--text);font-size:14px;font-family:var(--font);outline:none;transition:border-color .2s,box-shadow .2s}
.inp:focus{border-color:rgba(168,85,247,.5);box-shadow:0 0 0 3px rgba(147,51,234,.12)}
.inp::placeholder{color:var(--muted)}
textarea.inp{resize:vertical;line-height:1.65}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:11px 22px;border-radius:var(--r);font-size:14px;font-weight:600;font-family:var(--font);border:none;cursor:pointer;transition:all .2s;white-space:nowrap}
.btn-vi{background:linear-gradient(135deg,#9333ea,#6b21a8);color:#fff;box-shadow:0 4px 20px rgba(147,51,234,.5),inset 0 1px 0 rgba(255,255,255,.12)}
.btn-vi:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 8px 30px rgba(147,51,234,.7)}
.btn-vi:disabled{opacity:.4;cursor:not-allowed;transform:none}
.btn-cy{background:linear-gradient(135deg,#06b6d4,#0284c7);color:#fff;box-shadow:0 4px 20px rgba(6,182,212,.4)}
.btn-cy:hover{transform:translateY(-2px)}
.btn-gl{background:rgba(255,255,255,.06);color:var(--text2);border:1px solid var(--b)}
.btn-gl:hover{background:rgba(255,255,255,.1);color:var(--text)}
.btn-sm{padding:6px 13px;font-size:11px;border-radius:8px}
.btn-full{width:100%;padding:13px;font-size:15px}
.chip{padding:6px 15px;border-radius:7px;font-size:12px;font-weight:500;cursor:pointer;border:1px solid rgba(147,51,234,.2);background:transparent;color:var(--muted);transition:all .15s;font-family:var(--font)}
.chip:hover{color:var(--text);border-color:rgba(147,51,234,.4)}
.chip.on{background:rgba(147,51,234,.15);color:var(--vi3);border-color:rgba(147,51,234,.35)}
.field{margin-bottom:16px}
.fl{display:block;font-size:10px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-bottom:7px}
.dv{height:1px;background:linear-gradient(90deg,transparent,rgba(168,85,247,.4),transparent);margin:0 0 18px}
.dcy{height:1px;background:linear-gradient(90deg,transparent,rgba(6,182,212,.3),transparent);margin:16px 0}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0}
.dot-g{background:var(--green);box-shadow:0 0 8px var(--green);animation:dp 2.5s ease-in-out infinite}
@keyframes dp{0%,100%{box-shadow:0 0 6px var(--green)}50%{box-shadow:0 0 16px var(--green),0 0 0 4px rgba(16,185,129,.1)}}
.steps{display:flex;border-bottom:1px solid rgba(147,51,234,.2);margin-bottom:24px}
.step{flex:1;text-align:center;padding:10px 4px;border-bottom:2px solid transparent;margin-bottom:-1px;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);transition:all .25s}
.step.on{border-bottom-color:var(--vi2);color:var(--vi3)}
.step.done{border-bottom-color:var(--green);color:var(--green)}
.err{background:rgba(244,63,94,.08);border:1px solid rgba(244,63,94,.25);border-radius:var(--r);padding:11px 14px;color:var(--red);font-size:13px;margin-bottom:14px}
.sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px}
.sh-t{font-size:14px;font-weight:700}.sh-s{font-size:11px;color:var(--muted);margin-top:2px}
@keyframes up{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes afade{from{opacity:0}to{opacity:1}}
.au{animation:up .5s cubic-bezier(.22,.68,0,1.15) both}
.au1{animation:up .5s .07s cubic-bezier(.22,.68,0,1.15) both}
.au2{animation:up .5s .14s cubic-bezier(.22,.68,0,1.15) both}
.au3{animation:up .5s .21s cubic-bezier(.22,.68,0,1.15) both}
.au4{animation:up .5s .28s cubic-bezier(.22,.68,0,1.15) both}
.rin{animation:up .38s ease both}
.login-wrap{min-height:calc(100vh - 30px);display:grid;grid-template-columns:1.1fr 1fr}
.l-left{padding:48px 52px;display:flex;flex-direction:column;justify-content:space-between;position:relative;overflow:hidden;background:linear-gradient(145deg,rgba(147,51,234,.1),rgba(6,182,212,.05))}
.l-left::before{content:"";position:absolute;inset:0;background:radial-gradient(ellipse 70% 60% at 30% 40%,rgba(147,51,234,.15),transparent 65%);pointer-events:none}
.l-right{padding:48px 52px;display:flex;flex-direction:column;justify-content:center;background:rgba(0,0,0,.2)}
@media(max-width:768px){.login-wrap{grid-template-columns:1fr}.l-left{display:none}}
@media(max-width:640px){.hide-sm{display:none!important}.sg{grid-template-columns:1fr 1fr!important}.page,.page-sm{padding:12px}.topbar{padding:0 12px}}
.sc{background:rgba(255,255,255,.04);border:1px solid rgba(147,51,234,.15);border-radius:var(--r);padding:14px 16px}
.sv{font-size:28px;font-weight:700;font-family:var(--mono);letter-spacing:-.02em;line-height:1}
.sl{font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin-top:4px}
</style>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
"""
        + _TWEAKS_JS
        + r"""
</script>
<script type="text/babel">
const {useState,useEffect,useRef,useCallback}=React;

const fmt=(n,d=2)=>n==null||isNaN(+n)?"–":Number(n).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const REASON={TP3_HIT:"TP3 HIT",TP2_THEN_SL:"TP2 → SL",TP1_THEN_SL:"TP1 → SL",SL_HIT:"SL HIT"};

function Spin(){return<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{animation:"spin 1s linear infinite",flexShrink:0}}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" strokeLinecap="round"/></svg>;}

function getInitPage(){
  const p=window.location.pathname;
  if(p.startsWith("/u/"))return{page:"client",token:p.slice(3)};
  const MAP={"/login":"login","/register":"register","/guide":"guide","/board":"board","/history":"history","/admin":"admin"};
  return{page:MAP[p]||"dashboard",token:""};
}

/* ── TICKER ── */
function Ticker(){
  const SYMS=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","AVAXUSDT"];
  const [items,setItems]=React.useState(SYMS.map(s=>({s:s.replace("USDT","/USDT"),p:"–",c:"–",up:true})));
  const load=React.useCallback(async()=>{
    try{
      const r=await fetch("https://api.binance.com/api/v3/ticker/24hr?symbols=[%22"+SYMS.join("%22,%22")+"%22]",{cache:"no-store"});
      const data=await r.json();
      if(!Array.isArray(data))return;
      setItems(data.map(d=>({
        s:d.symbol.replace("USDT","/USDT"),
        p:parseFloat(d.lastPrice)<1?parseFloat(d.lastPrice).toFixed(4):parseFloat(d.lastPrice).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}),
        c:(parseFloat(d.priceChangePercent)>=0?"+":"")+parseFloat(d.priceChangePercent).toFixed(2)+"%",
        up:parseFloat(d.priceChangePercent)>=0
      })));
    }catch(e){}
  },[]);
  React.useEffect(()=>{load();const id=setInterval(load,30000);return()=>clearInterval(id);},[load]);
  return<div className="ticker"><div className="t-track">{[...items,...items].map((t,i)=><div className="t-item" key={i}><span style={{color:"var(--text2)"}}>{t.s}</span><span style={{fontWeight:600,color:"var(--text)"}}>{t.p}</span><span style={{color:t.up?"var(--green)":"var(--red)",fontWeight:700}}>{t.c}</span></div>)}</div></div>;
}

/* ── TOPBAR ── */
function Topbar({page,nav}){
  return(
    <div className="topbar">
      <div className="t-logo" onClick={()=>nav("dashboard")}><div className="t-icon">⚡</div><span className="t-name">AlphaFutures</span></div>
      <div className="t-sep hide-sm"/>
      {[["dashboard","Dashboard"],["history","History"],["board","Board"]].map(([id,l])=>(
        <button key={id} className={`nb${page===id?" on":""}`} onClick={()=>nav(id)}>{l}</button>
      ))}
      <div className="t-right">
        <button className="pill p-gr hide-sm" onClick={()=>nav("register")}>✏ Join</button>
        <button className="pill p-vi" onClick={()=>nav("login")}>🔑 Login</button>
        <button className="pill p-cy hide-sm" onClick={()=>nav("guide")}>📘 Guide</button>
      </div>
    </div>
  );
}

/* ── HOOKS ── */
function useCountUp(target,dur=1600,dec=1,go=true){
  const[v,setV]=useState(0);
  useEffect(()=>{
    if(!go||target===0){setV(0);return;}
    let t0=null;
    const f=ts=>{if(!t0)t0=ts;const p=Math.min((ts-t0)/dur,1);const e=1-Math.pow(1-p,4);setV(parseFloat((target*e).toFixed(dec)));if(p<1)requestAnimationFrame(f);else setV(target);};
    requestAnimationFrame(f);
  },[target,go,dur,dec]);
  return v;
}
function useInView(ref){
  const[v,setV]=useState(false);
  useEffect(()=>{const ob=new IntersectionObserver(([e])=>{if(e.isIntersecting)setV(true)},{threshold:.1});if(ref.current)ob.observe(ref.current);return()=>ob.disconnect();},[]);
  return v;
}

/* ── NSTAT ── */
function NStat({label,target,dec=1,pre="",suf="",col,note,delay="0s"}){
  const ref=useRef();const vis=useInView(ref);const v=useCountUp(target,1800,dec,vis);
  const cls=col==="cy"?"nstat-cy":col==="gr"?"nstat-gr":col==="re"?"nstat-re":col==="go"?"nstat-go":"";
  const tc=col==="cy"?"var(--cy2)":col==="gr"?"var(--green)":col==="re"?"var(--red)":col==="go"?"var(--gold)":"var(--vi3)";
  const ts=col==="cy"?"0 0 16px rgba(6,182,212,.5)":col==="gr"?"0 0 16px rgba(16,185,129,.5)":col==="re"?"0 0 16px rgba(244,63,94,.4)":"0 0 16px rgba(168,85,247,.5)";
  const pct=target===0?0:Math.min(v/target*100,100);
  return(
    <div ref={ref} className={`nstat ${cls} au`} style={{animationDelay:delay}}>
      <div className="shimmer"/><div className="stat-l">{label}</div>
      <div className="stat-v" style={{color:tc,textShadow:ts}}>{pre}{fmt(v,dec)}{suf}</div>
      {note&&<div className="stat-s">{note}</div>}
      <div className="prog"><div className="pf" style={{width:`${pct}%`,background:tc,boxShadow:`0 0 8px ${tc}`}}/></div>
    </div>
  );
}

/* ── CANDLE CHART ── */
function CandleChart(){
  const cc=[{o:60,h:80,l:50,c:75,up:true},{o:75,h:90,l:68,c:70,up:false},{o:70,h:85,l:62,c:82,up:true},{o:82,h:95,l:75,c:78,up:false},{o:78,h:92,l:70,c:88,up:true},{o:88,h:100,l:80,c:95,up:true},{o:95,h:108,l:88,c:90,up:false},{o:90,h:102,l:82,c:98,up:true},{o:98,h:115,l:90,c:105,up:true},{o:105,h:118,l:96,c:100,up:false},{o:100,h:112,l:88,c:108,up:true},{o:108,h:125,l:100,c:120,up:true}];
  const W=400,H=140,pad=20,max=Math.max(...cc.map(c=>c.h)),min=Math.min(...cc.map(c=>c.l));
  const sy=v=>pad+(1-(v-min)/(max-min))*(H-pad*2);
  const cw=Math.floor((W-pad*2)/cc.length),bw=Math.max(cw-6,4);
  return<svg viewBox={`0 0 ${W} ${H}`} style={{width:"100%",height:140}}>{cc.map((c,i)=>{const x=pad+i*cw+cw/2,col=c.up?"#10b981":"#f43f5e",top=sy(Math.max(c.o,c.c)),bot=sy(Math.min(c.o,c.c));return<g key={i}><line x1={x} y1={sy(c.h)} x2={x} y2={sy(c.l)} stroke={col} strokeWidth="1.5" opacity=".7"/><rect x={x-bw/2} y={top} width={bw} height={Math.max(bot-top,2)} fill={col} rx="1.5" opacity=".85"/></g>;})}</svg>;
}

/* ── EQUITY CURVE ── */
function EquityCurve({history}){
  const ref=useRef();const vis=useInView(ref);
  const asc=[...history].reverse();
  let eq=0;
  const pts=[0,...asc.map(t=>{eq+=parseFloat(t.rr||0);return eq;})];
  const totalRR=parseFloat(eq.toFixed(2));
  const W=700,H=120,px=10,py=12,n=Math.max(pts.length-1,1);
  const maxV=Math.max(...pts,0.1),minV=Math.min(...pts,0),range=maxV-minV||1;
  const sx=i=>px+(i/n)*(W-px*2);
  const sy=v=>py+(1-(v-minV)/range)*(H-py*2);
  const d=pts.map((v,i)=>`${i===0?"M":"L"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(" ");
  const area=pts.length>1?d+` L${sx(pts.length-1).toFixed(1)},${H} L${sx(0).toFixed(1)},${H} Z`:"";
  const col=totalRR>=0?"#10b981":"#f43f5e";
  return(
    <div ref={ref} className="card au3" style={{padding:"22px 24px",marginBottom:14}}>
      <div className="sh">
        <div><div className="sh-t">Equity Curve</div><div className="sh-s">Cumulative R — all closed signals</div></div>
        <div style={{textAlign:"right"}}><div className="mono" style={{fontSize:20,fontWeight:700,color:col}}>{totalRR>=0?"+":""}{totalRR}R</div><div style={{fontSize:11,color:"var(--muted)"}}>total return</div></div>
      </div>
      <div className="dcy"/>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{width:"100%",height:120}}>
        <defs>
          <linearGradient id="ef" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={col} stopOpacity=".25"/><stop offset="100%" stopColor={col} stopOpacity="0"/></linearGradient>
          <filter id="gf"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        {vis&&pts.length>1&&<>
          <path d={area} fill="url(#ef)" style={{animation:"afade .7s .7s both",opacity:0}}/>
          <path d={d} fill="none" stroke={col} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" filter="url(#gf)"
            style={{strokeDasharray:3000,strokeDashoffset:3000,animation:"draw 2.5s cubic-bezier(.22,1,.36,1) .5s forwards"}}/>
        </>}
        {pts.length<=1&&<text x={W/2} y={H/2} textAnchor="middle" fontSize="12" fill="var(--muted)" fontFamily="var(--mono)">No closed trades yet</text>}
      </svg>
    </div>
  );
}

/* ── PERF BARS ── */
function PerfBars({stats}){
  const ref=useRef();const vis=useInView(ref);
  const s=stats||{};
  const bars=[
    {l:"Win Rate",v:s.win_rate||0,max:100,txt:`${(s.win_rate||0).toFixed(1)}%`,col:"var(--green)",sh:"rgba(16,185,129,.4)"},
    {l:"Profit Factor",v:Math.min(s.profit_factor||0,5),max:5,txt:`${(s.profit_factor||0).toFixed(2)}×`,col:"var(--vi3)",sh:"rgba(168,85,247,.5)"},
    {l:"Avg R:R",v:Math.min(s.avg_rr||0,4),max:4,txt:`${(s.avg_rr||0).toFixed(2)}R`,col:"var(--cy2)",sh:"rgba(6,182,212,.4)"},
  ];
  return(
    <div ref={ref} className="card au4" style={{padding:"22px 24px",marginBottom:14}}>
      <div className="sh"><div><div className="sh-t">Performance</div><div className="sh-s">{s.total||0} closed · {s.wins||0}W {s.losses||0}L</div></div></div>
      <div className="dv"/>
      {bars.map((b,i)=>(
        <div key={i} style={{marginBottom:i<2?18:0}}>
          <div style={{display:"flex",justifyContent:"space-between",marginBottom:7}}>
            <span style={{fontSize:13,color:"var(--text2)"}}>{b.l}</span>
            <span className="mono" style={{fontSize:13,fontWeight:700,color:b.col,textShadow:`0 0 12px ${b.sh}`}}>{b.txt}</span>
          </div>
          <div className="prog"><div className="pf" style={{width:vis?`${(b.v/b.max)*100}%`:"0%",background:b.col,boxShadow:`0 0 8px ${b.sh}`,transitionDelay:`${.4+i*.12}s`}}/></div>
        </div>
      ))}
    </div>
  );
}

/* ── DASHBOARD ── */
function DashboardPage(){
  const[stats,setStats]=useState({});
  const[active,setActive]=useState([]);
  const[history,setHistory]=useState([]);
  const[loading,setLoading]=useState(true);
  const[err,setErr]=useState("");

  const load=useCallback(async()=>{
    try{
      const[s,h]=await Promise.all([
        fetch("/api/snapshot",{cache:"no-store"}).then(r=>r.json()),
        fetch("/api/history",{cache:"no-store"}).then(r=>r.json()),
      ]);
      if(s.ok){setStats(s.snapshot?.stats||{});setActive(s.snapshot?.active_trades||[]);}
      if(h.ok)setHistory(h.trades||[]);
      setErr("");
    }catch(e){setErr(e.message);}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{load();const id=setInterval(load,15000);return()=>clearInterval(id);},[load]);

  const s=stats;
  return(
    <div className="page">
      {err&&<div className="err" style={{marginBottom:12}}>⚠ {err}</div>}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(162px,1fr))",gap:12,marginBottom:14}} className="sg">
        <NStat label="Win Rate"     target={s.win_rate||0}     dec={1} suf="%" col="gr" note={`${s.wins||0}W · ${s.losses||0}L of ${s.total||0}`} delay="0s"/>
        <NStat label="Avg R:R"      target={s.avg_rr||0}       dec={2} note="risk : reward" delay=".06s"/>
        <NStat label="Max Drawdown" target={s.max_dd||0}       dec={1} pre="-" suf="R" col="re" note="in R units" delay=".12s"/>
        <NStat label="Total Trades" target={s.total||0}        dec={0} note="closed" delay=".18s"/>
        <NStat label="Profit Factor"target={s.profit_factor||0}dec={2} col="cy" note="gross W / L" delay=".24s"/>
      </div>

      <div className="card au2" style={{padding:"22px 24px",marginBottom:14}}>
        <div className="sh">
          <div><div style={{display:"flex",alignItems:"center",gap:9}}><span className="sh-t">Open Trades</span><span className="badge b-vi">{active.length} active</span></div><div className="sh-s">Elliott Wave signals · live positions</div></div>
          <div style={{display:"flex",alignItems:"center",gap:7}}><span className="dot dot-g"/><span style={{fontSize:11,color:"var(--muted)"}}>Auto-refresh 15s</span></div>
        </div>
        <div className="dv"/>
        {loading?<p style={{color:"var(--muted)",fontSize:13,padding:"20px 0",textAlign:"center"}}>Loading…</p>:
         active.length===0?<p style={{color:"var(--muted)",fontSize:13,padding:"20px 0",textAlign:"center"}}>No open positions</p>:(
          <div className="tw"><table className="tbl">
            <thead><tr><th>Symbol</th><th>TF</th><th>Side</th><th>Entry</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Status</th></tr></thead>
            <tbody>{active.map((t,i)=>(
              <tr key={i} className="rin" style={{animationDelay:`${i*.07}s`}}>
                <td><span style={{fontWeight:700}}>{t.symbol.replace("USDT","")}</span><span className="dim">/USDT</span></td>
                <td className="mono dim" style={{fontSize:11}}>{t.timeframe}</td>
                <td><span className={`badge b-${t.side==="LONG"?"long":"short"}`}>{t.side==="LONG"?"▲":"▼"} {t.side}</span></td>
                <td className="mono">{fmt(t.entry,2)}</td>
                <td className="mono neg">{fmt(t.sl,0)}</td>
                <td className="mono" style={{color:t.tp1_hit?"var(--green)":"var(--muted)"}}>{fmt(t.tp1,0)}{t.tp1_hit?" ✓":""}</td>
                <td className="mono" style={{color:t.tp2_hit?"var(--green)":"var(--muted)"}}>{fmt(t.tp2,0)}{t.tp2_hit?" ✓":""}</td>
                <td className="mono dim">{fmt(t.tp3,0)}</td>
                <td><span className="badge b-st">{t.status}</span></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 360px",gap:14}}>
        <EquityCurve history={history}/>
        <PerfBars stats={stats}/>
      </div>
    </div>
  );
}

/* ── HISTORY ── */
function HistoryPage(){
  const[f,setF]=useState("30");
  const[all,setAll]=useState([]);
  const[loading,setLoading]=useState(true);

  useEffect(()=>{
    fetch("/api/history",{cache:"no-store"}).then(r=>r.json()).then(d=>{if(d.ok)setAll(d.trades||[]);}).finally(()=>setLoading(false));
  },[]);

  const trades=f==="all"?all:all.filter(t=>{
    if(!t.closed_at)return false;
    const cut=new Date();cut.setDate(cut.getDate()-parseInt(f));
    return new Date(t.closed_at.replace(" ","T"))>=cut;
  });

  return(
    <div className="page">
      <div className="card au" style={{padding:"22px 24px"}}>
        <div className="sh">
          <div><div className="sh-t">Trade History</div><div className="sh-s">All closed signals</div></div>
          <div style={{display:"flex",gap:6}}>{["7","30","all"].map(v=><button key={v} className={`chip${f===v?" on":""}`} onClick={()=>setF(v)}>{v==="all"?"All Time":`${v}D`}</button>)}</div>
        </div>
        <div className="dv"/>
        {loading?<p style={{color:"var(--muted)",fontSize:13,padding:"20px 0",textAlign:"center"}}>Loading…</p>:
         trades.length===0?<p style={{color:"var(--muted)",fontSize:13,padding:"20px 0",textAlign:"center"}}>No trades found</p>:(
          <div className="tw"><table className="tbl">
            <thead><tr><th>Closed</th><th>Symbol</th><th>TF</th><th>Side</th><th>Entry</th><th>Exit</th><th>RR</th><th>Result</th></tr></thead>
            <tbody>{trades.map((t,i)=>(
              <tr key={i} className="rin" style={{animationDelay:`${i*.05}s`}}>
                <td className="mono dim" style={{fontSize:11}}>{t.closed_at}</td>
                <td><span style={{fontWeight:700}}>{(t.symbol||"").replace("USDT","")}</span><span className="dim">/USDT</span></td>
                <td className="mono dim" style={{fontSize:11}}>{t.timeframe}</td>
                <td><span className={`badge b-${t.side==="LONG"?"long":"short"}`}>{t.side==="LONG"?"▲":"▼"} {t.side}</span></td>
                <td className="mono">{fmt(t.entry,2)}</td>
                <td className="mono">{fmt(t.exit,2)}</td>
                <td className={`mono ${t.rr>=0?"pos":"neg"}`} style={{fontWeight:700}}>{t.rr>=0?"+":""}{t.rr}R</td>
                <td><span className={`badge b-${t.result==="WIN"?"win":"loss"}`}>{REASON[t.close_reason]||t.close_reason||t.result}</span></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}

/* ── BOARD ── */
function BoardPage(){
  const[name,setName]=useState("");const[msg,setMsg]=useState("");
  const[posts,setPosts]=useState([]);const[loading,setLoading]=useState(false);const[err,setErr]=useState("");

  const load=()=>fetch("/api/posts").then(r=>r.json()).then(d=>{if(d.ok)setPosts(d.posts||[]);});
  useEffect(()=>{load();},[]);

  const submit=async()=>{
    if(!name.trim()||!msg.trim()){setErr("Please enter name and message.");return;}
    setLoading(true);setErr("");
    try{
      const d=await fetch("/api/posts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name.trim(),message:msg.trim()})}).then(r=>r.json());
      if(d.ok){setName("");setMsg("");load();}else setErr(d.error||"Failed to submit.");
    }catch(e){setErr("Network error.");}
    finally{setLoading(false);}
  };

  return(
    <div className="page-sm">
      <div className="card au" style={{padding:24,marginBottom:14}}>
        <div className="sh"><div><div className="sh-t">Submit Feedback</div><div className="sh-s">Issues · Questions · Suggestions</div></div></div>
        <div className="dv"/>
        {err&&<div className="err">{err}</div>}
        <div className="field"><label className="fl">Your Name</label><input className="inp" placeholder="Name or nickname" value={name} onChange={e=>setName(e.target.value)} maxLength={60}/></div>
        <div className="field"><label className="fl">Message</label><textarea className="inp" placeholder="Describe your issue or feedback..." value={msg} onChange={e=>setMsg(e.target.value)} style={{minHeight:100}} maxLength={2000}/></div>
        <button className="btn btn-vi" onClick={submit} disabled={loading}>{loading?<><Spin/>Sending…</>:"Submit →"}</button>
      </div>
      {posts.length===0?<p style={{color:"var(--muted)",fontSize:13,textAlign:"center",padding:"40px 0"}}>No posts yet.</p>:
       posts.map(p=>(
        <div key={p.id} className="card au" style={{padding:"20px 22px",marginBottom:10}}>
          <div style={{display:"flex",justifyContent:"space-between",marginBottom:10}}>
            <span style={{fontWeight:700,fontSize:13}}>{p.name}</span>
            <span className="mono dim" style={{fontSize:11}}>{p.created_at}</span>
          </div>
          <div style={{fontSize:13,lineHeight:1.8,color:"var(--text2)",whiteSpace:"pre-wrap",wordBreak:"break-word"}}>{p.message}</div>
        </div>
       ))}
    </div>
  );
}

/* ── LOGIN ── */
function LoginPage({nav,onLogin}){
  const[email,setEmail]=useState("");const[pw,setPw]=useState("");
  const[loading,setLoading]=useState(false);const[err,setErr]=useState("");

  const go=async()=>{
    setErr("");
    if(!email||!pw){setErr("Please enter your email and password.");return;}
    setLoading(true);
    try{
      const d=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password:pw})}).then(r=>r.json());
      if(d.ok)onLogin(d.token);else setErr(d.error||"Invalid email or password.");
    }catch(e){setErr("Network error: "+e.message);}
    finally{setLoading(false);}
  };

  return(
    <div className="login-wrap">
      <div className="l-left">
        <div style={{position:"relative",zIndex:1}}>
          <div style={{display:"flex",alignItems:"center",gap:11,marginBottom:44}}>
            <div className="t-icon" style={{width:42,height:42,borderRadius:12,fontSize:22}}>⚡</div>
            <div>
              <div style={{fontWeight:700,fontSize:17,background:"linear-gradient(135deg,#e0d0ff,#a78bfa)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>AlphaFutures</div>
              <div style={{fontSize:10,color:"var(--cy2)",letterSpacing:".12em",textTransform:"uppercase",fontWeight:600,marginTop:2}}>Elliott Wave Engine</div>
            </div>
          </div>
          <div style={{marginBottom:36}}>
            <div style={{fontSize:36,fontWeight:800,letterSpacing:"-.02em",lineHeight:1.15,marginBottom:14}}>Algorithmic<br/><span style={{background:"linear-gradient(135deg,var(--vi3),var(--cy2))",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>trading.</span></div>
            <div style={{fontSize:14,color:"var(--text2)",lineHeight:1.8,maxWidth:340}}>Elliott Wave pattern detection running 24/7. Automated signals, live position tracking.</div>
          </div>
          <div style={{background:"rgba(0,0,0,.3)",border:"1px solid rgba(147,51,234,.2)",borderRadius:12,padding:"16px 18px",marginBottom:28}}>
            <div style={{display:"flex",justifyContent:"space-between",marginBottom:8}}><span style={{fontSize:12,color:"var(--text2)",fontWeight:600}}>BTC/USDT · 4H</span><span className="badge b-long">▲ LONG</span></div>
            <CandleChart/>
          </div>
        </div>
        <div style={{position:"relative",zIndex:1,fontSize:11,color:"var(--muted)"}}>© 2026 AlphaFutures · Since 18 Mar 2026</div>
      </div>
      <div className="l-right">
        <div style={{maxWidth:380,width:"100%",margin:"0 auto"}}>
          <div style={{marginBottom:32}}><div style={{fontSize:26,fontWeight:800,letterSpacing:"-.02em",marginBottom:6}}>Welcome back</div><div style={{fontSize:14,color:"var(--text2)"}}>Sign in to access your dashboard</div></div>
          <div className="field"><label className="fl">Email address</label><input className="inp" type="email" placeholder="you@example.com" value={email} onChange={e=>setEmail(e.target.value)} onKeyDown={e=>e.key==="Enter"&&go()} autoComplete="email"/></div>
          <div className="field"><label className="fl">Password</label><input className="inp" type="password" placeholder="••••••••" value={pw} onChange={e=>setPw(e.target.value)} onKeyDown={e=>e.key==="Enter"&&go()} autoComplete="current-password"/></div>
          {err&&<div className="err">{err}</div>}
          <button className="btn btn-vi btn-full" style={{marginBottom:20}} onClick={go} disabled={loading}>{loading?<><Spin/>Signing in…</>:"Sign in →"}</button>
          <div style={{height:1,background:"linear-gradient(90deg,transparent,rgba(147,51,234,.25),transparent)",margin:"4px 0 18px"}}/>
          <div style={{textAlign:"center",fontSize:13,color:"var(--muted)"}}>No account yet?{" "}<span style={{color:"var(--vi3)",cursor:"pointer",fontWeight:600}} onClick={()=>nav("register")}>Create one here</span></div>
          <div style={{textAlign:"center",fontSize:13,color:"var(--muted)",marginTop:10}}><span style={{cursor:"pointer"}} onClick={()=>nav("dashboard")}>← Back to Dashboard</span></div>
        </div>
      </div>
    </div>
  );
}

/* ── REGISTER ── */
function RegisterPage({nav}){
  const[step,setStep]=useState(1);
  const[email,setEmail]=useState("");const[pw,setPw]=useState("");const[pw2,setPw2]=useState("");
  const[key,setKey]=useState("");const[sec,setSec]=useState("");
  const[loading,setLoading]=useState(false);const[err,setErr]=useState("");
  const[regToken,setRegToken]=useState("");

  const s1=async()=>{
    setErr("");
    if(!email||!pw||!pw2){setErr("Please fill in all fields.");return;}
    if(pw.length<8){setErr("Min 8 characters.");return;}
    if(pw!==pw2){setErr("Passwords don't match.");return;}
    setLoading(true);
    try{
      const d=await fetch("/api/register/step1",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password:pw})}).then(r=>r.json());
      if(d.ok){setRegToken(d.token);setStep(2);}else setErr(d.error||"Registration failed.");
    }catch(e){setErr("Network error.");}
    finally{setLoading(false);}
  };

  const s2=async()=>{
    setErr("");
    if(!key||!sec){setErr("Please enter both keys.");return;}
    setLoading(true);
    try{
      const d=await fetch("/api/register/step2",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:regToken,api_key:key,api_secret:sec})}).then(r=>r.json());
      if(d.ok)setStep(3);else setErr(d.error||"Failed to save.");
    }catch(e){setErr("Network error.");}
    finally{setLoading(false);}
  };

  return(
    <div className="page-sm">
      <div className="steps">{["Create Account","Connect Binance","Complete"].map((l,i)=><div key={i} className={`step${step===i+1?" on":step>i+1?" done":""}`}>{i+1} — {l}</div>)}</div>
      <div className="card au" style={{padding:32}}>
        {step===1&&<>
          <div style={{marginBottom:22}}><div style={{fontSize:20,fontWeight:800,marginBottom:4}}>Create your account</div><div style={{fontSize:13,color:"var(--text2)"}}>Join the AlphaFutures trading network</div></div>
          <div style={{background:"rgba(147,51,234,.08)",border:"1px solid rgba(147,51,234,.2)",borderRadius:10,padding:"13px 16px",fontSize:13,color:"var(--text2)",lineHeight:1.7,marginBottom:22}}>Service fee — <strong style={{color:"var(--gold)"}}>300 THB / month</strong><br/><span style={{fontSize:11,color:"var(--muted)"}}>Admin contacts you after registration</span></div>
          <div className="field"><label className="fl">Email</label><input className="inp" type="email" placeholder="you@example.com" value={email} onChange={e=>setEmail(e.target.value)}/></div>
          <div className="field"><label className="fl">Password</label><input className="inp" type="password" placeholder="At least 8 characters" value={pw} onChange={e=>setPw(e.target.value)}/></div>
          <div className="field"><label className="fl">Confirm Password</label><input className="inp" type="password" placeholder="Re-enter password" value={pw2} onChange={e=>setPw2(e.target.value)}/></div>
          {err&&<div className="err">{err}</div>}
          <button className="btn btn-vi btn-full" onClick={s1} disabled={loading}>{loading?<><Spin/>Creating…</>:"Continue →"}</button>
          <div style={{textAlign:"center",fontSize:13,color:"var(--muted)",marginTop:16}}>Already have an account?{" "}<span style={{color:"var(--vi3)",cursor:"pointer",fontWeight:600}} onClick={()=>nav("login")}>Sign in</span></div>
        </>}
        {step===2&&<>
          <div style={{marginBottom:22}}><div style={{fontSize:20,fontWeight:800,marginBottom:4}}>Connect Binance</div><div style={{fontSize:13,color:"var(--text2)"}}>No keys? <span style={{color:"var(--vi3)",cursor:"pointer",fontWeight:600}} onClick={()=>nav("guide")}>See guide</span></div></div>
          <div className="field"><label className="fl">API Key</label><input className="inp" type="text" placeholder="Paste API Key" value={key} onChange={e=>setKey(e.target.value)} style={{fontFamily:"var(--mono)",fontSize:12}}/></div>
          <div className="field"><label className="fl">API Secret</label><input className="inp" type="password" placeholder="Paste Secret Key" value={sec} onChange={e=>setSec(e.target.value)} style={{fontFamily:"var(--mono)",fontSize:12}}/></div>
          {err&&<div className="err">{err}</div>}
          <button className="btn btn-vi btn-full" onClick={s2} disabled={loading}>{loading?<><Spin/>Saving…</>:"Submit →"}</button>
        </>}
        {step===3&&(
          <div style={{textAlign:"center",padding:"16px 0"}}>
            <div style={{fontSize:52,marginBottom:16}}>⏳</div>
            <div style={{fontSize:20,fontWeight:800,marginBottom:8}}>Pending Approval</div>
            <div style={{fontSize:14,color:"var(--text2)",lineHeight:1.8,marginBottom:24}}>Admin activates your account within 24 hours.</div>
            <div style={{background:"rgba(0,0,0,.3)",borderRadius:10,padding:16,marginBottom:22,border:"1px solid rgba(147,51,234,.2)"}}>
              <div style={{fontSize:10,color:"var(--muted)",fontWeight:700,letterSpacing:".08em",textTransform:"uppercase",marginBottom:6}}>Your dashboard link</div>
              <span className="mono" style={{color:"var(--vi3)",fontSize:13}}>{window.location.origin}/u/{regToken}</span>
            </div>
            <button className="btn btn-cy btn-full" onClick={()=>nav("login")}>Sign in →</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── CLIENT ── */
function ClientPage({token}){
  const[data,setData]=useState(null);
  const[loading,setLoading]=useState(true);

  const load=useCallback(async()=>{
    try{const d=await fetch("/api/client/"+token).then(r=>r.json());if(d.ok)setData(d);}catch(_){}
    finally{setLoading(false);}
  },[token]);

  useEffect(()=>{load();const id=setInterval(load,5000);return()=>clearInterval(id);},[load]);

  if(loading)return<div className="page"><p style={{color:"var(--muted)"}}>Loading…</p></div>;
  if(!data||!data.active)return(
    <div className="page" style={{textAlign:"center",padding:"80px 20px"}}>
      <div style={{fontSize:52,marginBottom:16}}>⏳</div>
      <div style={{fontSize:20,fontWeight:700,marginBottom:8}}>Pending Activation</div>
      <div style={{fontSize:14,color:"var(--text2)"}}>Your account is pending admin activation.<br/>Please complete payment. Activation within 24 hours.</div>
    </div>
  );

  const pos=data.positions||[];const hist=data.history||[];
  return(
    <div className="page">
      <div className="card au" style={{padding:"20px 24px",marginBottom:14,borderLeft:"3px solid var(--vi2)"}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",flexWrap:"wrap",gap:12}}>
          <div>
            <div style={{fontSize:10,color:"var(--muted)",fontWeight:700,letterSpacing:".1em",textTransform:"uppercase",marginBottom:5}}>Member Account</div>
            <div style={{fontSize:22,fontWeight:800}}>{data.label||"My Account"}</div>
            <div className="mono dim" style={{fontSize:11,marginTop:4}}>Updated {data.updated_at||"–"}</div>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:10}}><span className="dot dot-g"/><span className="badge b-act" style={{padding:"6px 14px",fontSize:12}}>ACTIVE</span></div>
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:12,marginBottom:14}} className="sg">
        <NStat label="Wallet Balance" target={data.wallet||0}    dec={2} note="USDT" delay="0s"/>
        <NStat label="Available"      target={data.available||0} dec={2} note="USDT" delay=".06s" col="cy"/>
        <NStat label="Open Positions" target={pos.length}        dec={0} note="active" delay=".12s"/>
        <div className="nstat nstat-gr au" style={{animationDelay:".18s"}}>
          <div className="shimmer"/><div className="stat-l">Unrealized PnL</div>
          <div className="stat-v" style={{color:(data.upnl||0)>=0?"var(--green)":"var(--red)"}}>{(data.upnl||0)>=0?"+":""}{fmt(data.upnl,2)}</div>
          <div className="stat-s">USDT · live</div>
          <div className="prog"><div className="pf" style={{width:`${Math.min(Math.abs(data.upnl||0)/Math.max(data.wallet||1,1)*100,100)}%`,background:(data.upnl||0)>=0?"var(--green)":"var(--red)"}}/></div>
        </div>
      </div>

      <div className="card au2" style={{padding:"22px 24px",marginBottom:14}}>
        <div className="sh"><div><div className="sh-t">Open Positions</div><div className="sh-s">Current exposure</div></div></div>
        <div className="dv"/>
        {pos.length===0?<p style={{color:"var(--muted)",fontSize:13,padding:"16px 0",textAlign:"center"}}>No open positions</p>:(
          <div className="tw"><table className="tbl">
            <thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>uPnL</th><th>Liq.</th></tr></thead>
            <tbody>{pos.map((p,i)=>(
              <tr key={i} className="rin" style={{animationDelay:`${i*.07}s`}}>
                <td style={{fontWeight:700}}>{p.symbol}</td>
                <td><span className={`badge b-${p.side.toLowerCase()}`}>{p.side==="LONG"?"▲":"▼"} {p.side}</span></td>
                <td className="mono">{fmt(p.size,4)}</td>
                <td className="mono">{fmt(p.entry_price,2)}</td>
                <td className="mono" style={{color:p.upnl>=0?"var(--green)":"var(--red)"}}>{fmt(p.mark_price,2)}</td>
                <td className={`mono ${p.upnl>=0?"pos":"neg"}`} style={{fontWeight:700}}>{p.upnl>=0?"+":""}{fmt(p.upnl,2)}</td>
                <td className="mono neg">{fmt(p.liq_price,0)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>

      <div className="card au3" style={{padding:"22px 24px"}}>
        <div className="sh"><div><div className="sh-t">Recent Trades</div><div className="sh-s">Last 20 closed</div></div></div>
        <div className="dcy"/>
        {hist.length===0?<p style={{color:"var(--muted)",fontSize:13,padding:"16px 0",textAlign:"center"}}>No closed trades yet</p>:(
          <div className="tw"><table className="tbl">
            <thead><tr><th>Date</th><th>Symbol</th><th>TF</th><th>Side</th><th>Result</th><th>RR</th></tr></thead>
            <tbody>{hist.slice(0,20).map((t,i)=>(
              <tr key={i} className="rin" style={{animationDelay:`${i*.05}s`}}>
                <td className="mono dim" style={{fontSize:11}}>{t.closed_at}</td>
                <td style={{fontWeight:700}}>{(t.symbol||"").replace("USDT","")}/USDT</td>
                <td className="mono dim" style={{fontSize:11}}>{t.timeframe}</td>
                <td><span className={`badge b-${t.side==="LONG"?"long":"short"}`}>{t.side==="LONG"?"▲":"▼"} {t.side}</span></td>
                <td><span className={`badge b-${t.result==="WIN"?"win":"loss"}`}>{REASON[t.close_reason]||t.close_reason}</span></td>
                <td className={`mono ${t.rr>=0?"pos":"neg"}`} style={{fontWeight:700}}>{t.rr>=0?"+":""}{t.rr}R</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}

/* ── GUIDE ── */
function GuidePage({nav}){
  const steps=[
    {n:1,t:"Log in to Binance",b:"Go to binance.com. Desktop browser recommended."},
    {n:2,t:"Open API Management",b:"Click profile icon (top right) → API Management."},
    {n:3,t:"Create New API Key",b:<>Create API → System Generated → label <code style={{background:"rgba(147,51,234,.15)",padding:"2px 8px",borderRadius:4,fontFamily:"var(--mono)",fontSize:12,color:"var(--vi3)"}}>AlphaFutures</code> → Next.</>},
    {n:4,t:"Complete 2FA",b:"OTP from email + Google Authenticator code."},
    {n:5,t:"Set Permissions",b:<div style={{marginTop:10}}>{["✓ Enable Reading","✓ Enable Futures"].map(s=><span key={s} style={{display:"inline-block",background:"rgba(16,185,129,.1)",color:"var(--green)",padding:"3px 10px",borderRadius:5,fontSize:11,fontWeight:700,margin:"2px 3px 2px 0",border:"1px solid rgba(16,185,129,.2)"}}>{s}</span>)}{["✗ Spot & Margin","✗ Withdrawals"].map(s=><span key={s} style={{display:"inline-block",background:"rgba(244,63,94,.1)",color:"var(--red)",padding:"3px 10px",borderRadius:5,fontSize:11,fontWeight:700,margin:"2px 3px 2px 0",border:"1px solid rgba(244,63,94,.2)"}}>{s}</span>)}<div style={{marginTop:10,background:"rgba(251,191,36,.07)",border:"1px solid rgba(251,191,36,.2)",borderRadius:8,padding:"11px 14px",fontSize:13,color:"var(--gold)"}}>⚠ Never enable Withdrawals.</div></div>},
    {n:6,t:"Restrict to Server IP",b:<>IP: <code style={{background:"rgba(147,51,234,.15)",padding:"2px 9px",borderRadius:4,fontFamily:"var(--mono)",fontSize:12,color:"var(--vi3)"}}>45.77.38.167</code></>},
    {n:7,t:"Copy Both Keys",b:<><span style={{color:"var(--gold)",fontWeight:600}}>⚠ Secret is shown once only.</span> Save immediately.</>},
    {n:8,t:"Paste into Register",b:"Enter keys on Register page. Admin activates within 24h.",cta:true},
  ];
  return(
    <div className="page-sm">
      <div style={{marginBottom:18}}><div style={{fontSize:18,fontWeight:800,marginBottom:2}}>How to Create a Binance API Key</div><div style={{fontSize:13,color:"var(--text2)"}}>Follow each step carefully</div></div>
      {steps.map((s,i)=>(
        <div key={i} className="card" style={{padding:"18px 20px",marginBottom:10,display:"flex",gap:18,animation:`up .4s ${i*.04}s ease both`}}>
          <div style={{minWidth:36,height:36,borderRadius:"50%",background:"linear-gradient(135deg,var(--vi),#6b21a8)",color:"#fff",fontSize:14,fontWeight:700,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,boxShadow:"0 0 16px rgba(147,51,234,.5)"}}>{s.n}</div>
          <div style={{flex:1}}><div style={{fontWeight:700,fontSize:14,marginBottom:8}}>{s.t}</div><div style={{fontSize:13,color:"var(--text2)",lineHeight:1.75}}>{s.b}</div>{s.cta&&<button className="btn btn-cy" style={{marginTop:16}} onClick={()=>nav("register")}>Go to Register →</button>}</div>
        </div>
      ))}
    </div>
  );
}

/* ── ADMIN ── */
function AdminPage(){
  const[pw,setPw]=useState("");const[auth,setAuth]=useState(false);
  const[accounts,setAccounts]=useState([]);const[err,setErr]=useState("");const[loading,setLoading]=useState(false);

  const doLogin=async()=>{
    setErr("");setLoading(true);
    try{
      const d=await fetch("/api/admin/accounts",{headers:{"X-Admin-Password":pw}}).then(r=>r.json());
      if(d.ok){setAccounts(d.accounts);setAuth(true);}else setErr(d.error||"Wrong password.");
    }catch(e){setErr("Network error.");}
    finally{setLoading(false);}
  };

  const reload=async()=>{
    const d=await fetch("/api/admin/accounts",{headers:{"X-Admin-Password":pw}}).then(r=>r.json());
    if(d.ok)setAccounts(d.accounts);
  };

  const act=(path,body)=>fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Admin-Password":pw},body:JSON.stringify(body)}).then(()=>reload());

  if(!auth)return(
    <div className="page-sm" style={{maxWidth:400}}>
      <div className="card au" style={{padding:32}}>
        <div style={{fontSize:18,fontWeight:800,marginBottom:20}}>🔒 Admin Login</div>
        {err&&<div className="err">{err}</div>}
        <div className="field"><label className="fl">Password</label><input className="inp" type="password" placeholder="Admin password" value={pw} onChange={e=>setPw(e.target.value)} onKeyDown={e=>e.key==="Enter"&&doLogin()} style={{fontFamily:"var(--mono)"}}/></div>
        <button className="btn btn-vi btn-full" onClick={doLogin} disabled={loading}>{loading?<><Spin/>Checking…</>:"Login →"}</button>
      </div>
    </div>
  );

  const members=accounts.filter(a=>a.role!=="admin");
  return(
    <div className="page">
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(120px,1fr))",gap:10,marginBottom:14}}>
        {[{l:"Members",v:members.length,c:""},{l:"Active",v:members.filter(a=>a.active).length,c:"ngr"},{l:"Paid",v:members.filter(a=>a.payment_status==="paid").length,c:"ngr"},{l:"Unpaid",v:members.filter(a=>a.payment_status!=="paid"&&a.payment_status!=="admin").length,c:"ngo"}].map((s,i)=>(
          <div key={i} className="sc"><div className={`sv ${s.c}`}>{s.v}</div><div className="sl">{s.l}</div></div>
        ))}
      </div>
      <div className="card au" style={{padding:"22px 24px"}}>
        <div className="sh"><div className="sh-t">Members</div></div>
        <div className="dv"/>
        <div className="tw"><table className="tbl">
          <thead><tr><th>Name</th><th>Email</th><th>Status</th><th>Payment</th><th>Paid Until</th><th>Days</th><th>API</th><th>Actions</th></tr></thead>
          <tbody>{accounts.map((a,i)=>{
            const isAdm=a.role==="admin";
            return(
              <tr key={i} className="rin" style={{animationDelay:`${i*.06}s`,background:isAdm?"rgba(147,51,234,.04)":""}}>
                <td style={{fontWeight:700}}>{a.label}</td>
                <td className="mono dim" style={{fontSize:11}}>{a.email}</td>
                <td><span className={`badge b-${a.active?"act":"ina"}`}>{a.active?"ACTIVE":"INACTIVE"}</span></td>
                <td>{isAdm?<span className="badge b-vi">ADMIN</span>:a.payment_status==="paid"?<span className="badge b-win">Paid</span>:<span className="badge b-st">Unpaid</span>}</td>
                <td className="mono dim" style={{fontSize:11}}>{a.paid_until||"—"}</td>
                <td className="mono" style={{fontSize:11,color:a.days_remaining>0?"var(--green)":"var(--muted)"}}>{a.days_remaining>0?`${a.days_remaining}d`:"—"}</td>
                <td className="mono dim" style={{fontSize:11}}>{a.has_api_key?a.api_key_masked:<span style={{color:"var(--red)"}}>None</span>}</td>
                <td>{!isAdm&&<div style={{display:"flex",gap:5}}>
                  <button className={`btn btn-sm ${a.active?"btn-gl":"btn-vi"}`} style={{fontSize:11,color:a.active?"var(--red)":undefined}} onClick={()=>act(a.active?"/api/admin/deactivate":"/api/admin/activate",{id:a.id})}>{a.active?"Deactivate":"Activate"}</button>
                  <button className="btn btn-sm btn-gl" style={{color:"var(--gold)",fontSize:11}} onClick={()=>act("/api/admin/mark_paid",{id:a.id,months:1})}>+1M</button>
                </div>}</td>
              </tr>
            );
          })}</tbody>
        </table></div>
      </div>
    </div>
  );
}

/* ── APP ── */
const TWEAK_DEFAULTS=/*EDITMODE-BEGIN*/{"accentColor":"#9333ea","showTicker":true,"compactMode":false}/*EDITMODE-END*/;

function App(){
  const init=getInitPage();
  const[page,setPage]=useState(init.page);
  const[clientToken,setClientToken]=useState(init.token);
  const[k,setK]=useState(0);
  const[t,setTweak]=useTweaks(TWEAK_DEFAULTS);

  useEffect(()=>{
    const c=t.accentColor||"#9333ea";
    document.documentElement.style.setProperty("--vi",c);
    const r=parseInt(c.slice(1,3),16),g=parseInt(c.slice(3,5),16),b=parseInt(c.slice(5,7),16);
    document.documentElement.style.setProperty("--vi2",`rgba(${r},${g},${b},1)`);
    document.documentElement.style.setProperty("--vi3",`rgba(${Math.min(r+20,255)},${Math.min(g+20,255)},${Math.min(b+12,255)},1)`);
  },[t.accentColor]);

  useEffect(()=>{
    const h=()=>{const i=getInitPage();setPage(i.page);setClientToken(i.token);setK(n=>n+1);};
    window.addEventListener("popstate",h);return()=>window.removeEventListener("popstate",h);
  },[]);

  const nav=(p,opts={})=>{
    const tok=opts.token!==undefined?opts.token:clientToken;
    if(opts.token!==undefined)setClientToken(opts.token);
    setPage(p);setK(n=>n+1);
    const path=p==="dashboard"?"/" : p==="client"?`/u/${tok}` : `/${p}`;
    history.pushState({},"",path);
  };

  const noNav=["login","register"].includes(page);
  return(
    <div style={{minHeight:"100vh"}}>
      {t.showTicker&&<Ticker/>}
      {!noNav&&<Topbar page={page} nav={nav}/>}
      <div key={k}>
        {page==="dashboard"&&<DashboardPage/>}
        {page==="history"  &&<HistoryPage/>}
        {page==="board"    &&<BoardPage/>}
        {page==="login"    &&<LoginPage nav={nav} onLogin={tok=>nav("client",{token:tok})}/>}
        {page==="register" &&<RegisterPage nav={nav}/>}
        {page==="guide"    &&<GuidePage nav={nav}/>}
        {page==="client"   &&<ClientPage token={clientToken}/>}
        {page==="admin"    &&<AdminPage/>}
      </div>
      <TweaksPanel>
        <TweakSection label="Theme"/>
        <TweakColor label="Accent Color" value={t.accentColor} onChange={v=>setTweak("accentColor",v)}/>
        <TweakSection label="Layout"/>
        <TweakToggle label="Price Ticker" value={t.showTicker} onChange={v=>setTweak("showTicker",v)}/>
        <TweakToggle label="Compact Mode" value={t.compactMode} onChange={v=>setTweak("compactMode",v)}/>
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
</script>
</body>
</html>"""
    )
