"""
Remnant — Partitura HTML navigabile (standalone)
Legge brownian_score.json e genera partitura identica all'interfaccia Dash.
Uso:   python3 partitura_html.py
Output: ~/Desktop/partitura_remnant.html
"""

import os, sys, json
import numpy as np
import plotly.graph_objects as go

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
SCORE_PATH = os.path.join(BASE_DIR, "brownian_score.json")
OUT_PATH   = os.path.expanduser("~/Desktop/partitura_remnant.html")

if not os.path.exists(SCORE_PATH):
    print(f"Score non trovata: {SCORE_PATH}")
    sys.exit(1)

with open(SCORE_PATH) as f:
    score = json.load(f)

gestures   = score["gestures"]
n_gestures = len(gestures)

# ── Costanti ──────────────────────────────────────────────────────────────────
DYNAMIC_FORM_COLORS = {
    "Forward":  "#378ADD",
    "Backward": "#E05C5C",
    "Presence": "#5CB85C",
    "Neutral":  "#888888",
}
DIR_GLYPH = {"Forward": "→", "Backward": "←", "Presence": "○", "Neutral": "—"}
DIR_DEFAULT_SYM = {
    "Forward":  "triangle-right",
    "Backward": "triangle-left",
    "Presence": "circle-open",
    "Neutral":  "line-ew",
}
ACCENT_SYMBOL = {
    "release":     ("triangle-up",   10),
    "goal":        ("circle",        11),
    "termination": ("triangle-down", 10),
    "warning":     ("diamond-open",   9),
}
OCTO_CHANNELS = [
    (0,1),(45,2),(90,3),(135,4),(180,5),(225,6),(270,7),(315,8)
]

def channel_label(az):
    az = az % 360
    for i in range(len(OCTO_CHANNELS)):
        a0,c0 = OCTO_CHANNELS[i]
        a1,c1 = OCTO_CHANNELS[(i+1) % len(OCTO_CHANNELS)]
        span  = (a1-a0) % 360
        diff  = (az-a0) % 360
        if diff <= span:
            alpha = round(diff/span,3) if span>0 else 0.0
            if alpha == 0.0: return f"CH{c0}"
            if alpha == 1.0: return f"CH{c1}"
            return f"CH{c0}›CH{c1} {int(alpha*100)}%"
    return "CH1"

def compute_accent(ev_idx, n_ev, tensions, direction):
    if n_ev == 0: return "none"
    goal_idx = int(np.argmax(tensions)) if len(tensions) > 0 else 0
    acc = []
    if ev_idx == 0: acc.append("release")
    if ev_idx == n_ev-1: acc.append("termination")
    if ev_idx == goal_idx: acc.append("goal")
    if direction == "Forward" and ev_idx == n_ev-2 and n_ev > 3: acc.append("warning")
    if not acc: return "none"
    for p in ("goal","release","termination","warning"):
        if p in acc: return p
    return "none"

