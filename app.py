"""
app.py — Serveur web Flask
Interface graphique pour Product Finder avec progression en temps réel (SSE).
Lancement : python app.py  →  http://localhost:5000
"""

import asyncio
import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template_string, request, send_file
from archives import save_session, get_archives, delete_session

app = Flask(__name__)

# ─── File de messages pour le SSE ───
_progress_queue: queue.Queue = queue.Queue()

# ─── Résultats de la dernière session ───
_last_results  = []
_last_config   = {}
_last_xlsx     = None
_session_running = False


# ══════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/run", methods=["POST"])
def api_run():
    global _session_running
    if _session_running:
        return jsonify({"error": "Une session est déjà en cours."}), 409

    data = request.get_json()
    config = {
        "niche"      : data.get("niche", "").strip(),
        "markets"    : data.get("markets", ["USA"]),
        "budget"     : data.get("budget", "500$ – 2 000$"),
        "dry_run"    : data.get("dry_run", True),
        "keywords"    : data.get("keywords", []),
        "comment_kw"  : data.get("comment_kw", []),
        "days_window" : data.get("days_window", 60),
        "sources"     : data.get("sources", ["facebook_ads","amazon","tiktok_videos","tiktok_comments","google_trends","aliexpress"]),
    }

    thread = threading.Thread(target=_run_session, args=(config,), daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/progress")
def api_progress():
    """Server-Sent Events — stream de progression en temps réel."""
    def generate():
        while True:
            try:
                msg = _progress_queue.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") == "done" or msg.get("type") == "error":
                    break
            except queue.Empty:
                yield "data: {\"type\": \"ping\"}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/results")
def api_results():
    return jsonify({"results": _format_results(_last_results), "config": _last_config})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Analyse un produit à partir d'URLs via agent5."""
    data = request.get_json(force=True)
    urls = data.get("urls", [])
    dry_run = data.get("dry_run", True)

    if not urls:
        return jsonify({"error": "Aucune URL fournie"})

    if dry_run:
        # Simulation d'analyse
        import random
        score = random.randint(55, 88)
        verdict = "LANCER" if score >= 70 else "CREUSER" if score >= 50 else "ABANDONNER"
        return jsonify({
            "product_name": "Produit analysé (simulation)",
            "urls": urls,
            "wow_factor": {"score": random.randint(6, 9), "details": "Fort potentiel viral, démonstration facile"},
            "problem_solved": {"description": "Résout un problème quotidien fréquent", "market_size": "Large", "pain_level": "fort"},
            "margin": {"supplier_price": "$8", "sale_price": "$29", "net_margin": "52%", "multiplier": "x3.6"},
            "strengths": ["Fort WOW factor", "Démonstration TikTok facile", "Marge x3 réalisable", "Marché en croissance"],
            "weaknesses": ["Concurrence modérée", "Risque de copies", "SAV à anticiper"],
            "scores": {"wow": random.randint(6,9), "problem": random.randint(6,9), "market": random.randint(5,9),
                      "margin": random.randint(12,18), "logistics": random.randint(6,9), "competition": random.randint(5,8),
                      "marketing": random.randint(10,13), "scalability": random.randint(10,13), "total": score},
            "verdict": verdict,
            "recommendation": f"Ce produit présente un score de {score}/100. {'Lancer une campagne test avec un budget de $300-500 sur TikTok Ads.' if verdict == 'LANCER' else 'Creuser la différenciation avant de lancer.'}",
            "marketing": {"platforms": ["TikTok", "Meta Ads", "YouTube Shorts"], "formats": ["Démonstration avant/après", "Unboxing", "Review vidéo"], "creative_ease": "facile"}
        })

    # Mode réel — utiliser agent5
    try:
        import asyncio
        from agents.agent5_analyzer import Agent5Analyzer
        analyzer = Agent5Analyzer()
        result = asyncio.run(analyzer.analyze(urls))
        return jsonify(result)
    except Exception as e:
        logger.error(f"[api/analyze] {e}")
        return jsonify({"error": str(e)})

@app.route("/api/archives")
def api_archives():
    return jsonify({"archives": get_archives()})

@app.route("/api/archives/<session_id>", methods=["DELETE"])
def api_delete_archive(session_id):
    delete_session(session_id)
    return jsonify({"status": "deleted"})

@app.route("/api/download")
def api_download():
    if _last_xlsx and Path(_last_xlsx).exists():
        return send_file(_last_xlsx, as_attachment=True,
                         download_name=Path(_last_xlsx).name)
    return jsonify({"error": "Aucun fichier disponible"}), 404


# ══════════════════════════════════════════════════════════════
# LOGIQUE DE SESSION (thread séparé)
# ══════════════════════════════════════════════════════════════

def _emit(msg: dict):
    _progress_queue.put(msg)


def _run_session(config: dict):
    global _session_running, _last_results, _last_config, _last_xlsx
    _session_running = True

    try:
        kw_info = f" | Mots-clés: {', '.join(config['keywords'][:2])}" if config.get('keywords') else ""
        ckw_info = f" | Commentaires: {', '.join(config['comment_kw'][:2])}" if config.get('comment_kw') else ""
        niche_disp = "🎲 SURPRISE ME" if config.get('niche') == '__surprise__' else (config.get('niche') or 'Non définie')
        days_disp  = config.get('days_window', 60)
        _emit({"type": "start", "config": config,
               "message": f"🚀 Démarrage — {niche_disp} | {days_disp}j | Mode : {'Simulation' if config['dry_run'] else 'Réel'}{kw_info}{ckw_info}"})

        if config["dry_run"]:
            results, xlsx = _run_dry(config)
        else:
            results, xlsx = _run_real(config)

        _last_results = results
        _last_config  = config
        _last_xlsx    = xlsx

        # Sauvegarder dans les archives
        try:
            save_session(_last_config, results, _last_xlsx)
        except Exception as e:
            logger.warning(f"Archive save failed: {e}")

        _emit({"type": "done",
               "message": f"✅ Session terminée — {len(results)} produits analysés",
               "count"  : len(results)})

    except Exception as e:
        _emit({"type": "error", "message": f"❌ Erreur : {str(e)}"})
    finally:
        _session_running = False


def _run_dry(config):
    """Mode simulation — importe dry_run.py et patch les agents."""
    from mock_data import get_mock_product, MOCK_PRODUCTS
    from utils.scorer   import ProductScorer
    from utils.exporter import ProductExporter

    niche   = config["niche"]
    markets = config["markets"]
    scorer  = ProductScorer()
    exporter= ProductExporter()

    # Récupérer les candidats
    niche_data = MOCK_PRODUCTS.get(niche.lower(), [])
    if niche_data:
        candidates = [p["keyword"] for p in niche_data]
    else:
        candidates = [
            f"{niche} gadget organizer", f"{niche} smart device",
            f"{niche} accessory kit",    f"portable {niche} tool",
            f"mini {niche} cleaner",
        ]

    _emit({"type": "candidates", "count": len(candidates),
           "message": f"📋 {len(candidates)} candidats identifiés pour '{niche}'"})

    results = []
    for i, kw in enumerate(candidates, 1):
        _emit({"type": "analyzing", "index": i, "total": len(candidates),
               "product": kw, "message": f"[{i}/{len(candidates)}] Analyse de : {kw}"})

        time.sleep(0.4)   # simule latence
        mock = get_mock_product(kw, niche)
        result = asyncio.run(_mock_analyze(kw, markets, mock, scorer))
        results.append(result)

        fs = result["final_score"]
        _emit({"type": "result", "product": kw,
               "score": fs["total"], "status": fs["status"],
               "message": f"→ {fs['total']}/190  {fs['status']}"})

    results.sort(key=lambda x: x["final_score"]["total"], reverse=True)

    ts   = datetime.now().strftime("%Y%m%d_%H%M")
    path = f"results_{niche.replace(' ', '_')}_{ts}.xlsx"
    _emit({"type": "exporting", "message": "📁 Export Excel en cours..."})
    exporter.export_all(results, config)
    xlsx = path

    return results, path


