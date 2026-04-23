"""
agent4_competition.py — Agent Concurrence & Positionnement
Sources : Amazon (avis), Google Shopping, Shopify stores
"""

import asyncio
import logging
from apify_client import ApifyClient
from config import APIFY_API_KEY, ACTORS, MARKETS

logger = logging.getLogger(__name__)


class Agent4Competition:
    """
    Cartographie la concurrence et identifie les angles de différenciation.
    Score max : 30 points (30 bruts x coefficient 1.0)
    """

    def __init__(self):
        self.apify     = ApifyClient(APIFY_API_KEY)
        self.actor_log = {"success": [], "failed": []}

    # ──────────────────────────────────────────────
    # POINT D'ENTRÉE PRINCIPAL
    # ──────────────────────────────────────────────
    async def analyze(self, product_name: str, markets: list[str]) -> dict:
        logger.info(f"[Agent4] Analyse concurrence pour : {product_name}")

        amazon_task   = asyncio.to_thread(self._amazon_competition, product_name, markets)
        shopify_task  = asyncio.to_thread(self._shopify_stores, product_name)

        amazon_result, shopify_result = await asyncio.gather(
            amazon_task, shopify_task, return_exceptions=True
        )

        if isinstance(amazon_result, Exception):
            logger.warning(f"[Agent4] Amazon concurrence échoué : {amazon_result}")
            amazon_result = self._empty_amazon()

        if isinstance(shopify_result, Exception):
            logger.warning(f"[Agent4] Shopify stores échoué : {shopify_result}")
            shopify_result = self._empty_shopify()

        return self._build_report(product_name, amazon_result, shopify_result)

    # ──────────────────────────────────────────────
    # AMAZON — Avis concurrents + prix marché
    # ──────────────────────────────────────────────
    def _amazon_competition(self, keyword: str, markets: list[str]) -> dict:
        all_products = []
        review_insights = []

        for market in markets[:2]:   # Limiter à 2 marchés pour l'API
            try:
                kw_encoded = keyword.replace(" ", "+")
                domain = MARKETS[market]["amazon_domain"]
                amazon_url = f"https://www.{domain}/s?k={kw_encoded}"
                run_input = {
                    "categoryOrProductUrls": [{"url": amazon_url}],
                    "maxItemsPerStartUrl"  : 8,
                    "scrapeProductDetails" : False,
                }
                run   = self.apify.actor(ACTORS["amazon"]).call(run_input=run_input)
                items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())
                if items and ACTORS["amazon"] not in self.actor_log["success"]:
                    self.actor_log["success"].append(f'{ACTORS["amazon"]} (competition)')

                for item in items:
                    price_raw = item.get("price")
                    if isinstance(price_raw, (int, float)):
                        price = price_raw
                    elif isinstance(price_raw, dict):
                        price = price_raw.get("value") or price_raw.get("amount")
                    else:
                        price = None

                    all_products.append({
                        "title"   : item.get("title", "")[:60],
                        "price"   : float(price) if price else None,
                        "rating"  : item.get("stars"),
                        "reviews" : item.get("reviewsCount"),
                        "brand"   : item.get("brand", ""),
                        "url"     : item.get("url", ""),
                        "asin"    : item.get("asin", ""),
                        "market"  : market,
                    })

            except Exception as e:
                logger.warning(f"[Agent4] Amazon competition {market} : {e}")
                key = f'{ACTORS["amazon"]} (competition)'
                if key not in self.actor_log["failed"] and key not in self.actor_log["success"]:
                    self.actor_log["failed"].append(f'{key} ({str(e)[:50]})')

        # Analyse des prix concurrents
        prices = [p["price"] for p in all_products if p.get("price")]
        brands = list(set(p["brand"] for p in all_products if p.get("brand")))

        # Détecter les géants (marques connues)
        giant_brands = ["Nike", "Apple", "Samsung", "Adidas", "Sony", "Philips",
                        "Bosch", "Amazon", "Google", "Microsoft", "Dyson"]
        has_giant = any(b in brands for b in giant_brands for brands_item in brands if b.lower() in brands_item.lower())

        return {
            "products"       : all_products[:8],
            "price_range"    : {
                "min": round(min(prices), 2) if prices else None,
                "max": round(max(prices), 2) if prices else None,
                "avg": round(sum(prices) / len(prices), 2) if prices else None,
            },
            "brands"         : brands[:8],
            "has_giant_brand": has_giant,
            "total_found"    : len(all_products),
        }

    # ──────────────────────────────────────────────
    # SHOPIFY STORES — Via Google Search (Apify)
    # ──────────────────────────────────────────────
    def _shopify_stores(self, keyword: str) -> dict:
        """
        Cherche des boutiques Shopify concurrentes via Google.
        Requête type : "keyword site:myshopify.com" ou stores connus.
        """
        stores = []
        try:
            # On utilise l'actor Amazon pour un scraping Google Shopping
            # Dans un vrai projet, utiliser : apify/google-search-scraper
            run_input = {
                "queries"     : [f"{keyword} buy online shopify"],
                "maxResults"  : 10,
                "resultsPerPage": 10,
            }
            # Fallback : on retourne des données vides si l'actor Google n'est pas configuré
            # Décommente la ligne suivante quand tu as configuré l'actor Google :
            # run = self.apify.actor("apify/google-search-scraper").call(run_input=run_input)
            # items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())

        except Exception as e:
            logger.warning(f"[Agent4] Shopify stores : {e}")

        return {
            "stores"     : stores,
            "store_count": len(stores),
            "store_urls" : [s.get("url") for s in stores[:5]],
        }

    # ──────────────────────────────────────────────
    # ANALYSE DES INSATISFACTIONS (avis négatifs)
    # ──────────────────────────────────────────────
    def _extract_pain_points(self, products: list) -> list:
        """
        Identifie les patterns d'insatisfaction à partir des titres et notes.
        Dans une version avancée, scraper les vraies reviews 1-2 étoiles.
        """
        pain_keywords = {
            "qualité"    : ["quality", "cheap", "broke", "broke", "flimsy", "poor"],
            "livraison"  : ["shipping", "delivery", "late", "slow", "never arrived"],
            "taille"     : ["size", "small", "large", "fit", "too big", "too small"],
            "service"    : ["support", "customer service", "refund", "return"],
            "description": ["not as", "different", "misleading", "fake"],
        }

        # Analyse des ratings bas
        low_rated = [p for p in products if p.get("rating") and p["rating"] < 4.0]
        pain_points = []

        if low_rated:
            pain_points.append(f"{len(low_rated)} produits concurrents notés < 4 étoiles")

        # Sans accès aux vraies reviews, on donne des pistes génériques
        if products:
            avg_price = sum(p["price"] or 0 for p in products) / len(products)
            if avg_price > 0:
                pain_points.append(f"Prix moyen marché : ${avg_price:.0f} — opportunité de se positionner à valeur")

        return pain_points or ["Données insuffisantes pour l'analyse des avis"]

    # ──────────────────────────────────────────────
    # SUGGESTIONS DE DIFFÉRENCIATION
    # ──────────────────────────────────────────────
    def _differentiation_angles(self, amazon: dict, shopify: dict) -> list:
        angles = []

        if not amazon.get("has_giant_brand"):
            angles.append("Marché sans géant dominant → opportunité de branding fort")

        price_range = amazon.get("price_range", {})
        if price_range.get("avg"):
            avg = price_range["avg"]
            angles.append(f"Positionnement premium possible au-dessus de ${avg:.0f}")
            angles.append("Bundle produit + accessoire pour augmenter panier moyen")

        if shopify.get("store_count", 0) < 5:
            angles.append("Peu de boutiques Shopify spécialisées → niche accessible")

        angles.append("Améliorer le packaging et l'unboxing experience")
        angles.append("Offrir garantie étendue vs concurrents AliExpress")

        return angles[:4]

    # ──────────────────────────────────────────────
    # SCORING (30 pts bruts → x1.0 = 30 max)
    # ──────────────────────────────────────────────
    def _score(self, amazon: dict, shopify: dict) -> dict:
        points  = 0
        details = {}

        # ① Pas de marque géante dominante → 8 pts
        no_giant = not amazon.get("has_giant_brand", False)
        if no_giant:
            points += 8
        details["no_giant_brand"] = {
            "value" : no_giant,
            "points": 8 if no_giant else 0
        }

        # ② Des concurrents existent (preuve de marché) → 7 pts
        market_exists = amazon.get("total_found", 0) >= 3
        if market_exists:
            points += 7
        details["market_exists"] = {
            "value" : amazon.get("total_found"),
            "points": 7 if market_exists else 0
        }

        # ③ Marché non saturé (pas de monopole visible) → 7 pts
        brands = amazon.get("brands", [])
        not_saturated = len(brands) >= 3  # plusieurs acteurs = pas de monopole
        if not_saturated:
            points += 7
        details["not_saturated"] = {
            "value" : len(brands),
            "points": 7 if not_saturated else 0
        }

        # ④ Différenciation possible → 8 pts
        can_differentiate = len(self._differentiation_angles(amazon, shopify)) >= 2
        if can_differentiate:
            points += 8
        details["differentiation"] = {
            "value" : can_differentiate,
            "points": 8 if can_differentiate else 0
        }

        weighted = round(points * 1.0, 1)
        return {"raw": points, "weighted": weighted, "max": 30, "details": details}

    # ──────────────────────────────────────────────
    # RAPPORT FINAL
    # ──────────────────────────────────────────────
    def _build_report(self, product: str, amazon: dict, shopify: dict) -> dict:
        score = self._score(amazon, shopify)
        pain_points = self._extract_pain_points(amazon.get("products", []))
        angles      = self._differentiation_angles(amazon, shopify)

        verdict = (
            "✅ VALIDE"  if score["weighted"] >= 20 else
            "⚠️ MITIGÉ" if score["weighted"] >= 12 else
            "❌ REJETER"
        )

        return {
            "agent"      : "Agent4_Competition",
            "actor_log"  : self.actor_log,
            "product" : product,
            "amazon_competition": {
                "price_range"    : amazon.get("price_range"),
                "brands"         : amazon.get("brands", [])[:5],
                "has_giant"      : amazon.get("has_giant_brand"),
                "competitor_urls": [p["url"] for p in amazon.get("products", [])[:3]],
            },
            "shopify_stores": {
                "count": shopify.get("store_count"),
                "urls" : shopify.get("store_urls", []),
            },
            "pain_points"    : pain_points,
            "differentiation": angles,
            "score"  : score,
            "verdict": verdict,
        }

    def _empty_amazon(self):
        return {"products": [], "price_range": {}, "brands": [], "has_giant_brand": False, "total_found": 0}

    def _empty_shopify(self):
        return {"stores": [], "store_count": 0, "store_urls": []}
