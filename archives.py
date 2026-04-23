"""
archives.py — Gestion des archives des sessions de recherche
Sauvegarde chaque session dans un fichier JSON local.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import os
# En production (Render), stocker sur le disque persistant /data
# En local, stocker dans le dossier courant
_DATA_DIR = os.environ.get("RENDER_DISK_PATH", os.environ.get("DATA_DIR", "."))
ARCHIVES_FILE = Path(_DATA_DIR) / "archives.json"

def load_archives() -> list:
    if not ARCHIVES_FILE.exists():
        return []
    try:
        with open(ARCHIVES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_session(config: dict, results: list, xlsx_path: str = None) -> dict:
    """Sauvegarde une session dans les archives."""
    archives = load_archives()
    
    session = {
        "id"         : datetime.now().strftime("%Y%m%d_%H%M%S"),
        "date"       : datetime.now().isoformat(),
        "date_label" : datetime.now().strftime("%d/%m/%Y à %H:%M"),
        "niche"      : config.get("niche", ""),
        "markets"    : config.get("markets", []),
        "budget"     : config.get("budget", ""),
        "days_window": config.get("days_window", 60),
        "dry_run"    : config.get("dry_run", True),
        "keywords"   : config.get("keywords", []),
        "comment_kw" : config.get("comment_kw", []),
        "total_products": len(results),
        "winners"    : len([r for r in results if "GAGNANT" in r.get("final_score", {}).get("status", "")]),
        "potentials" : len([r for r in results if "POTENTIEL" in r.get("final_score", {}).get("status", "")]),
        "xlsx_path"  : str(xlsx_path) if xlsx_path else None,
        "top5"       : [
            {
                "product": r.get("product", ""),
                "status" : r.get("final_score", {}).get("status", ""),
                "score"  : r.get("final_score", {}).get("total", 0),
            }
            for r in sorted(results, key=lambda x: x.get("final_score", {}).get("total", 0), reverse=True)[:5]
        ],
    }
    
    archives.insert(0, session)  # Plus récent en premier
    archives = archives[:50]      # Garder les 50 dernières sessions max
    
    with open(ARCHIVES_FILE, "w", encoding="utf-8") as f:
        json.dump(archives, f, ensure_ascii=False, indent=2)
    
    return session

def get_archives() -> list:
    return load_archives()

def delete_session(session_id: str) -> bool:
    archives = load_archives()
    archives = [a for a in archives if a["id"] != session_id]
    with open(ARCHIVES_FILE, "w", encoding="utf-8") as f:
        json.dump(archives, f, ensure_ascii=False, indent=2)
    return True