def _run_real(config):
    """Mode réel — appelle les vrais agents avec Apify + SSE progress."""
    import builtins, re
    from orchestrator import Orchestrator

    original_print = builtins.print

    def sse_print(*args, **kwargs):
        text = " ".join(str(a) for a in args).strip()
        if not text:
            return
        if "GAGNANT" in text or "POTENTIEL" in text or "REJETER" in text:
            msg_type = "result"
        elif "candidats" in text.lower():
            try:
                m = re.search(r'(\d+)\s+produits?\s+candidats?', text)
                count = int(m.group(1)) if m else 0
                _emit({"type": "candidates", "count": count, "message": text})
                original_print(*args, **kwargs)
                return
            except Exception:
                msg_type = "info"
        elif "Analyse de" in text or "[" in text:
            msg_type = "analyzing"
        else:
            msg_type = "info"
        _emit({"type": msg_type, "message": text})
        original_print(*args, **kwargs)

    builtins.print = sse_print
    try:
        orch    = Orchestrator()
        results = asyncio.run(orch.run_session(config))
    finally:
        builtins.print = original_print

    ts    = datetime.now().strftime("%Y%m%d_%H%M")
    niche = config["niche"].replace(" ", "_")
    path  = f"results_{niche}_{ts}.xlsx"
    _emit({"type": "exporting", "message": "📁 Export Excel en cours..."})
    from utils.exporter import ProductExporter
    ProductExporter().export_all(results, config)
    return results, path


async def _mock_analyze(kw, markets, mock, scorer):
    """Analyse simulée d'un produit (copie de dry_run sans les prints)."""
    from dry_run import MockAgent1Trends, MockAgent2Social, MockAgent3Suppliers, MockAgent4Competition
    a1r, a2r, a3r, a4r = await asyncio.gather(
        MockAgent1Trends().analyze(kw, markets, mock),
        MockAgent2Social().analyze(kw, markets, mock),
        MockAgent3Suppliers().analyze(kw, mock),
        MockAgent4Competition().analyze(kw, markets, mock),
    )
    return {
        "product": kw, "markets": markets,
        "timestamp": datetime.now().isoformat(),
        "agent1": a1r, "agent2": a2r, "agent3": a3r, "agent4": a4r,
        "final_score": scorer.compute_final_score(a1r, a2r, a3r, a4r),
    }


def _format_results(results):
    """Formate les résultats pour le front-end."""
    out = []
    for r in results:
        fs = r.get("final_score", {})
        a3 = r.get("agent3", {})
        a2 = r.get("agent2", {})
        a1 = r.get("agent1", {})
        margin = a3.get("margin", {})
        # Détecter les données manquantes pour affichage
        missing = []
        if not margin.get("sale_price"):
            missing.append("Prix fournisseur")
        if a2.get("facebook", {}).get("unique_advertisers", 0) == 0:
            missing.append("FB Ads")

        out.append({
            "product"       : r.get("product", ""),
            "status"        : fs.get("status", ""),
            "score"         : fs.get("total", 0),
            "pct"           : fs.get("percentage", 0),
            "action"        : fs.get("action", ""),
            "sale_price"    : margin.get("sale_price"),
            "supplier_cost" : margin.get("supplier_cost"),
            "net_margin_pct": margin.get("net_margin_pct"),
            "multiplier"    : margin.get("multiplier"),
            "fb_ads"        : a2.get("facebook", {}).get("unique_advertisers", 0),
            "tiktok_viral"  : a2.get("tiktok", {}).get("viral_videos_count", 0),
            "tiktok_links"  : a2.get("tiktok", {}).get("top_links", [])[:2],
            "fb_links"      : a2.get("facebook", {}).get("sample_links", [])[:2],
            "trends"        : a1.get("google_trends", {}),
            "differentiation": r.get("agent4", {}).get("differentiation", [])[:2],
            "breakdown"     : fs.get("breakdown", {}),
            "suppliers"     : a3.get("suppliers", {}),
            "missing_data"  : missing,
            "verdicts"      : fs.get("verdicts", {}),
            "actor_log"     : r.get("actor_log", {"success": [], "failed": []}),
        })
    return out


