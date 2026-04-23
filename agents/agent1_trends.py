"""
agent1_trends.py — Agent Tendances & Demande
Sources : Google Trends, Amazon Best Sellers, Amazon Movers & Shakers
"""

import asyncio
import logging
from typing import Optional
from apify_client import ApifyClient
from pytrends.request import TrendReq
from config import APIFY_API_KEY, ACTORS, MARKETS, SCORING, TIME_WINDOWS

logger = logging.getLogger(__name__)


class Agent1Trends:
    """
    Valide la demande réelle et la tendance d'un produit sur les marchés cibles.
    Score max : 45 points (30 bruts x coefficient 1.5)
    """

    def __init__(self):
        self.apify    = ApifyClient(APIFY_API_KEY)
        self.pytrends = TrendReq(hl="en-US", tz=360)
        self.actor_log = {"success": [], "failed": []}

    # ──────────────────────────────────────────────
    # POINT D'ENTRÉE PRINCIPAL
    # ──────────────────────────────────────────────
    async def analyze(self, product_name: str, markets: list[str]) -> dict:
        """Lance toutes les analyses en parallèle et retourne un rapport."""
        logger.info(f"[Agent1] Analyse tendances pour : {product_name}")

        trends_task  = asyncio.to_thread(self._google_trends, product_name, markets)
        amazon_task  = asyncio.to_thread(self._amazon_best_sellers, product_name, markets)

        trends_result, amazon_result = await asyncio.gather(
            trends_task, amazon_task, return_exceptions=True
        )

        # Gérer les erreurs sans tout faire planter
        if isinstance(trends_result, Exception):
            logger.warning(f"[Agent1] Google Trends échoué : {trends_result}")
            trends_result = self._empty_trends()

        if isinstance(amazon_result, Exception):
            logger.warning(f"[Agent1] Amazon échoué : {amazon_result}")
            amazon_result = self._empty_amazon()

        report = self._build_report(product_name, trends_result, amazon_result)
        return report

    # ──────────────────────────────────────────────
    # GOOGLE TRENDS
    # ──────────────────────────────────────────────
    def _google_trends(self, keyword: str, markets: list[str]) -> dict:
        results = {}
        for market in markets:
            country_code = MARKETS.get(market, {}).get("country_code", "US")
            try:
                self.pytrends.build_payload(
                    [keyword],
                    timeframe=TIME_WINDOWS["google_trends"],  # 3 mois glissants
                    geo=country_code
                )
                data = self.pytrends.interest_over_time()
                if data.empty:
                    results[market] = {"avg_index": 0, "trend": "inconnu", "raw": []}
                    continue

                values   = data[keyword].tolist()
                avg      = round(sum(values) / len(values), 1)
                first_h  = sum(values[:len(values)//2])
                second_h = sum(values[len(values)//2:])
                if second_h > first_h * 1.1:
                    trend_dir = "hausse"
                elif second_h < first_h * 0.9:
                    trend_dir = "baisse"
                else:
                    trend_dir = "stable"

                results[market] = {
                    "avg_index" : avg,
                    "trend"     : trend_dir,
                    "raw"       : values[-12:],   # 12 dernières semaines
                }
            except Exception as e:
                logger.warning(f"[Agent1] Trends {market} : {e}")
                results[market] = {"avg_index": 0, "trend": "erreur", "raw": []}

        return results

    # ──────────────────────────────────────────────
    # AMAZON BEST SELLERS via Apify
    # ──────────────────────────────────────────────
    def _amazon_best_sellers(self, keyword: str, markets: list[str]) -> dict:
        results = {}
        for market in markets:
            domain = MARKETS.get(market, {}).get("amazon_domain", "amazon.com")
            try:
                # junglee/Amazon-crawler attend des URLs de recherche Amazon
                kw_encoded = keyword.replace(" ", "+")
                domain = MARKETS[market]["amazon_domain"]
                amazon_url = f"https://www.{domain}/s?k={kw_encoded}"
                run_input = {
                    "categoryOrProductUrls": [{"url": amazon_url}],
                    "maxItemsPerStartUrl"  : 10,
                    "scrapeProductDetails" : False,   # plus rapide
                }
                run = self.apify.actor(ACTORS["amazon"]).call(run_input=run_input)
                items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())
                if items and ACTORS["amazon"] not in self.actor_log["success"]:
                    self.actor_log["success"].append(ACTORS["amazon"])

                products = []
                for item in items[:10]:
                    # Le crawler retourne price comme float direct ou dans price.value
                    price_raw = item.get("price")
                    price_val = None
                    if isinstance(price_raw, (int, float)):
                        price_val = price_raw
                    elif isinstance(price_raw, dict):
                        price_val = price_raw.get("value") or price_raw.get("amount")
                    products.append({
                        "title"       : item.get("title", "") or item.get("name", ""),
                        "price"       : price_val,
                        "rating"      : item.get("stars") or item.get("rating"),
                        "reviews"     : item.get("reviewsCount") or item.get("ratingsTotal"),
                        "best_seller" : item.get("isBestSeller", False),
                        "url"         : item.get("url", "") or item.get("link", ""),
                        "asin"        : item.get("asin", ""),
                    })

                results[market] = {
                    "domain"      : domain,
                    "products"    : products,
                    "top_result"  : products[0] if products else None,
                    "avg_reviews" : (
                        round(sum(p["reviews"] or 0 for p in products) / len(products), 0)
                        if products else 0
                    ),
                }
            except Exception as e:
                logger.warning(f"[Agent1] Amazon {market} : {e}")
                results[market] = {"domain": domain, "products": [], "top_result": None, "avg_reviews": 0}
                if ACTORS["amazon"] not in self.actor_log["failed"] and ACTORS["amazon"] not in self.actor_log["success"]:
                    self.actor_log["failed"].append(f'{ACTORS["amazon"]} ({str(e)[:60]})')

        return results

    # ──────────────────────────────────────────────
    # SCORING (30 pts bruts → x1.5 = 45 max)
    # ──────────────────────────────────────────────
    def _score(self, trends: dict, amazon: dict) -> dict:
        points = 0
        details = {}

        # ① Google Trends index moyen > 50 → 10 pts
        avg_indexes = [v["avg_index"] for v in trends.values() if v["avg_index"] > 0]
        global_avg  = round(sum(avg_indexes) / len(avg_indexes), 1) if avg_indexes else 0
        if global_avg >= SCORING["google_trends_min_index"]:
            points += 10
        details["google_trends_index"] = {"value": global_avg, "points": 10 if global_avg >= 50 else 0}

        # ② Tendance stable ou en hausse → 8 pts
        hausse_count = sum(1 for v in trends.values() if v["trend"] == "hausse")
        stable_count = sum(1 for v in trends.values() if v["trend"] == "stable")
        trend_ok = (hausse_count + stable_count) >= len(trends) * 0.6
        if trend_ok:
            points += 8
        details["trend_direction"] = {"value": "positif" if trend_ok else "négatif", "points": 8 if trend_ok else 0}

        # ③ Présent sur Amazon avec des avis → 7 pts
        has_amazon_presence = any(
            r["top_result"] is not None and (r["top_result"].get("reviews") or 0) >= SCORING["amazon_reviews_min"]
            for r in amazon.values()
        )
        if has_amazon_presence:
            points += 7
        details["amazon_presence"] = {"value": has_amazon_presence, "points": 7 if has_amazon_presence else 0}

        # ④ Best Seller badge sur Amazon → 5 pts
        has_best_seller = any(
            any(p.get("best_seller") for p in r["products"])
            for r in amazon.values()
        )
        if has_best_seller:
            points += 5
        details["amazon_best_seller"] = {"value": has_best_seller, "points": 5 if has_best_seller else 0}

        weighted = round(points * 1.5, 1)
        return {"raw": points, "weighted": weighted, "max": 45, "details": details}

    # ──────────────────────────────────────────────
    # RAPPORT FINAL
    # ──────────────────────────────────────────────
    def _build_report(self, product: str, trends: dict, amazon: dict) -> dict:
        score = self._score(trends, amazon)

        # Tendance globale lisible
        trend_summary = {}
        for market, data in trends.items():
            trend_summary[market] = f"{data['trend'].upper()} (index moy. {data['avg_index']})"

        # Meilleur produit Amazon toutes régions confondues
        best_amazon = None
        for data in amazon.values():
            if data["top_result"]:
                r = data["top_result"].get("reviews") or 0
                if best_amazon is None or r > (best_amazon.get("reviews") or 0):
                    best_amazon = data["top_result"]

        verdict = (
            "✅ VALIDE"   if score["weighted"] >= 30 else
            "⚠️ MITIGÉ"  if score["weighted"] >= 18 else
            "❌ REJETER"
        )

        return {
            "agent"         : "Agent1_Trends",
            "actor_log"     : self.actor_log,
            "product"       : product,
            "google_trends" : trend_summary,
            "amazon"        : {
                "best_result" : best_amazon,
                "by_market"   : {m: d["top_result"] for m, d in amazon.items()},
            },
            "score"         : score,
            "verdict"       : verdict,
        }

    def _empty_trends(self):
        return {m: {"avg_index": 0, "trend": "inconnu", "raw": []} for m in MARKETS}

    def _empty_amazon(self):
        return {m: {"domain": "", "products": [], "top_result": None, "avg_reviews": 0} for m in MARKETS}
