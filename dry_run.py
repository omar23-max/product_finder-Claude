"""
dry_run.py — Mode simulation complète (sans appels API réels)
Lance tout le pipeline avec des données simulées réalistes.
Usage : python dry_run.py
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# ─── On neutralise les imports Apify/pytrends ───
# Les agents sont remplacés par leurs versions simulées ci-dessous.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from config import TARGET_PRODUCTS, SCORING, FINANCE
from mock_data import get_mock_product
from utils.scorer   import ProductScorer
from utils.exporter import ProductExporter


# ══════════════════════════════════════════════════════════════
# AGENTS SIMULÉS
# Chaque agent retourne exactement le même format que le vrai,
# mais depuis mock_data au lieu des API externes.
# ══════════════════════════════════════════════════════════════

class MockAgent1Trends:
    async def analyze(self, product: str, markets: list, mock: dict) -> dict:
        await asyncio.sleep(0.05)  # simule latence réseau
        avg   = mock["trends_avg"]
        direc = mock["trends_dir"]

        # Score
        points = 0
        points += 10 if avg >= SCORING["google_trends_min_index"] else 0
        points += 8  if direc in ["hausse", "stable"] else 0
        points += 7  if mock["amazon_reviews"] >= SCORING["amazon_reviews_min"] else 0
        points += 5  if mock["amazon_reviews"] >= 1000 else 0
        weighted = round(points * 1.5, 1)

        verdict = "✅ VALIDE" if weighted >= 30 else "⚠️ MITIGÉ" if weighted >= 18 else "❌ REJETER"

        return {
            "agent"         : "Agent1_Trends",
            "actor_log"     : {"success": ["junglee/Amazon-crawler"], "failed": []},
            "product"       : product,
            "google_trends" : {m: f"{direc.upper()} (index moy. {avg})" for m in markets},
            "amazon"        : {
                "best_result": {
                    "title"  : f"{product} - Top Amazon",
                    "price"  : mock["amazon_price"],
                    "reviews": mock["amazon_reviews"],
                    "url"    : f"https://www.amazon.com/s?k={product.replace(' ', '+')}",
                },
                "by_market"  : {},
            },
            "score"  : {"raw": points, "weighted": weighted, "max": 45,
                        "details": {
                            "google_trends_index": {"value": avg,  "points": 10 if avg >= 50 else 0},
                            "trend_direction"    : {"value": direc,"points": 8  if direc != "baisse" else 0},
                            "amazon_presence"    : {"value": True, "points": 7},
                        }},
            "verdict": verdict,
        }


class MockAgent2Social:
    async def analyze(self, product: str, markets: list, mock: dict) -> dict:
        await asyncio.sleep(0.05)
        fb_ads    = mock["fb_advertisers"]
        viral     = mock["tiktok_viral"]
        max_views = mock["tiktok_max_views"]

        points = 0
        points += 10 if fb_ads >= SCORING["fb_ads_min_advertisers"] else 0
        points += 8  if viral >= 2 else 0
        points += 7  if viral > 0 else 0
        points += 5  if viral >= 3 else 0
        weighted = round(points * 1.5, 1)

        verdict = "✅ VALIDE" if weighted >= 30 else "⚠️ MITIGÉ" if weighted >= 18 else "❌ REJETER"

        # Générer des liens fictifs mais réalistes
        fb_links = [
            f"https://www.facebook.com/ads/library/?q={product.replace(' ', '+')}&id=sim{i:06d}"
            for i in range(1, min(fb_ads + 1, 4))
        ]
        tiktok_links = [
            f"https://www.tiktok.com/@creator{i}/video/sim{7000000000 + i}"
            for i in range(1, min(viral + 1, 4))
        ]

        return {
            "agent"      : "Agent2_Social",
            "actor_log"  : {"success": ["clockworks/tiktok-scraper"], "failed": ["apify/facebook-ads-scraper (Simulation mode)"]},
            "product"    : product,
            "facebook": {
                "unique_advertisers": fb_ads,
                "sample_links"      : fb_links,
                "dominant_format"   : "vidéo",
                "top_advertisers"   : [f"Brand{i}" for i in range(1, min(fb_ads + 1, 4))],
            },
            "tiktok": {
                "viral_videos_count": viral,
                "top_links"         : tiktok_links,
                "max_views"         : max_views,
                "creative_formats"  : ["démonstration", "avant/après", "lifestyle"][:max(1, viral // 2)],
            },
            "score"  : {"raw": points, "weighted": weighted, "max": 45,
                        "details": {
                            "fb_advertisers": {"value": fb_ads, "points": 10 if fb_ads >= 3 else 0},
                            "tiktok_viral"  : {"value": viral,  "points": 8  if viral >= 2 else 0},
                        }},
            "verdict": verdict,
        }


class MockAgent3Suppliers:
    async def analyze(self, product: str, mock: dict) -> dict:
        await asyncio.sleep(0.05)
        ali_price  = mock["ali_price"]
        ali_rating = mock["ali_rating"]
        ali_orders = mock["ali_orders"]

        # Calcul marge
        sale_price   = round(ali_price * 3.2, 2)
        sale_price   = max(FINANCE["min_sale_price"], min(FINANCE["max_sale_price"], sale_price))
        shipping     = round(sale_price * 0.10, 2)
        ads_cost     = round(sale_price * 0.20, 2)
        platform_fee = round(sale_price * 0.03, 2)
        total_costs  = ali_price + shipping + ads_cost + platform_fee
        net_margin   = round(sale_price - total_costs, 2)
        net_pct      = round((net_margin / sale_price) * 100, 1)
        multiplier   = round(sale_price / ali_price, 1)

        points = 0
        points += 10 if multiplier >= FINANCE["min_margin_multiplier"] else 0
        points += 10 if net_pct >= FINANCE["min_net_margin_pct"] else 0
        points += 7                                             # CJ = livraison rapide simulée
        points += 5  if ali_rating >= SCORING["supplier_min_rating"] else 0
        points += 3                                             # 2+ fournisseurs toujours dispo
        weighted = round(points * 2.0, 1)

        verdict = "✅ VALIDE" if weighted >= 45 else "⚠️ MITIGÉ" if weighted >= 28 else "❌ REJETER"

        ali_url  = f"https://www.aliexpress.com/wholesale?SearchText={product.replace(' ', '+')}"
        alib_url = f"https://www.alibaba.com/trade/search?SearchText={product.replace(' ', '+')}"
        cj_url   = f"https://app.cjdropshipping.com/product.html?q={product.replace(' ', '+')}"

        return {
            "agent"      : "Agent3_Suppliers",
            "actor_log"  : {"success": ["devcake/aliexpress-products-scraper"], "failed": ["hello.datawizards/aliexpress-bulk-scraper-pro (Simulation mode)"]},
            "product"    : product,
            "suppliers": {
                "aliexpress"     : {"name": "AliExpress", "price": ali_price,
                                    "rating": ali_rating, "orders": ali_orders,
                                    "url": ali_url, "shipping": 10},
                "alibaba"        : {"name": "Alibaba", "price": round(ali_price * 0.75, 2),
                                    "rating": 4.4, "orders": None,
                                    "url": alib_url, "shipping": 18},
                "cj_dropshipping": {"name": "CJ Dropshipping", "price": round(ali_price * 1.1, 2),
                                    "rating": 4.6, "orders": None,
                                    "url": cj_url, "shipping": 7},
            },
            "trending_products": {
                "aliexpress": [f"{product} variant A", f"{product} premium", f"{product} mini"],
            },
            "margin": {
                "supplier_cost"  : ali_price,
                "sale_price"     : sale_price,
                "shipping"       : shipping,
                "ads_cost"       : ads_cost,
                "platform_fee"   : platform_fee,
                "net_margin_usd" : net_margin,
                "net_margin_pct" : net_pct,
                "is_profitable"  : net_pct >= FINANCE["min_net_margin_pct"],
                "multiplier"     : multiplier,
            },
            "score"  : {"raw": points, "weighted": weighted, "max": 70,
                        "details": {
                            "margin_multiplier": {"value": multiplier, "points": 10 if multiplier >= 3 else 0},
                            "net_margin"       : {"value": net_pct,    "points": 10 if net_pct >= 25 else 0},
                        }},
            "verdict": verdict,
        }


class MockAgent4Competition:
    async def analyze(self, product: str, markets: list, mock: dict) -> dict:
        await asyncio.sleep(0.05)
        amazon_price = mock["amazon_price"]
        competitors  = [
            {"title": f"{product} - Brand A", "price": amazon_price * 0.9, "rating": 4.2, "reviews": 850,
             "brand": "BrandA", "url": f"https://amazon.com/dp/SIM001"},
            {"title": f"{product} - Brand B", "price": amazon_price,       "rating": 4.5, "reviews": 2300,
             "brand": "BrandB", "url": f"https://amazon.com/dp/SIM002"},
            {"title": f"{product} - Brand C", "price": amazon_price * 1.2, "rating": 3.9, "reviews": 420,
             "brand": "BrandC", "url": f"https://amazon.com/dp/SIM003"},
        ]

        pain_points = [
            f"Plusieurs produits notés < 4 étoiles → qualité perçue faible",
            f"Avis mentionnent des délais de livraison trop longs",
            f"Packaging basique — opportunité de différenciation premium",
        ]
        angles = [
            f"Marché sans géant dominant → opportunité de branding fort",
            f"Positionnement premium possible au-dessus de ${amazon_price:.0f}",
            f"Bundle produit + accessoire pour augmenter panier moyen",
            f"Garantie étendue vs concurrents génériques AliExpress",
        ]

        points = 0
        points += 8   # Pas de géant
        points += 7   # 3 concurrents = marché existant
        points += 7   # 3 marques = pas de monopole
        points += 8   # Différenciation possible
        weighted = round(points * 1.0, 1)

        return {
            "agent"      : "Agent4_Competition",
            "actor_log"  : {"success": ["junglee/Amazon-crawler (competition)"], "failed": []},
            "product"    : product,
            "amazon_competition": {
                "price_range"    : {
                    "min": round(amazon_price * 0.85, 2),
                    "max": round(amazon_price * 1.3,  2),
                    "avg": round(amazon_price, 2),
                },
                "brands"         : ["BrandA", "BrandB", "BrandC"],
                "has_giant"      : False,
                "competitor_urls": [c["url"] for c in competitors],
            },
            "shopify_stores": {"count": 3, "urls": [
                f"https://store1-{product.replace(' ', '-')}.myshopify.com",
                f"https://store2-{product.replace(' ', '-')}.myshopify.com",
            ]},
            "pain_points"    : pain_points,
            "differentiation": angles,
            "score"  : {"raw": points, "weighted": weighted, "max": 30,
                        "details": {
                            "no_giant_brand": {"value": True,  "points": 8},
                            "market_exists" : {"value": 3,     "points": 7},
                            "not_saturated" : {"value": 3,     "points": 7},
                            "differentiation":{"value": True,  "points": 8},
                        }},
            "verdict": "✅ VALIDE",
        }


# ══════════════════════════════════════════════════════════════
# ORCHESTRATEUR DRY RUN
# ══════════════════════════════════════════════════════════════

class DryRunOrchestrator:

    def __init__(self):
        self.a1       = MockAgent1Trends()
        self.a2       = MockAgent2Social()
        self.a3       = MockAgent3Suppliers()
        self.a4       = MockAgent4Competition()
        self.scorer   = ProductScorer()
        self.exporter = ProductExporter()

    def ask_questions(self) -> dict:
        print("\n" + "═"*60)
        print("  🤖  PRODUCT FINDER — MODE DRY RUN (simulation)")
        print("═"*60)
        print("  Aucun appel API réel — données simulées réalistes\n")

        print("📌 Q1 — Niche à explorer ?")
        print("   Exemples : fitness / maison / animaux / cuisine / bureau")
        niche = input("   → ").strip() or "fitness"

        print("\n📌 Q2 — Marchés prioritaires ?")
        print("   1. USA  2. Canada  3. Europe  4. Tous")
        choice = input("   → Choix (1/2/3/4) : ").strip()
        markets = {
            "1": ["USA"], "2": ["Canada"],
            "3": ["France", "UK", "Germany"],
            "4": ["USA", "Canada", "France"],
        }.get(choice, ["USA", "Canada", "France"])

        print("\n📌 Q3 — Budget pub estimé ?")
        print("   1. < 500$   2. 500-2000$   3. > 2000$")
        bc = input("   → Choix (1/2/3) : ").strip()
        budget = {"1": "< 500$", "2": "500$ – 2 000$", "3": "> 2 000$"}.get(bc, "500$ – 2 000$")

        return {"niche": niche, "markets": markets, "budget": budget}

    def _get_candidates(self, niche: str) -> list[str]:
        import random, sys
        sys.path.insert(0, '.')
        from orchestrator import Orchestrator
        # Réutiliser exactement le même mapping que l'orchestrateur réel
        orch = Orchestrator.__new__(Orchestrator)
        return orch._generate_candidates(niche)

    async def _analyze_one(self, keyword: str, niche: str, markets: list) -> dict:
        mock = get_mock_product(keyword, niche)

        # Lancement parallèle des 4 agents
        a1r, a2r, a3r, a4r = await asyncio.gather(
            self.a1.analyze(keyword, markets, mock),
            self.a2.analyze(keyword, markets, mock),
            self.a3.analyze(keyword, mock),
            self.a4.analyze(keyword, markets, mock),
        )

        final = self.scorer.compute_final_score(a1r, a2r, a3r, a4r)

        # Agréger actor_logs
        all_s, all_f = [], []
        for ag in [a1r, a2r, a3r, a4r]:
            for s in ag.get("actor_log", {}).get("success", []):
                if s not in all_s: all_s.append(s)
            for f in ag.get("actor_log", {}).get("failed", []):
                if f.split(" (")[0] not in all_s and f not in all_f: all_f.append(f)

        return {
            "product"    : keyword,
            "markets"    : markets,
            "timestamp"  : datetime.now().isoformat(),
            "agent1"     : a1r,
            "agent2"     : a2r,
            "agent3"     : a3r,
            "agent4"     : a4r,
            "final_score": final,
            "actor_log"  : {"success": all_s, "failed": all_f},
        }

    async def run(self, config: dict) -> list[dict]:
        niche      = config["niche"]
        markets    = config["markets"]
        days       = config.get("days_window", 60)
        niche_disp = "🎲 SURPRISE ME" if niche == "__surprise__" else f"'{niche}'"

        print(f"\n🚀 Démarrage — Niche : {niche_disp} | Marchés : {', '.join(markets)} | {days}j")
        print(f"{'─'*60}")

        candidates = self._get_candidates(niche)
        print(f"📋 {len(candidates)} candidats à analyser\n")

        results = []
        for i, kw in enumerate(candidates, 1):
            print(f"[{i}/{len(candidates)}] ⏳ {kw}...", end=" ", flush=True)
            result = await self._analyze_one(kw, niche, markets)
            results.append(result)
            score  = result["final_score"]["total"]
            status = result["final_score"]["status"]
            print(f"→ {score}/190  {status}")

        # Tri par score décroissant
        results.sort(key=lambda x: x["final_score"]["total"], reverse=True)

        # Résumé console
        print(f"\n{'═'*60}")
        print(f"  🏆  TOP {min(len(results), TARGET_PRODUCTS)} PRODUITS")
        print(f"{'═'*60}")
        print(f"  {'#':<3} {'Produit':<35} {'Score':>7}  {'Statut'}")
        print(f"  {'─'*3} {'─'*35} {'─'*7}  {'─'*14}")
        for i, r in enumerate(results[:TARGET_PRODUCTS], 1):
            fs = r["final_score"]
            print(f"  {i:<3} {r['product'][:35]:<35} {fs['total']:>5}/190  {fs['status']}")

        return results[:TARGET_PRODUCTS]

    async def start(self):
        config   = self.ask_questions()
        products = await self.run(config)

        print(f"\n{'─'*60}")
        print(f"📁 Export des résultats...")
        path = self.exporter.export_all(products, config)
        print(f"   ✅ Fichier Excel  : {path}")
        print(f"   ✅ Fichier JSON   : {path.replace('.xlsx', '.json')}")
        print(f"\n✅ DRY RUN TERMINÉ — {len(products)} fiches générées")
        print(f"{'═'*60}\n")
        return products, config


# ──────────────────────────────────────────────
# LANCEMENT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    from mock_data import get_mock_product
    orchestrator = DryRunOrchestrator()
    asyncio.run(orchestrator.start())