# ══════════════════════════════════════════════════════════════
# TEMPLATE HTML — Interface web complète
# ══════════════════════════════════════════════════════════════

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Product Finder</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #080c10;
    --surface:  #0e1520;
    --border:   #1c2a3a;
    --amber:    #f5a623;
    --amber-dim:#9a6510;
    --green:    #22c55e;
    --yellow:   #eab308;
    --red:      #ef4444;
    --text:     #c8d8e8;
    --muted:    #4a6070;
    --mono:     'Space Mono', monospace;
    --sans:     'DM Sans', sans-serif;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ── GRID BG ── */
  body::before {
    content: '';
    position: fixed; inset: 0; z-index: 0;
    background-image:
      linear-gradient(rgba(245,166,35,.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(245,166,35,.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
  }

  .wrap { position: relative; z-index: 1; max-width: 1100px; margin: 0 auto; padding: 0 24px 60px; }

  /* ── HEADER ── */
  header {
    padding: 40px 0 32px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 40px;
    display: flex; align-items: flex-end; justify-content: space-between;
  }
  .logo { display: flex; align-items: center; gap: 14px; }
  .logo-icon {
    width: 44px; height: 44px; border-radius: 10px;
    background: linear-gradient(135deg, var(--amber) 0%, #d97706 100%);
    display: grid; place-items: center; font-size: 20px;
  }
  .logo-text h1 {
    font-family: var(--mono); font-size: 18px; font-weight: 700;
    color: #fff; letter-spacing: -.5px;
  }
  .logo-text p { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .badge {
    font-family: var(--mono); font-size: 10px; padding: 4px 10px;
    border: 1px solid var(--amber-dim); color: var(--amber);
    border-radius: 20px; letter-spacing: 1px;
  }

  /* ── PANELS ── */
  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 28px 32px;
    margin-bottom: 24px;
  }
  .panel-title {
    font-family: var(--mono); font-size: 11px; font-weight: 700;
    color: var(--amber); letter-spacing: 2px; text-transform: uppercase;
    margin-bottom: 24px;
    display: flex; align-items: center; gap: 8px;
  }
  .panel-title::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, var(--border), transparent);
  }

  /* ── FORM ── */
  .form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 16px; }
  .form-grid-wide { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
  @media (max-width: 700px) { .form-grid { grid-template-columns: 1fr; } }

  .field-hint { font-size:10px; font-weight:400; color:var(--muted); padding:2px 7px; background:rgba(245,166,35,.08); border-radius:20px; border:1px solid var(--amber-dim); margin-left:6px; }
  .field-desc { display:block; font-size:11px; color:var(--muted); margin-bottom:6px; line-height:1.5; }
  .kw-input-wrap { display:flex; gap:6px; }
  .kw-input-wrap input { flex:1; }
  .kw-none-btn { padding:8px 14px; border-radius:8px; background:transparent; border:1px solid var(--border); color:var(--muted); font-size:11px; cursor:pointer; white-space:nowrap; transition:all .15s; font-family:var(--sans); }
  .kw-none-btn:hover { border-color:var(--amber-dim); color:var(--amber); }
  .kw-none-btn.active { background:rgba(239,68,68,.1); border-color:#ef4444; color:#ef4444; }
  .field label {
    display: block; font-size: 11px; font-weight: 600;
    color: var(--muted); letter-spacing: 1px; text-transform: uppercase;
    margin-bottom: 8px;
  }
  .field input, .field select {
    width: 100%; padding: 12px 14px;
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text);
    font-family: var(--sans); font-size: 14px;
    transition: border-color .2s;
    outline: none;
  }
  .field input:focus, .field select:focus { border-color: var(--amber); }
  .field select option { background: var(--bg); }

  .checkbox-group { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
  .chip {
    padding: 7px 14px; border-radius: 20px; cursor: pointer;
    border: 1px solid var(--border); font-size: 13px; color: var(--muted);
    transition: all .2s; user-select: none; background: transparent;
  }
  .chip:hover { border-color: var(--amber-dim); color: var(--text); }
  .chip.active { border-color: var(--amber); color: var(--amber); background: rgba(245,166,35,.08); }

  /* Toggle dry run */
  .toggle-row {
    display: flex; align-items: center; gap: 12px;
    margin-top: 20px; padding-top: 20px;
    border-top: 1px solid var(--border);
  }
  .toggle {
    width: 44px; height: 24px; border-radius: 12px;
    background: var(--border); position: relative; cursor: pointer;
    transition: background .2s; flex-shrink: 0;
  }
  .toggle.on { background: var(--amber); }
  .toggle::after {
    content: ''; position: absolute; top: 3px; left: 3px;
    width: 18px; height: 18px; border-radius: 50%;
    background: #fff; transition: transform .2s;
  }
  .toggle.on::after { transform: translateX(20px); }
  .toggle-label { font-size: 13px; color: var(--text); }
  .toggle-label span { color: var(--muted); font-size: 12px; display: block; margin-top: 2px; }

  /* ── BUTTON ── */
  .btn-run {
    margin-top: 24px; width: 100%; padding: 16px;
    background: linear-gradient(135deg, var(--amber) 0%, #d97706 100%);
    border: none; border-radius: 10px; cursor: pointer;
    font-family: var(--mono); font-size: 13px; font-weight: 700;
    color: #000; letter-spacing: 1px; text-transform: uppercase;
    transition: opacity .2s, transform .1s;
  }
  .btn-run:hover:not(:disabled) { opacity: .9; transform: translateY(-1px); }
  .btn-run:disabled { opacity: .4; cursor: not-allowed; transform: none; }

  /* ── PROGRESS ── */
  #progress-panel { display: none; }
  .log-box {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
    font-family: var(--mono); font-size: 12px; line-height: 1.8;
    max-height: 240px; overflow-y: auto;
    color: #7a9ab0;
  }
  .log-box .log-ok    { color: var(--green); }
  .log-box .log-warn  { color: var(--yellow); }
  .log-box .log-err   { color: var(--red); }
  .log-box .log-info  { color: var(--amber); }

  .progress-bar-wrap {
    margin-top: 16px; background: var(--bg);
    border: 1px solid var(--border); border-radius: 4px; height: 6px; overflow: hidden;
  }
  .progress-bar {
    height: 100%; width: 0%;
    background: linear-gradient(90deg, var(--amber), #d97706);
    transition: width .4s ease;
  }

  /* ── RESULTS ── */
  #results-panel { display: none; }
  .result-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 20px; flex-wrap: gap;
  }
  .btn-dl {
    padding: 10px 20px; border-radius: 8px;
    background: transparent; border: 1px solid var(--amber);
    color: var(--amber); font-family: var(--mono); font-size: 11px;
    letter-spacing: 1px; cursor: pointer; transition: all .2s;
  }
  .btn-dl:hover { background: rgba(245,166,35,.1); }

  /* Table */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    font-family: var(--mono); font-size: 10px; font-weight: 700;
    color: var(--muted); letter-spacing: 1.5px; text-transform: uppercase;
    text-align: left; padding: 8px 14px;
    border-bottom: 1px solid var(--border);
  }
  tbody tr {
    border-bottom: 1px solid rgba(28,42,58,.6);
    transition: background .15s; cursor: pointer;
  }
  tbody tr:hover { background: rgba(245,166,35,.04); }
  tbody td { padding: 14px 14px; font-size: 13px; vertical-align: middle; }

  .status-badge {
    padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600;
    font-family: var(--mono); white-space: nowrap;
  }
  .status-winner   { background: rgba(34,197,94,.12);  color: var(--green);  border: 1px solid rgba(34,197,94,.3); }
  .status-potential{ background: rgba(234,179,8,.12);  color: var(--yellow); border: 1px solid rgba(234,179,8,.3); }
  .status-reject   { background: rgba(239,68,68,.12);  color: var(--red);    border: 1px solid rgba(239,68,68,.3); }

  .score-bar-wrap { display: flex; align-items: center; gap: 8px; }
  .score-mini { width: 80px; height: 5px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .score-mini-fill { height: 100%; background: var(--amber); border-radius: 3px; }
  .score-num { font-family: var(--mono); font-size: 12px; color: var(--text); white-space: nowrap; }

  /* ── DETAIL DRAWER ── */
  .drawer-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.7); z-index: 100;
    backdrop-filter: blur(4px);
  }
  .drawer {
    position: fixed; right: 0; top: 0; bottom: 0;
    width: min(520px, 100vw); background: var(--surface);
    border-left: 1px solid var(--border); z-index: 101;
    overflow-y: auto; padding: 32px;
    transform: translateX(100%); transition: transform .3s ease;
  }
  .drawer.open { transform: translateX(0); }
  .drawer-close {
    position: absolute; top: 16px; right: 20px;
    background: none; border: none; color: var(--muted);
    font-size: 20px; cursor: pointer; line-height: 1;
    transition: color .2s;
  }
  .drawer-close:hover { color: var(--text); }
  .drawer h2 { font-size: 16px; font-weight: 600; margin-bottom: 6px; color: #fff; padding-right: 30px; }
  .drawer .sub { font-size: 12px; color: var(--muted); margin-bottom: 24px; }

  .kv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
  .kv {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 12px 14px;
  }
  .kv .k { font-size: 10px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; }
  .kv .v { font-family: var(--mono); font-size: 15px; color: #fff; font-weight: 700; }
  .kv .v.pos { color: var(--green); }
  .kv .v.amber { color: var(--amber); }

  .section-title {
    font-family: var(--mono); font-size: 10px; color: var(--amber);
    letter-spacing: 2px; text-transform: uppercase;
    margin: 20px 0 10px; padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }

  .agent-scores { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .agent-score {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 12px;
  }
  .agent-score .name { font-size: 11px; color: var(--muted); margin-bottom: 6px; }
  .agent-score .bar-row { display: flex; align-items: center; gap: 8px; }
  .mini-bar { flex: 1; height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
  .mini-bar-fill { height: 100%; background: var(--amber); border-radius: 2px; }
  .mini-score { font-family: var(--mono); font-size: 11px; color: var(--text); white-space: nowrap; }

  .link-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
  .link-item {
    padding: 8px 12px; background: var(--bg); border: 1px solid var(--border);
    border-radius: 6px; font-size: 11px; color: var(--amber);
    text-decoration: none; word-break: break-all;
    transition: border-color .2s;
  }
  .link-item:hover { border-color: var(--amber); }

  .tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .tag {
    padding: 4px 10px; border-radius: 4px; font-size: 11px;
    background: rgba(245,166,35,.1); color: var(--amber);
    border: 1px solid rgba(245,166,35,.2);
  }

  /* ── EMPTY STATE ── */
  .empty { text-align: center; padding: 40px 0; color: var(--muted); font-size: 14px; }

  /* Archives panel */
  .archive-item { background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:14px 16px; margin-bottom:10px; display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center; cursor:pointer; transition:border-color .15s; }
  .archive-item:hover { border-color:var(--amber-dim); }
  .archive-meta { font-size:11px; color:var(--muted); margin-top:3px; }
  .archive-stats { display:flex; gap:8px; margin-top:6px; }
  .archive-badge { padding:2px 8px; border-radius:4px; font-size:11px; font-family:var(--mono); }
  .archive-badge.win { background:rgba(34,197,94,.1); color:var(--green); }
  .archive-badge.pot { background:rgba(245,166,35,.1); color:var(--amber); }
  .archive-badge.tot { background:rgba(74,96,112,.15); color:var(--muted); }
  .archive-del { background:none; border:none; color:var(--muted); cursor:pointer; font-size:14px; padding:4px 8px; border-radius:4px; transition:all .15s; }
  .archive-del:hover { background:rgba(239,68,68,.1); color:#ef4444; }
  .archive-title { font-size:14px; font-weight:500; color:var(--text); }
  .archive-top { font-size:11px; color:var(--muted); margin-top:4px; font-style:italic; }

  /* ── Sources checkboxes ── */
  .sources-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:8px; margin-top:8px; }
  .source-chip { display:flex; align-items:center; gap:8px; padding:10px 14px; border-radius:8px; cursor:pointer; border:1px solid var(--border); background:var(--bg); transition:all .2s; user-select:none; }
  .source-chip input[type=checkbox] { display:none; }
  .source-chip:hover { border-color:var(--amber-dim); }
  .source-chip.active { border-color:var(--amber); background:rgba(245,166,35,.07); }
  .source-icon { font-size:16px; }
  .source-name { font-size:12px; color:var(--text); font-weight:500; }
  .source-chip.active .source-name { color:var(--amber); }

  /* ── Mode Analyse Produit ── */
  .analyze-mode-wrap { margin-top:20px; padding-top:20px; border-top:1px solid var(--border); }
  .analyze-toggle-row { display:flex; align-items:center; gap:12px; cursor:pointer; }
  .analyze-toggle-row:hover .toggle-label { color:var(--amber); }
  .url-input-row { display:flex; gap:8px; margin-bottom:8px; }
  .product-url-input { flex:1; padding:11px 14px; background:var(--bg); border:1px solid var(--border); border-radius:8px; color:var(--text); font-size:13px; font-family:var(--sans); outline:none; transition:border-color .2s; }
  .product-url-input:focus { border-color:var(--amber); }
  .url-add-btn { padding:0 16px; border-radius:8px; background:rgba(245,166,35,.1); border:1px solid var(--amber-dim); color:var(--amber); font-size:18px; cursor:pointer; transition:all .2s; }
  .url-add-btn:hover { background:rgba(245,166,35,.2); }
  .analyze-hint { font-size:11px; color:var(--muted); margin-top:6px; padding:8px 12px; background:rgba(245,166,35,.04); border-radius:6px; border:1px solid rgba(245,166,35,.1); }
  .btn-analyze { background:linear-gradient(135deg,#7c3aed,#5b21b6) !important; }
  .disabled-form { opacity:.4; pointer-events:none; }

  /* ── Panneau résultat analyse ── */
  .analyze-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }
  .analyze-score-total { text-align:center; padding:24px; background:var(--bg); border-radius:12px; border:1px solid var(--border); }
  .analyze-score-num { font-size:48px; font-weight:800; font-family:var(--mono); }
  .analyze-score-num.high { color:var(--green); }
  .analyze-score-num.mid { color:var(--yellow); }
  .analyze-score-num.low { color:var(--red); }
  .analyze-verdict { font-size:12px; letter-spacing:2px; text-transform:uppercase; margin-top:6px; }
  .analyze-section { background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:14px; }
  .analyze-section-title { font-size:11px; font-weight:700; color:var(--amber); letter-spacing:1.5px; text-transform:uppercase; margin-bottom:12px; }
  .score-row { display:flex; justify-content:space-between; align-items:center; padding:4px 0; font-size:13px; }
  .score-row-bar { flex:1; height:4px; background:var(--border); border-radius:2px; overflow:hidden; margin:0 12px; }
  .score-row-fill { height:100%; background:var(--amber); border-radius:2px; transition:width .6s ease; }
  .tag-list { display:flex; flex-wrap:wrap; gap:6px; }
  .tag-green { padding:4px 10px; border-radius:20px; font-size:11px; background:rgba(34,197,94,.1); color:var(--green); border:1px solid rgba(34,197,94,.2); }
  .tag-red { padding:4px 10px; border-radius:20px; font-size:11px; background:rgba(239,68,68,.1); color:var(--red); border:1px solid rgba(239,68,68,.2); }
  .verdict-badge { padding:6px 16px; border-radius:20px; font-size:12px; font-family:var(--mono); font-weight:700; letter-spacing:1px; }
  .verdict-launch { background:rgba(34,197,94,.15); color:var(--green); border:1px solid rgba(34,197,94,.3); }
  .verdict-explore { background:rgba(234,179,8,.15); color:var(--yellow); border:1px solid rgba(234,179,8,.3); }
  .verdict-abandon { background:rgba(239,68,68,.15); color:var(--red); border:1px solid rgba(239,68,68,.3); }
  .analyze-recommendation { font-size:13px; line-height:1.7; color:var(--text); padding:14px 16px; background:rgba(245,166,35,.04); border-radius:8px; border-left:3px solid var(--amber); margin-top:12px; }
  .analyze-loading { text-align:center; padding:40px; color:var(--muted); font-family:var(--mono); }
  .analyze-loading::after { content:""; animation:dots 1.5s infinite; }
  @keyframes dots { 0%{content:"."} 33%{content:".."} 66%{content:"..."} }

  /* Actors panel */
  .actors-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .actors-col h4 { font-family: var(--mono); font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
  .actors-col.ok h4 { color: var(--green); }
  .actors-col.ko h4 { color: var(--red); }
  .actor-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; }
  .actor-item.success { border-color: rgba(34,197,94,.25); background: rgba(34,197,94,.04); }
  .actor-item.failed  { border-color: rgba(239,68,68,.25);  background: rgba(239,68,68,.04); }
  .actor-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
  .actor-dot.s { background: var(--green); }
  .actor-dot.f { background: var(--red); }
  .actor-name { font-family: var(--mono); font-size: 12px; color: var(--text); }
  .actor-reason { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .actor-link { font-size: 11px; color: var(--amber); text-decoration: none; }
  .actor-link:hover { text-decoration: underline; }
  .actors-summary { display: flex; gap: 12px; margin-bottom: 16px; }
  .actors-stat { padding: 8px 16px; border-radius: 8px; font-size: 12px; font-family: var(--mono); }
  .actors-stat.ok { background: rgba(34,197,94,.1); color: var(--green); border: 1px solid rgba(34,197,94,.2); }
  .actors-stat.ko { background: rgba(239,68,68,.1);  color: var(--red);   border: 1px solid rgba(239,68,68,.2); }
  .actors-stat.info { background: rgba(245,166,35,.1); color: var(--amber); border: 1px solid rgba(245,166,35,.2); }

  /* scrollbar */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<div class="wrap">

  <!-- HEADER -->
  <header>
    <div class="logo">
      <div class="logo-icon">🏆</div>
      <div class="logo-text">
        <h1>PRODUCT FINDER</h1>
        <p>Système multi-agents e-commerce</p>
      </div>
    </div>
    <span class="badge">v2.0</span>
  </header>

  <!-- CONFIG PANEL -->
  <div class="panel" id="config-panel">
    <div class="panel-title">⚙ Configuration de la session</div>
    <div class="form-grid">
      <div class="field">
        <label>Niche</label>
        <select id="niche-select" onchange="onNicheChange()">
          <option value="none">None</option>
          <option value="">— Choisir une niche —</option>
          <option value="Health & Wellness">Health & Wellness</option><option value="Pets">Pets</option><option value="Home & Decor">Home & Decor</option><option value="Beauty & Cosmetics">Beauty & Cosmetics</option><option value="Baby & Parenting">Baby & Parenting</option><option value="Fashion & Accessories">Fashion & Accessories</option><option value="Tech & Gadgets">Tech & Gadgets</option><option value="Productivity & Education">Productivity & Education</option><option value="Hobbies & Passions">Hobbies & Passions</option><option value="Sport & Outdoor">Sport & Outdoor</option><option value="Ecology & Sustainable">Ecology & Sustainable</option><option value="Luxury & Premium Lifestyle">Luxury & Premium Lifestyle</option><option value="Surprise Me">Surprise Me</option><option value="Wedding">Wedding</option><option value="Funny">Funny</option><option value="Gifts">Gifts</option><option value="DIY">DIY</option><option value="Car Accessories">Car Accessories</option>
        </select>
      </div>
      <div class="field">
        <label>Sous-niche</label>
        <select id="subniche-select" disabled>
          <option value="none">None</option>
          <option value="all">— Choisir une niche d'abord —</option>
        </select>
      </div>
      <div class="field">
        <label>Fenêtre temporelle</label>
        <select id="days-window">
          <option value="30">30 jours</option>
          <option value="60" selected>60 jours</option>
          <option value="90">90 jours</option>
        </select>
      </div>
      <div class="field">
        <label>Marchés cibles</label>
        <div class="checkbox-group" id="markets">
          <button class="chip active" data-val="USA">🇺🇸 USA</button>
          <button class="chip active" data-val="Canada">🇨🇦 Canada</button>
          <button class="chip" data-val="France">🇫🇷 France</button>
          <button class="chip" data-val="UK">🇬🇧 UK</button>
          <button class="chip" data-val="Germany">🇩🇪 Germany</button>
        </div>
      </div>
    </div>

    <!-- SOURCES CHECKBOXES -->
    <div class="field" style="margin-top:16px">
      <label>Sources de données <span class="field-hint">Sélectionne 1 ou plusieurs</span></label>
      <small class="field-desc">Choisis les plateformes sur lesquelles l'agent va chercher les signaux produit.</small>
      <div class="sources-grid" id="sources-grid">
        <label class="source-chip active" data-source="facebook_ads">
          <input type="checkbox" checked> <span class="source-icon">📘</span>
          <span class="source-name">Facebook Ads</span>
        </label>
        <label class="source-chip active" data-source="amazon">
          <input type="checkbox" checked> <span class="source-icon">🛒</span>
          <span class="source-name">Amazon</span>
        </label>
        <label class="source-chip active" data-source="tiktok_videos">
          <input type="checkbox" checked> <span class="source-icon">🎵</span>
          <span class="source-name">TikTok Vidéos</span>
        </label>
        <label class="source-chip active" data-source="tiktok_comments">
          <input type="checkbox" checked> <span class="source-icon">💬</span>
          <span class="source-name">TikTok Commentaires</span>
        </label>
        <label class="source-chip active" data-source="google_trends">
          <input type="checkbox" checked> <span class="source-icon">📈</span>
          <span class="source-name">Google Trends</span>
        </label>
        <label class="source-chip" data-source="reddit">
          <input type="checkbox"> <span class="source-icon">🤖</span>
          <span class="source-name">Reddit</span>
        </label>
        <label class="source-chip active" data-source="aliexpress">
          <input type="checkbox" checked> <span class="source-icon">🏪</span>
          <span class="source-name">AliExpress</span>
        </label>
        <label class="source-chip" data-source="pinterest">
          <input type="checkbox"> <span class="source-icon">📌</span>
          <span class="source-name">Pinterest</span>
        </label>
        <label class="source-chip" data-source="youtube">
          <input type="checkbox"> <span class="source-icon">▶️</span>
          <span class="source-name">YouTube</span>
        </label>
      </div>
    </div>

    <div class="form-grid-wide">
      <div class="field">
        <label>Mots-clés produits <span class="field-hint">FB Ads · TikTok · Amazon · AliExpress</span></label>
        <small class="field-desc">Mots-clés spécifiques pour scraper les pubs et produits. Sépare par des virgules.</small>
        <div class="kw-input-wrap">
          <input type="text" id="keywords" placeholder="ex : posture corrector, back pain relief, ergonomic…">
          <button class="kw-none-btn" onclick="toggleNone('keywords')">None</button>
        </div>
      </div>
      <div class="field">
        <label>Mots-clés commentaires TikTok <span class="field-hint">Scraping commentaires uniquement</span></label>
        <small class="field-desc">Recherche ces mots dans les commentaires TikTok. Sépare par des virgules.</small>
        <div class="kw-input-wrap">
          <input type="text" id="tiktok-comments-kw" placeholder="ex : where to buy, link, buy this, price…">
          <button class="kw-none-btn" onclick="toggleNone('tiktok-comments-kw')">None</button>
        </div>
      </div>
    </div>

    <div class="toggle-row">
      <div class="toggle on" id="dry-toggle" onclick="toggleDry()"></div>
      <div class="toggle-label">
        Mode simulation (Dry Run)
        <span id="dry-desc">Données simulées — aucun appel API réel</span>
      </div>
    </div>

    <!-- MODE ANALYSE PRODUIT -->
    <div class="analyze-mode-wrap">
      <div class="analyze-toggle-row" onclick="toggleAnalyzeMode()">
        <div class="toggle" id="analyze-toggle"></div>
        <div class="toggle-label">
          🔍 Analyser un produit spécifique
          <span>Colle des liens — TikTok, Amazon, AliExpress, Instagram...</span>
        </div>
      </div>

      <div id="analyze-fields" style="display:none; margin-top:16px">
        <div class="field">
          <label>URLs du produit <span class="field-hint">1 à 5 liens</span></label>
          <small class="field-desc">Colle les liens de vidéos TikTok, pages Amazon, publications Instagram, pages AliExpress du même produit.</small>
          <div id="url-inputs">
            <div class="url-input-row">
              <input type="text" class="product-url-input" placeholder="https://www.tiktok.com/@... ou https://www.amazon.com/dp/...">
              <button class="url-add-btn" onclick="addUrlInput()">+</button>
            </div>
          </div>
          <div class="analyze-hint">
            <span>✅ Compatible :</span> TikTok · Amazon · AliExpress · Instagram · YouTube · Facebook · Shopify · n'importe quel site
          </div>
        </div>
        <button class="btn-run btn-analyze" id="analyze-btn" onclick="runAnalyze()">
          🔍 ANALYSER CE PRODUIT
        </button>
      </div>
    </div>

    <button class="btn-run" id="run-btn" onclick="runSession()">
      ▶ LANCER LA RECHERCHE
    </button>
  </div>

  <!-- PROGRESS PANEL -->
  <div class="panel" id="progress-panel">
    <div class="panel-title">⟳ Progression en temps réel</div>
    <div class="log-box" id="log-box"></div>
    <div class="progress-bar-wrap">
      <div class="progress-bar" id="progress-bar"></div>
    </div>
  </div>

  <!-- RESULTS PANEL -->
  <div class="panel" id="results-panel">
    <div class="result-header">
      <div class="panel-title" style="margin-bottom:0">◈ Résultats</div>
      <button class="btn-dl" onclick="downloadXlsx()">⬇ Télécharger Excel</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Produit</th>
            <th>Statut</th>
            <th>Score</th>
            <th>Prix vente</th>
            <th>Marge nette</th>
            <th>FB Ads</th>
            <th>TikTok viral</th>
          </tr>
        </thead>
        <tbody id="results-body"></tbody>
      </table>
    </div>
  </div>

  <!-- ANALYZE RESULT PANEL -->
  <div class="panel" id="analyze-panel" style="display:none;margin-top:24px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.2rem">
      <div class="panel-title" style="margin-bottom:0">🔍 Analyse Produit</div>
      <div id="analyze-verdict-badge"></div>
    </div>
    <div id="analyze-content"><div class="empty">Lance une analyse pour voir les résultats ici.</div></div>
  </div>

  <!-- ACTORS PANEL -->
  <div id="actorspanel" style="display:none">
    <div class="panel">
      <div class="panel-title">🎭 Actors Apify utilisés</div>
      <div id="actors-content"></div>
    </div>
  </div>

  <!-- ARCHIVES PANEL -->
  <div class="panel" id="archivespanel" style="display:none;margin-top:24px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem">
      <div class="panel-title" style="margin-bottom:0">🗂 Archives des recherches</div>
      <button class="dlbtn" onclick="loadArchives()">↻ Actualiser</button>
    </div>
    <div id="archives-content"><div class="empty">Aucune archive pour l'instant</div></div>
  </div>

  <button class="dlbtn" id="archives-toggle-btn"
    onclick="toggleArchives()"
    style="position:fixed;bottom:24px;right:24px;z-index:50;padding:12px 20px;background:var(--surface);border:1px solid var(--amber-dim);color:var(--amber);font-size:12px;border-radius:24px;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,.4)">
    🗂 Archives
  </button>

</div><!-- /wrap -->

<!-- DRAWER DETAIL -->
<div class="drawer-overlay" id="overlay" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
  <button class="drawer-close" onclick="closeDrawer()">✕</button>
  <div id="drawer-content"></div>
</div>

<script>
  let dryRun = true;
  let allResults = [];
  let progressCount = 0, progressTotal = 0;

  // ── Chips marchés ──
  // ── Source chips ──
const SOURCE_LABELS = {
  facebook_ads: 'FB Ads', tiktok_videos: 'TikTok Vidéos',
  amazon: 'Amazon', aliexpress: 'AliExpress',
  reddit: 'Reddit', pinterest: 'Pinterest', youtube: 'YouTube'
};
function updateKeywordsBadge() {
  const active = [...document.querySelectorAll('.source-chip')]
    .filter(c => c.classList.contains('active'))
    .map(c => SOURCE_LABELS[c.dataset.source])
    .filter(Boolean);
  const badge = document.getElementById('keywords-badge');
  if (badge) badge.textContent = active.length ? active.join(' · ') : 'Aucune source';
}
document.querySelectorAll('.source-chip').forEach(chip => {
  chip.addEventListener('click', function() {
    const cb = this.querySelector('input[type=checkbox]');
    setTimeout(() => {
      this.classList.toggle('active', cb.checked);
      updateKeywordsBadge();
    }, 0);
  });
});
  document.querySelectorAll('.chip').forEach(c => {
    c.addEventListener('click', () => c.classList.toggle('active'));
  });

  function toggleDry() {
    dryRun = !dryRun;
    document.getElementById('dry-toggle').classList.toggle('on', dryRun);
    document.getElementById('dry-desc').textContent = dryRun
      ? 'Données simulées — aucun appel API réel'
      : 'Appels API réels — clé Apify requise';
  }

  function getMarkets() {
    return [...document.querySelectorAll('.chip.active')].map(c => c.dataset.val);
  }

  // ── Lancement ──
  // ── Produits surprise (inattendus et viraux) ──────
  const SURPRISE_POOL = ["magnetic posture ring", "gravity blanket weight", "plant communication device", "anti-snore chin strap", "japanese drawer organizer", "pasta measuring tool", "beard bib catcher", "butter infuser", "corn holder set", "ear cleaning endoscope", "fingernail cleaning brush", "soap saver bag mesh", "shower curtain tightener", "toilet night light sensor", "fridge deodorizer egg", "electric nail file drill", "scalp scrubber silicone", "cooking thermometer instant", "mattress vacuum bag storage", "shoe stretcher plastic", "closet organizer hanging", "bed wedge pillow", "pet hair lint roller self cleaning", "cable management box wood", "wall mounted key holder"];

  // ── Données niches / sous-niches ─────────────────
  const NICHES_DATA = {"Health & Wellness": ["Supplements", "Superfoods", "Nootropics", "Sleep", "Anti-Stress", "Home Fitness", "Hormonal Health", "Immunity", "Biohacking", "Probiotics"], "Pets": ["Premium Clothing", "Personalized Accessories", "Natural Calming Products for Anxious Dogs", "Luxury Accessories", "Nutrition", "Health Products", "Toys", "Grooming", "Transportation", "Gadgets"], "Home & Decor": ["Luxury Decor", "Lighting", "Organization", "Kitchen Gadgets", "Eco Home", "Smart Home", "Perfumes", "Textiles"], "Beauty & Cosmetics": ["Skincare", "Clean Beauty", "Haircare", "Beauty Men", "Beauty Tools", "Kits", "Customize", "Dermatologist"], "Baby & Parenting": ["Montessori", "Security", "Organic Care", "Breastfeeding", "Parents' Organization", "Educational Toys", "Newborn Kits"], "Fashion & Accessories": ["Minimalist", "Streetwear", "Customize", "Jewelry", "Glasses", "Bags", "Sustainable"], "Tech & Gadgets": ["Smartphone", "Desk", "Gaming", "Smart Devices", "Nomadic", "Audio"], "Productivity & Education": ["Tools", "Learning", "Memory", "Training", "Organization", "Focus"], "Hobbies & Passions": ["Gaming", "Art", "DIY", "Collection", "Music", "Outdoor"], "Sport & Outdoor": ["Camping", "Yoga", "Sports", "Fitness", "Journey", "Recovery"], "Ecology & Sustainable": ["Zero Waste", "Eco Home", "Sustainable Fashion", "Natural Cosmetics", "Plastic Alternatives"], "Luxury & Premium Lifestyle": ["Personalized Luxury", "Premium Gifts", "Luxury Decor", "Exclusive Accessories", "Limited Editions"], "Surprise Me": ["Viral Products", "Innovations", "Unique Concepts"], "Wedding": ["Wedding Decor", "Bridal Accessories", "Marie's Accessories", "Guests", "Wedding Gifts"], "Funny": ["Humorous Products", "Fun Gadgets", "Funny Gifts", "Unusual Objects"], "Gifts": ["Women", "Husband", "Girls' Kids", "Kids Boy", "Teenage Girl", "Teenage Boy", "Girl", "Young Men", "Young Women", "Women Bride", "Men Marie", "Seniors"], "DIY": ["Tools", "DIY Home", "Repair", "Workshop Organization", "DIY Accessories"], "Car Accessories": ["Car Interior", "Premium Car Organization", "Cleaning", "Security", "Car Gadgets", "Comfort"]};

  function onNicheChange() {
    const niche = document.getElementById('niche-select').value;
    const sub   = document.getElementById('subniche-select');
    sub.innerHTML = '';
    if (!niche) {
      sub.disabled = true;
      sub.innerHTML = "<option value='all'>— Choisir une niche d\'abord —</option>";
      return;
    }
    sub.disabled = false;
    const noneOpt = document.createElement('option');
    noneOpt.value = 'none'; noneOpt.textContent = 'None';
    sub.appendChild(noneOpt);
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = 'All — toutes les sous-niches';
    sub.appendChild(allOpt);
    (NICHES_DATA[niche] || []).forEach(s => {
      const o = document.createElement('option');
      o.value = s; o.textContent = s;
      sub.appendChild(o);
    });
  }

  function getSearchQuery() {
    const niche = document.getElementById('niche-select').value;
    const sub   = document.getElementById('subniche-select').value;
    if (!niche || niche === 'none') return '';
    if (niche === 'Surprise Me') return '__surprise__';
    if (sub && sub !== 'all' && sub !== 'none') return sub + ' ' + niche;
    return niche;
  }

  function isSurpriseMode() {
    return document.getElementById('niche-select').value === 'Surprise Me';
  }

  function toggleNone(fieldId) {
    const input = document.getElementById(fieldId);
    const btn   = input.nextElementSibling;
    if (input.disabled) {
      input.disabled = false;
      input.value = '';
      btn.classList.remove('active');
      btn.textContent = 'None';
    } else {
      input.disabled = true;
      input.value = '';
      btn.classList.add('active');
      btn.textContent = '✕ None actif';
    }
  }

  function getKeywords() {
    const inp = document.getElementById('keywords');
    if (inp.disabled || !inp.value.trim()) return [];
    return inp.value.split(',').map(k => k.trim()).filter(Boolean);
  }

  function getCommentKeywords() {
    const inp = document.getElementById('tiktok-comments-kw');
    if (inp.disabled || !inp.value.trim()) return [];
    return inp.value.split(',').map(k => k.trim()).filter(Boolean);
  }

  async function runSession() {
    const niche   = getSearchQuery().trim();
    const markets = getMarkets();
    if (!niche) { alert('Choisis une niche dans le menu.'); return; }
    if (!markets.length) { alert('Sélectionne au moins un marché.'); return; }

    document.getElementById('run-btn').disabled = true;
    document.getElementById('progress-panel').style.display = 'block';
    document.getElementById('results-panel').style.display = 'none';
    document.getElementById('log-box').innerHTML = '';
    document.getElementById('progress-bar').style.width = '0%';
    progressCount = 0; progressTotal = 0;

    // Scroll vers la progression
    document.getElementById('progress-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Démarrer le SSE
    const es = new EventSource('/api/progress');
    es.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      handleMessage(msg);
      if (msg.type === 'done' || msg.type === 'error') {
        es.close();
        if (msg.type === 'done') loadResults();
        document.getElementById('run-btn').disabled = false;
      }
    };

    // Appel API pour démarrer
    await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        niche,
        markets,
        budget      : document.getElementById('budget').value,
        dry_run     : dryRun,
        keywords    : getKeywords(),
        comment_kw  : getCommentKeywords(),
        days_window : parseInt(document.getElementById('days-window').value),
        sources     : getSources()
      })
    });
  }

  function handleMessage(msg) {
    const box = document.getElementById('log-box');
    let cls = '';
    if (msg.type === 'done')      cls = 'log-ok';
    else if (msg.type === 'error')cls = 'log-err';
    else if (msg.type === 'result') {
      cls = msg.status.includes('GAGNANT') ? 'log-ok' : msg.status.includes('POTENTIEL') ? 'log-warn' : '';
      progressCount++;
      if (progressTotal) {
        document.getElementById('progress-bar').style.width = `${(progressCount/progressTotal)*100}%`;
      }
    } else if (msg.type === 'candidates') {
      progressTotal = msg.count;
      cls = 'log-info';
    } else if (msg.type === 'analyzing') {
      cls = 'log-info';
    }

    if (msg.message) {
      const line = document.createElement('div');
      if (cls) line.className = cls;
      line.textContent = msg.message;
      box.appendChild(line);
      box.scrollTop = box.scrollHeight;
    }

    if (msg.type === 'done') {
      document.getElementById('progress-bar').style.width = '100%';
    }
  }

  async function loadResults() {
    const r = await fetch('/api/results');
    const data = await r.json();
    allResults = data.results;
    renderTable(allResults);
    renderActors(allResults);
    document.getElementById('results-panel').style.display = 'block';
    document.getElementById('actorspanel').style.display = 'block';
    document.getElementById('results-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function renderActors(results) {
    if (!results || !results.length) return;
    const globalSuccess = [], globalFailed = [];
    results.forEach(r => {
      const log = r.actor_log || {success:[], failed:[]};
      (log.success||[]).forEach(s => { if (!globalSuccess.includes(s)) globalSuccess.push(s); });
      (log.failed||[]).forEach(f => {
        const base = f.split(' (')[0];
        if (!globalSuccess.includes(base) && !globalFailed.find(x => x.startsWith(base))) globalFailed.push(f);
      });
    });
    const AINFO = {
      'junglee/Amazon-crawler': {l:'Amazon Product Scraper', u:'https://apify.com/junglee/Amazon-crawler'},
      'junglee/Amazon-crawler (competition)': {l:'Amazon Scraper (concurrence)', u:'https://apify.com/junglee/Amazon-crawler'},
      'clockworks/tiktok-scraper': {l:'TikTok Scraper', u:'https://apify.com/clockworks/tiktok-scraper'},
      'clockworks/free-tiktok-scraper': {l:'TikTok Data Extractor (gratuit)', u:'https://apify.com/clockworks/free-tiktok-scraper'},
      'apify/facebook-ads-scraper': {l:'Facebook Ads Library Scraper', u:'https://apify.com/apify/facebook-ads-scraper'},
      'devcake/aliexpress-products-scraper': {l:'AliExpress Products Scraper', u:'https://apify.com/devcake/aliexpress-products-scraper'},
      'hello.datawizards/aliexpress-bulk-scraper-pro': {l:'AliExpress Bulk Scraper Pro', u:'https://apify.com/hello.datawizards/aliexpress-bulk-scraper-pro'},
      'epctex/aliexpress-scraper': {l:'AliExpress Scraper (epctex)', u:'https://apify.com/epctex/aliexpress-scraper'},
      'epctex/alibaba-scraper': {l:'Alibaba Scraper', u:'https://apify.com/epctex/alibaba-scraper'},
    };
    function card(raw, type) {
      const name = raw.split(' (')[0];
      const reason = raw.includes('(') ? raw.split('(').slice(1).join('(').replace(/\)$/, '') : '';
      const info = AINFO[name] || AINFO[raw] || {l: name, u: 'https://apify.com/' + name};
      const cls = type === 'success' ? 'success' : 'failed';
      const dot = type === 'success' ? 's' : 'f';
      return '<div class="actor-item ' + cls + '"><div class="actor-dot ' + dot + '"></div><div>' +
        '<div class="actor-name">' + info.l + '</div>' +
        '<div class="actor-reason">' + name + (reason ? ' — ' + reason : '') + '</div>' +
        '<a class="actor-link" href="' + info.u + '" target="_blank">Voir sur Apify \u2192</a>' +
        '</div></div>';
    }
    const ok = globalSuccess.length;
    const ko = globalFailed.length;
    document.getElementById('actors-content').innerHTML =
      '<div class="actors-summary">' +
        '<span class="actors-stat ok">\u2705 ' + ok + ' actor' + (ok>1?'s':'') + ' op\u00e9rationnel' + (ok>1?'s':'') + '</span>' +
        (ko ? '<span class="actors-stat ko">\u274c ' + ko + ' actor' + (ko>1?'s':'') + ' en \u00e9chec</span>' : '') +
        '<span class="actors-stat info">\ud83d\udcca ' + results.length + ' produit' + (results.length>1?'s':'') + ' analys\u00e9' + (results.length>1?'s':'') + '</span>' +
      '</div>' +
      '<div class="actors-grid">' +
        '<div class="actors-col ok"><h4>\u2705 Actors op\u00e9rationnels</h4>' +
          (ok ? globalSuccess.map(s => card(s,'success')).join('') : '<div style="color:var(--muted);font-size:13px">Aucun (mode simulation)</div>') +
        '</div>' +
        '<div class="actors-col ko"><h4>\u274c Actors en \u00e9chec</h4>' +
          (ko ? globalFailed.map(f => card(f,'failed')).join('') : '<div style="color:var(--green);font-size:13px">Tous les actors ont fonctionn\u00e9 \u2705</div>') +
        '</div>' +
      '</div>';
  }

  function renderTable(results) {
    const body = document.getElementById('results-body');
    if (!results.length) {
      body.innerHTML = '<tr><td colspan="8" class="empty">Aucun résultat</td></tr>';
      return;
    }
    body.innerHTML = results.map((r, i) => {
      const cls = r.status.includes('GAGNANT') ? 'status-winner'
                : r.status.includes('POTENTIEL') ? 'status-potential'
                : 'status-reject';
      const pct = (r.score / 190) * 100;
      return `
        <tr onclick="openDrawer(${i})">
          <td><span style="font-family:var(--mono);color:var(--muted);font-size:12px">${i+1}</span></td>
          <td style="font-weight:500;color:#fff;max-width:200px">${r.product}</td>
          <td><span class="status-badge ${cls}">${r.status}</span></td>
          <td>
            <div class="score-bar-wrap">
              <div class="score-mini"><div class="score-mini-fill" style="width:${pct}%"></div></div>
              <span class="score-num">${r.score}/190</span>
            </div>
          </td>
          <td style="font-family:var(--mono);color:var(--amber)">${r.sale_price ? '$' + r.sale_price : '—'}</td>
          <td style="font-family:var(--mono);color:${(r.net_margin_pct||0)>=25?'var(--green)':'var(--yellow)'}">${r.net_margin_pct ? r.net_margin_pct + '%' : '—'}</td>
          <td style="font-family:var(--mono)">${r.fb_ads || 0} annonceurs</td>
          <td style="font-family:var(--mono)">${r.tiktok_viral || 0} vidéos</td>
        </tr>`;
    }).join('');
  }

  // ── DRAWER ──
  function openDrawer(idx) {
    const r = allResults[idx];
    if (!r) return;

    const bk = r.breakdown || {};
    const agents = [
      { name: 'Tendances',    key: 'agent1_trends',     max: 45 },
      { name: 'Social/Pubs',  key: 'agent2_social',     max: 45 },
      { name: 'Fournisseurs', key: 'agent3_suppliers',  max: 70 },
      { name: 'Concurrence',  key: 'agent4_competition',max: 30 },
    ];

    const agentHTML = agents.map(a => {
      const s = (bk[a.key] || {}).score || 0;
      const pct = (s / a.max) * 100;
      return `<div class="agent-score">
        <div class="name">${a.name}</div>
        <div class="bar-row">
          <div class="mini-bar"><div class="mini-bar-fill" style="width:${pct}%"></div></div>
          <span class="mini-score">${s}/${a.max}</span>
        </div>
      </div>`;
    }).join('');

    const fbLinks = (r.fb_links || []).map(l =>
      `<a class="link-item" href="${l}" target="_blank">📣 ${l.substring(0,60)}…</a>`).join('');
    const ttLinks = (r.tiktok_links || []).map(l =>
      `<a class="link-item" href="${l}" target="_blank">🎵 ${l.substring(0,60)}…</a>`).join('');

    const diffTags = (r.differentiation || []).map(d => `<span class="tag">${d}</span>`).join('');

    const trendHTML = Object.entries(r.trends || {}).map(([m, v]) =>
      `<div style="font-size:12px;color:var(--muted);margin-bottom:4px"><b style="color:var(--text)">${m}</b> — ${v}</div>`
    ).join('');

    const statusCls = r.status.includes('GAGNANT') ? 'status-winner'
                    : r.status.includes('POTENTIEL') ? 'status-potential'
                    : 'status-reject';

    document.getElementById('drawer-content').innerHTML = `
      <h2>${r.product}</h2>
      <div class="sub">
        <span class="status-badge ${statusCls}" style="margin-right:8px">${r.status}</span>
        Score global : <b style="color:var(--amber)">${r.score}/190 (${r.pct}%)</b>
      </div>

      <div class="kv-grid">
        <div class="kv"><div class="k">Prix vente cible</div><div class="v amber">${r.sale_price ? '$'+r.sale_price : '—'}</div></div>
        <div class="kv"><div class="k">Coût fournisseur</div><div class="v">${r.supplier_cost ? '$'+r.supplier_cost : '—'}</div></div>
        <div class="kv"><div class="k">Marge nette est.</div><div class="v pos">${r.net_margin_pct ? r.net_margin_pct+'%' : '—'}</div></div>
        <div class="kv"><div class="k">Multiplicateur</div><div class="v">${r.multiplier ? 'x'+r.multiplier : '—'}</div></div>
      </div>

      <div class="section-title">◈ Scores par agent</div>
      <div class="agent-scores">${agentHTML}</div>

      <div class="section-title">◈ Google Trends (3 mois)</div>
      ${trendHTML || '<div style="font-size:12px;color:var(--muted)">Non disponible</div>'}

      <div class="section-title">◈ Pubs Facebook actives (90j)</div>
      <div style="font-size:13px;margin-bottom:8px">
        <span style="color:var(--amber);font-family:var(--mono)">${r.fb_ads}</span>
        <span style="color:var(--muted)"> annonceurs distincts</span>
      </div>
      <div class="link-list">${fbLinks || '<div style="font-size:12px;color:var(--muted)">—</div>'}</div>

      <div class="section-title">◈ TikTok viral (60j)</div>
      <div style="font-size:13px;margin-bottom:8px">
        <span style="color:var(--amber);font-family:var(--mono)">${r.tiktok_viral}</span>
        <span style="color:var(--muted)"> vidéos >100K vues</span>
      </div>
      <div class="link-list">${ttLinks || '<div style="font-size:12px;color:var(--muted)">—</div>'}</div>

      <div class="section-title">◈ Angles de différenciation</div>
      <div class="tag-list">${diffTags || '<span style="font-size:12px;color:var(--muted)">Non analysé</span>'}</div>

      <div class="section-title">◈ Recommandation</div>
      <div style="font-size:13px;color:var(--text);line-height:1.6">${r.action}</div>
    `;

    document.getElementById('overlay').style.display = 'block';
    document.getElementById('drawer').classList.add('open');
  }

  function closeDrawer() {
    document.getElementById('drawer').classList.remove('open');
    document.getElementById('overlay').style.display = 'none';
  }

  function downloadXlsx() {
    window.location.href = '/api/download';
  }

  // ── Sources checkboxes ───────────────────────────
  document.querySelectorAll('.source-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      chip.classList.toggle('active');
      chip.querySelector('input').checked = chip.classList.contains('active');
    });
  });

  function getSources() {
    return [...document.querySelectorAll('.source-chip.active')].map(c => c.dataset.source);
  }

  // ── Mode Analyse Produit ─────────────────────────
  let analyzeMode = false;

  function toggleAnalyzeMode() {
    analyzeMode = !analyzeMode;
    const toggle = document.getElementById('analyze-toggle');
    const fields = document.getElementById('analyze-fields');
    const runBtn = document.getElementById('run-btn');
    toggle.classList.toggle('on', analyzeMode);
    fields.style.display = analyzeMode ? 'block' : 'none';
    runBtn.style.display = analyzeMode ? 'none' : 'block';
    const fg = document.querySelector('.form-grid');
    const fgw = document.querySelector('.form-grid-wide');
    const sg = document.getElementById('sources-grid');
    [fg, fgw, sg].forEach(el => {
      if (el) { el.style.opacity = analyzeMode ? '0.35' : '1'; el.style.pointerEvents = analyzeMode ? 'none' : ''; }
    });
  }

  function addUrlInput() {
    const container = document.getElementById('url-inputs');
    if (container.querySelectorAll('.url-input-row').length >= 5) return;
    const row = document.createElement('div');
    row.className = 'url-input-row';
    row.innerHTML = '<input type="text" class="product-url-input" placeholder="https://...">' +
      '<button class="url-add-btn" onclick="this.parentElement.remove()" style="font-size:14px">✕</button>';
    container.appendChild(row);
  }

  function getProductUrls() {
    return [...document.querySelectorAll('.product-url-input')]
      .map(i => i.value.trim()).filter(v => v.length > 5);
  }

  async function runAnalyze() {
    const urls = getProductUrls();
    if (!urls.length) { alert('Colle au moins une URL de produit.'); return; }
    const btn = document.getElementById('analyze-btn');
    btn.disabled = true; btn.textContent = '⏳ Analyse en cours...';
    document.getElementById('analyze-panel').style.display = 'block';
    document.getElementById('analyze-content').innerHTML = '<div class="analyze-loading">Scraping + analyse Claude en cours</div>';
    document.getElementById('analyze-verdict-badge').innerHTML = '';
    document.getElementById('analyze-panel').scrollIntoView({ behavior: 'smooth' });
    try {
      const resp = await fetch('/api/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls, dry_run: dryRun })
      });
      const data = await resp.json();
      renderAnalysis(data);
    } catch(e) {
      document.getElementById('analyze-content').innerHTML = '<div class="empty">Erreur : ' + e.message + '</div>';
    }
    btn.disabled = false; btn.textContent = '🔍 ANALYSER CE PRODUIT';
  }

  function renderAnalysis(d) {
    if (d.error && !d.scores) {
      document.getElementById('analyze-content').innerHTML = '<div class="empty">Erreur : ' + d.error + '</div>'; return;
    }
    const scores = d.scores || {};
    const total = scores.total || 0;
    const sc = total >= 70 ? 'high' : total >= 50 ? 'mid' : 'low';
    const vc = d.verdict === 'LANCER' ? 'verdict-launch' : d.verdict === 'CREUSER' ? 'verdict-explore' : 'verdict-abandon';
    const ve = d.verdict === 'LANCER' ? '🚀' : d.verdict === 'CREUSER' ? '🔎' : '❌';
    document.getElementById('analyze-verdict-badge').innerHTML = '<span class="verdict-badge ' + vc + '">' + ve + ' ' + (d.verdict||'') + '</span>';
    const scoreItems = [
      {k:'wow',label:'WOW Factor',max:10},{k:'problem',label:'Problème résolu',max:10},
      {k:'market',label:'Potentiel marché',max:10},{k:'margin',label:'Marge',max:20},
      {k:'logistics',label:'Logistique',max:10},{k:'competition',label:'Concurrence',max:10},
      {k:'marketing',label:'Marketing',max:15},{k:'scalability',label:'Scalabilité',max:15}
    ];
    const scoresHtml = scoreItems.map(s => {
      const v = scores[s.k]||0; const pct = Math.round((v/s.max)*100);
      return '<div class="score-row"><span style="color:var(--muted);font-size:12px;width:140px">' + s.label + '</span>' +
        '<div class="score-row-bar"><div class="score-row-fill" style="width:' + pct + '%"></div></div>' +
        '<span style="font-family:var(--mono);font-size:12px">' + v + '/' + s.max + '</span></div>';
    }).join('');
    const m = d.margin || {};
    const strengths = (d.strengths||[]).map(s => '<span class="tag-green">' + s + '</span>').join('');
    const weaknesses = (d.weaknesses||[]).map(w => '<span class="tag-red">' + w + '</span>').join('');
    const platforms = (d.marketing&&d.marketing.platforms||[]).join(' · ');
    const formats = (d.marketing&&d.marketing.formats||[]).join(', ');
    document.getElementById('analyze-content').innerHTML =
      '<div class="analyze-grid">' +
        '<div class="analyze-score-total">' +
          '<div class="analyze-score-num ' + sc + '">' + total + '</div>' +
          '<div style="font-size:13px;color:var(--muted);margin-top:4px">/ 100</div>' +
          '<div class="analyze-verdict" style="color:' + (total>=70?'var(--green)':total>=50?'var(--yellow)':'var(--red)') + '">' + (d.verdict||'') + '</div>' +
          '<div style="font-size:11px;color:var(--muted);margin-top:8px">' + (d.product_name||'') + '</div>' +
        '</div>' +
        '<div class="analyze-section">' +
          '<div class="analyze-section-title">💰 Marge estimée</div>' +
          '<div class="kv-grid" style="grid-template-columns:1fr 1fr;gap:8px">' +
            '<div class="kv"><div class="k">Fournisseur</div><div class="v">' + (m.supplier_price||'—') + '</div></div>' +
            '<div class="kv"><div class="k">Prix vente</div><div class="v">' + (m.sale_price||'—') + '</div></div>' +
            '<div class="kv"><div class="k">Marge nette</div><div class="v">' + (m.net_margin||'—') + '</div></div>' +
            '<div class="kv"><div class="k">Multiplicateur</div><div class="v">' + (m.multiplier||'—') + '</div></div>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="analyze-section"><div class="analyze-section-title">📊 Scores détaillés</div>' + scoresHtml + '</div>' +
      '<div class="analyze-section"><div class="analyze-section-title">✅ Points forts</div><div class="tag-list">' + (strengths||'<span style="color:var(--muted)">—</span>') + '</div></div>' +
      '<div class="analyze-section"><div class="analyze-section-title">⚠️ Points faibles</div><div class="tag-list">' + (weaknesses||'<span style="color:var(--muted)">—</span>') + '</div></div>' +
      (platforms ? '<div class="analyze-section"><div class="analyze-section-title">📣 Marketing</div>' +
        '<div style="font-size:13px;color:var(--text)">Plateformes : ' + platforms + '</div>' +
        (formats ? '<div style="font-size:12px;color:var(--muted);margin-top:4px">Formats : ' + formats + '</div>' : '') + '</div>' : '') +
      (d.recommendation ? '<div class="analyze-recommendation">' + d.recommendation + '</div>' : '');
  }
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    print(f"\n🤖  Product Finder — {'DEV' if debug else 'PROD'} mode")
    print(f"   → http://localhost:{port}")
    app.run(debug=debug, port=port, threaded=True)