def build_figure(g):
    from math import gcd as _gcd
    direction  = g.get("dynamic_form", "Neutral")
    dir_color  = DYNAMIC_FORM_COLORS.get(direction, "#888")
    t_start    = g["t_start"]; t_end = g["t_end"]
    events     = g["events"];  n_ev  = len(events)
    g_dur      = max(t_end - t_start, 0.001)
    idx        = g["index"]
    n_gestures = len(gestures)

    INK="black"; INK_MED="#222"; INK_LIGHT="#444"; INK_FAINT="#888"; PAPER="white"

    fig = go.Figure()

    # Header
    fig.add_annotation(x=-g_dur*0.03, y=410,
        text=f"<b>field {idx+1}</b>",
        font=dict(size=11,color=INK,family="Georgia, serif"),
        showarrow=False, xanchor="left", yanchor="bottom")
    fig.add_annotation(x=-g_dur*0.03, y=401,
        text=f"{t_start:.0f}″ — {t_end:.0f}″  ·  {n_ev} eventi",
        font=dict(size=8,color=INK_LIGHT,family="Georgia, serif"),
        showarrow=False, xanchor="left", yanchor="bottom")
    fig.add_annotation(x=g_dur*1.08, y=412,
        text=f"<b>{DIR_GLYPH.get(direction,'—')}</b>",
        font=dict(size=18,color=dir_color,family="Georgia, serif"),
        showarrow=False, xanchor="right", yanchor="bottom")
    fig.add_annotation(x=g_dur*1.08, y=401,
        text=f"<i>{direction}</i>",
        font=dict(size=10,color=dir_color,family="Georgia, serif"),
        showarrow=False, xanchor="right", yanchor="bottom")

    # Nav gesti
    nav = []
    for ni in range(n_gestures):
        nd = gestures[ni].get("dynamic_form","Neutral")
        nc = DYNAMIC_FORM_COLORS.get(nd,"#888")
        nav.append(f"<b>{ni+1}</b>" if ni==idx else
                   f'<span style="color:{nc}">{ni+1}{DIR_GLYPH.get(nd,"—")}</span>')
    fig.add_annotation(x=g_dur*1.08, y=394,
        text="  ".join(nav),
        font=dict(size=8,color=INK_LIGHT,family="Georgia, serif"),
        showarrow=False, xanchor="right", yanchor="bottom")

    # Griglia azimutale
    for deg in range(0,361,45):
        fig.add_shape(type="line",x0=0,x1=g_dur,y0=deg,y1=deg,
            line=dict(color=INK_FAINT,width=0.4,dash="dot"),layer="below")
        fig.add_annotation(x=-g_dur*0.02,y=deg,text=f"{deg}°",
            font=dict(size=7,color=INK_FAINT,family="Georgia, serif"),
            showarrow=False,xanchor="right",yanchor="middle")

    # Asse temporale
    fig.add_shape(type="line",x0=0,x1=g_dur,y0=-5,y1=-5,
        line=dict(color=INK_FAINT,width=0.6))
    tick_step = max(1,round(g_dur/8))
    for tt in range(0,int(g_dur)+1,tick_step):
        fig.add_shape(type="line",x0=tt,x1=tt,y0=-8,y1=-2,
            line=dict(color=INK_FAINT,width=0.6))
        fig.add_annotation(x=tt,y=-13,text=f"{tt}″",
            font=dict(size=7,color=INK_FAINT,family="Georgia, serif"),
            showarrow=False,xanchor="center",yanchor="top")

    # Separatori sotto-gesto
    for s in range(1,4):
        fig.add_shape(type="line",x0=g_dur*s/4,x1=g_dur*s/4,y0=0,y1=360,
            line=dict(color=INK_FAINT,width=0.5,dash="dash"),layer="below")

    # Curva tensione compositiva
    if n_ev > 1:
        t_c   = [ev["t"]-t_start for ev in events]
        ten_c = [ev.get("tension",0.5) for ev in events]
        mn,mx = min(ten_c),max(ten_c)
        tn    = [(v-mn)/max(mx-mn,0.01) for v in ten_c]
        fig.add_trace(go.Scatter(
            x=t_c, y=[374+v*14 for v in tn], mode="lines",
            line=dict(color=dir_color,width=1.2,dash="dot"),
            opacity=0.4, showlegend=False, hoverinfo="skip"))

    # Curva browniana (step_dists)
    step_dists = g.get("step_dists",[])
    if len(step_dists) > 1:
        raw = step_dists[1:]
        tot = sum(raw) if sum(raw)>0 else 1.0
        inv = [tot/(d*len(raw)) if d>0 else 1.0 for d in raw]
        mn2,mx2 = min(inv),max(inv)
        inv_n = [(v-mn2)/max(mx2-mn2,0.01) for v in inv]
        cell_s = [d/tot*g_dur for d in raw]
        tenv = [0.0]
        for s in cell_s: tenv.append(tenv[-1]+s)
        tc = [(tenv[i]+tenv[i+1])/2 for i in range(len(cell_s))]
        fig.add_trace(go.Scatter(
            x=tc, y=[374+v*14 for v in inv_n], mode="lines+markers",
            line=dict(color="#E05C5C",width=1.0),
            marker=dict(size=3,color="#E05C5C"),
            opacity=0.35, showlegend=False, hoverinfo="skip"))

    # Pulse grid (step_dists)
    if len(step_dists) > 1:
        RH_Y = -70
        raw_d = step_dists[1:]
        tot_d = sum(raw_d) if sum(raw_d)>0 else 1.0
        cell_s = [d/tot_d*g_dur for d in raw_d]
        n_steps = len(raw_d)
        CANONICAL_BPM = [
            40,42,44,46,48,50,52,54,56,58,60,63,66,69,72,76,80,84,88,
            92,96,100,104,108,112,116,120,126,132,138,144,152,160,168,176,184,200
        ]
        bpm_s = min(CANONICAL_BPM,
                    key=lambda b: abs(g_dur*b/60.0 - round(g_dur*b/60.0)))
        beat_s = 60.0/bpm_s
        BINARY_D = [1,2,4,8,16,32]
        frac_labels = []
        tick_times  = [0.0]
        for dur_s in cell_s:
            db = dur_s/beat_s
            best_num,best_den,best_err = max(1,round(db)),1,float("inf")
            for den in BINARY_D:
                num = max(1,round(db*den))
                err = abs(num/den-db)
                if err < best_err:
                    best_err=err; best_num,best_den=num,den
            d=_gcd(best_num,best_den)
            fn,fd=best_num//d,best_den//d
            frac_labels.append(f"{fn}/{fd}" if fd>1 else str(fn))
            tick_times.append(tick_times[-1]+dur_s)
        fig.add_shape(type="line",x0=0,x1=g_dur,y0=RH_Y,y1=RH_Y,
            line=dict(color=INK_FAINT,width=0.8))
        fig.add_shape(type="line",x0=g_dur,x1=g_dur,y0=RH_Y-3,y1=RH_Y+3,
            line=dict(color=INK_LIGHT,width=1.0))
        for i,(tt,lbl) in enumerate(zip(tick_times[:-1],frac_labels)):
            if i>0:
                fig.add_shape(type="line",x0=tt,x1=tt,y0=0,y1=360,
                    line=dict(color="#E05C5C",width=1.2),opacity=0.7,layer="below")
            fig.add_shape(type="line",x0=tt,x1=tt,y0=RH_Y-3,y1=RH_Y+3,
                line=dict(color="#E05C5C" if i>0 else INK,width=1.2))
            above = (i%2==1)
            y_t   = RH_Y+(8 if above else -5)
            anc   = "bottom" if above else "top"
            fig.add_annotation(x=tt,y=y_t,
                text=f"<b>{lbl}</b><br><span style='font-size:9px;color:#555'>♩={bpm_s}</span>",
                font=dict(size=11,color=INK,family="Georgia, serif"),
                showarrow=False,xanchor="center",yanchor=anc)
        fig.add_annotation(x=g_dur*1.01,y=RH_Y,text="pulse grid",
            font=dict(size=7,color=INK_FAINT,family="Georgia, serif"),
            showarrow=False,xanchor="left",yanchor="middle")
        fig.add_annotation(x=g_dur*1.01,y=RH_Y-6,text=f"Σ {round(g_dur,2)}s",
            font=dict(size=7,color=INK_FAINT,family="Georgia, serif"),
            showarrow=False,xanchor="left",yanchor="top")

    # Suoni
    dur_min,dur_max_v = 0.4,7.0
    ev_tensions = [ev.get("tension",0.5) for ev in events]
    default_sym = DIR_DEFAULT_SYM.get(direction,"circle-open")
    default_pts = {"x":[],"y":[],"sz":[],"tip":[],"op":[]}
    by_accent   = {}

    for ei,ev in enumerate(events):
        instr   = ev["instrument"]
        mode    = ev.get("mode","")
        t       = ev["t"]-t_start
        azimuth = ev["azimuth"]
        tension = ev.get("tension",0.5)
        accent  = ev.get("accent") or compute_accent(ei,n_ev,ev_tensions,direction)
        t_draw  = t
        dur_vis = dur_min+tension*(dur_max_v-dur_min)
        line_w  = 0.4+tension*2.2
        line_op = 0.35+tension*0.6
        bar_end = min(t_draw+dur_vis,g_dur)

        fig.add_shape(type="line",x0=t_draw,x1=bar_end,y0=azimuth,y1=azimuth,
            line=dict(color=INK,width=line_w),opacity=line_op)
        if bar_end < g_dur:
            fig.add_shape(type="line",x0=bar_end,x1=bar_end,
                y0=azimuth-2,y1=azimuth+2,
                line=dict(color=INK_LIGHT,width=0.6),opacity=line_op)

        mid_x = (t_draw+bar_end)/2
        if t_draw > g_dur*0.72:
            lx,xanc = min(t_draw-2,g_dur*0.97),"right"
        else:
            lx,xanc = mid_x,"center"
        fig.add_annotation(x=lx,y=azimuth,text=instr,
            font=dict(size=10,color=INK_MED,family="Georgia, serif"),
            showarrow=False,xanchor=xanc,yanchor="bottom",
            yshift=5,bgcolor="rgba(255,255,255,0.92)",borderpad=2)

        ch_lbl = ev.get("ch_label",channel_label(azimuth))
        tip = f"<b>{instr}</b>"
        if mode: tip += f"<br><i>{mode}</i>"
        tip += f"<br>t={ev['t']:.1f}s · {azimuth}° · {ch_lbl}<br>{direction} · t={tension:.2f}<br><i>{accent}</i>"

        sz = 6+tension*5
        op = min(line_op+0.15,1.0)
        default_pts["x"].append(t_draw); default_pts["y"].append(azimuth)
        default_pts["sz"].append(sz); default_pts["tip"].append(tip)
        default_pts["op"].append(op)

        if accent not in ("none",None):
            s2 = sz*1.7 if accent=="goal" else sz*1.3
            by_accent.setdefault(accent,{"x":[],"y":[],"sz":[],"tip":[],"op":[]})
            by_accent[accent]["x"].append(t_draw); by_accent[accent]["y"].append(azimuth)
            by_accent[accent]["sz"].append(s2); by_accent[accent]["tip"].append(tip)
            by_accent[accent]["op"].append(min(op+0.1,1.0))

    if default_pts["x"]:
        fig.add_trace(go.Scatter(
            x=default_pts["x"],y=default_pts["y"],mode="markers",
            marker=dict(symbol=default_sym,size=default_pts["sz"],
                        color=INK,line=dict(color=INK,width=1.0),
                        opacity=default_pts["op"]),
            customdata=default_pts["tip"],
            hovertemplate="%{customdata}<extra></extra>",
            showlegend=True,
            name=f"{DIR_GLYPH.get(direction,'—')} {direction}",
            legendgroup="default"))

    ACCENT_LABEL = {"release":"release point ▲","goal":"goal point ●",
                    "termination":"termination ▼","warning":"warning point ◇"}
    for acc_name,data in by_accent.items():
        sym,_ = ACCENT_SYMBOL.get(acc_name,("circle",7))
        fig.add_trace(go.Scatter(
            x=data["x"],y=data["y"],mode="markers",
            marker=dict(symbol=sym,size=data["sz"],color=INK,
                        line=dict(color=INK,width=1.6),opacity=data["op"]),
            customdata=data["tip"],
            hovertemplate="%{customdata}<extra></extra>",
            showlegend=True,name=ACCENT_LABEL.get(acc_name,acc_name),
            legendgroup=acc_name))

    # Canali 8ch
    ch_labels = [
        ("0°","CH1"),("45°","CH2"),("90°","CH3"),("135°","CH4"),
        ("180°","CH5"),("225°","CH6"),("270°","CH7"),("315°","CH8"),
    ]
    step = g_dur/max(len(ch_labels),1)
    for li,(az_l,ch_l) in enumerate(ch_labels):
        lx = li*step
        fig.add_trace(go.Scatter(x=[lx],y=[-28],mode="markers",
            marker=dict(symbol="circle-open" if li%2==0 else "circle",
                        size=6,color=INK,line=dict(color=INK,width=1)),
            showlegend=False,hoverinfo="skip"))
        fig.add_annotation(x=lx+step*0.12,y=-28,
            text=f"{ch_l} {az_l}",
            font=dict(size=7,color=INK_LIGHT,family="Georgia, serif"),
            showarrow=False,xanchor="left",yanchor="middle")

    fig.update_layout(
        paper_bgcolor=PAPER,plot_bgcolor=PAPER,
        margin=dict(l=60,r=40,t=60,b=80),
        font=dict(family="Georgia, serif",size=8,color=INK_LIGHT),
        xaxis=dict(range=[-g_dur*0.04,g_dur*1.12],
            showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(range=[-95,420],showgrid=False,zeroline=False,
            showticklabels=False,side="right"),
        hovermode="closest",dragmode="pan",
        hoverlabel=dict(bgcolor="white",bordercolor=INK_FAINT,
            font_size=10,font_family="Georgia, serif"),
        legend=dict(orientation="h",x=0,y=-0.1,
            font=dict(size=8,color=INK_LIGHT,family="Georgia, serif"),
            bgcolor="rgba(0,0,0,0)",borderwidth=0),
        showlegend=True)

    return fig

# ── Genera le figure ──────────────────────────────────────────────────────────
print(f"Generando {n_gestures} gesti...")
figs_html = []
for i,g in enumerate(gestures):
    fig = build_figure(g)
    fh  = fig.to_html(full_html=False, include_plotlyjs=False,
                      config={"displayModeBar":True,"scrollZoom":True,
                              "toImageButtonOptions":{"format":"png",
                                  "filename":f"partitura_g{i+1}",
                                  "height":700,"width":1600,"scale":2}})
    figs_html.append(fh)
    print(f"  G{i+1}/{n_gestures}")

# Meta per navigazione
meta = [{"idx":g["index"],
         "dir":g.get("dynamic_form","Neutral"),
         "color":DYNAMIC_FORM_COLORS.get(g.get("dynamic_form","Neutral"),"#888"),
         "t0":g.get("t_start",0),
         "t1":g.get("t_end",score.get("duration",0)),
         "n_ev":len(g.get("events",[]))}
        for g in gestures]
meta_js = json.dumps(meta)

# Div per ogni pagina
pages_divs = ""
for i,fh in enumerate(figs_html):
    vis = "visible" if i==0 else "hidden"
    zi  = "1" if i==0 else "0"
    pages_divs += f'<div class="page" id="page-{i}" style="visibility:{vis};z-index:{zi};position:absolute;top:0;left:0;width:100%;height:100%">{fh}</div>\n'

import plotly
plotly_js = plotly.offline.get_plotlyjs()

html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>Remnant — Partitura</title>
<script>{plotly_js}</script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f5f5f0;font-family:Georgia,serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}}
#topbar{{display:flex;align-items:center;padding:8px 20px;border-bottom:1px solid #ddd;background:white;gap:16px;flex-shrink:0;height:48px}}
#title{{font-size:11px;letter-spacing:3px;color:#aaa;font-style:italic;flex:1}}
#gnum{{font-size:20px;font-weight:bold;font-family:"Courier New",monospace;letter-spacing:2px}}
#dlabel{{font-size:13px;font-style:italic}}
#info{{font-size:9px;color:#aaa;font-family:"Courier New",monospace;text-align:right;line-height:1.5}}
#dots{{display:flex;gap:5px;align-items:center}}
.dot{{width:9px;height:9px;border-radius:50%;cursor:pointer;opacity:.35;transition:opacity .15s,transform .15s}}
.dot.active{{opacity:1;transform:scale(1.35)}}
.dot:hover{{opacity:.7}}
#navbtns{{display:flex;gap:6px}}
.nbtn{{background:white;border:1px solid #ccc;color:#666;font-size:16px;width:32px;height:32px;cursor:pointer;border-radius:3px;display:flex;align-items:center;justify-content:center}}
.nbtn:hover{{background:#f0f0f0;color:#111}}
.nbtn:disabled{{opacity:.25;cursor:default}}
#score-wrap{{flex:1;overflow:hidden;position:relative}}
.page{{position:absolute;top:0;left:0;width:100%;height:100%}}
</style>
</head>
<body>
<div id="topbar">
  <div id="title">R E M N A N T &nbsp;·&nbsp; partitura</div>
  <div id="gnum">—</div>
  <div id="dlabel">—</div>
  <div id="info">—</div>
  <div id="dots"></div>
  <div id="navbtns">
    <button class="nbtn" id="btn-prev">&#8592;</button>
    <button class="nbtn" id="btn-next">&#8594;</button>
  </div>
</div>
<div id="score-wrap">
{pages_divs}
</div>
<script>
const META={meta_js},N=META.length;
let cur=0;
const elN=document.getElementById('gnum'),elD=document.getElementById('dlabel'),
      elI=document.getElementById('info'),elDots=document.getElementById('dots'),
      elPrev=document.getElementById('btn-prev'),elNext=document.getElementById('btn-next');
META.forEach((m,i)=>{{
  const d=document.createElement('div');
  d.className='dot'+(i===0?' active':'');
  d.style.background=m.color;
  d.title=`G${{i+1}} — ${{m.dir}}`;
  d.onclick=()=>go(i);
  elDots.appendChild(d);
}});
function go(i){{
  i=Math.max(0,Math.min(N-1,i));
  const prev=document.getElementById('page-'+cur);
  prev.style.visibility='hidden'; prev.style.zIndex='0';
  cur=i;
  const p=document.getElementById('page-'+cur);
  p.style.visibility='visible'; p.style.zIndex='1';
  // Forza resize dopo che il div è visibile
  const pd=p.querySelector('.plotly-graph-div');
  if(pd&&window.Plotly) window.requestAnimationFrame(()=>Plotly.Plots.resize(pd));
  render();
}}
function render(){{
  const m=META[cur];
  elN.textContent=`G${{m.idx+1}} / ${{N}}`;elN.style.color=m.color;
  elD.textContent=m.dir;elD.style.color=m.color;
  elI.innerHTML=`${{m.t0.toFixed(1)}}″ — ${{m.t1.toFixed(1)}}″<br>${{m.n_ev}} eventi`;
  elPrev.disabled=cur===0;elNext.disabled=cur===N-1;
  document.querySelectorAll('.dot').forEach((d,i)=>{{
    d.className='dot'+(i===cur?' active':'');
  }});
}}
elPrev.onclick=()=>go(cur-1);
elNext.onclick=()=>go(cur+1);
document.addEventListener('keydown',e=>{{
  if(e.key==='ArrowRight'||e.key===' ')go(cur+1);
  if(e.key==='ArrowLeft')go(cur-1);
  const n=parseInt(e.key);
  if(!isNaN(n)&&n>=1&&n<=9)go(n-1);
}});
render();
// Forza resize di tutte le figure dopo il caricamento
window.addEventListener('load', () => {{
  document.querySelectorAll('.plotly-graph-div').forEach(pd => {{
    if(window.Plotly) Plotly.Plots.resize(pd);
  }});
}});
</script>
</body>
</html>"""

with open(OUT_PATH,"w",encoding="utf-8") as f:
    f.write(html)

print(f"\n✓ Partitura HTML → {OUT_PATH}")
print(f"  {n_gestures} gesti · {score.get('duration',0)}s totali")
print(f"  Apri nel browser · ← → o tasti 1-9")
