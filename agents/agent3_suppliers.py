"""
agent3_suppliers.py — Agent Fournisseurs & Marge
Sources : AliExpress, Alibaba, CJ Dropshipping
AliExpress et Alibaba servent aussi à la DÉCOUVERTE de produits trending.
"""

import asyncio
import logging
import requests
from typing import Optional
from apify_client import ApifyClient
from config import APIFY_API_KEY, CJ_API_KEY, ACTORS, FINANCE, SCORING

logger = logging.getLogger(__name__)

CJ_BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"


class Agent3Suppliers:
    """
    Trouve les meilleurs fournisseurs, valide la marge et détecte les produits trending
    sur AliExpress, Alibaba et CJ Dropshipping.
    Score max : 70 points (35 bruts x coefficient 2.0)
    """

    def __init__(self):
        self.apify     = ApifyClient(APIFY_API_KEY)
        self._cj_token = None
        self.actor_log = {"success": [], "failed": []}

    # ──────────────────────────────────────────────
    # POINT D'ENTRÉE PRINCIPAL
    # ──────────────────────────────────────────────
    async def analyze(self, product_name: str) -> dict:
        logger.info(f"[Agent3] Analyse fournisseurs pour : {product_name}")

        ali_task  = asyncio.to_thread(self._aliexpress_search, product_name)
        alib_task = asyncio.to_thread(self._alibaba_search, product_name)
        cj_task   = asyncio.to_thread(self._cj_search, product_name)

        ali_result, alib_result, cj_result = await asyncio.gather(
            ali_task, alib_task, cj_task, return_exceptions=True
        )

        if isinstance(ali_result,  Exception):
            logger.warning(f"[Agent3] AliExpress échoué : {ali_result}")
            ali_result = self._empty_supplier("AliExpress")

        if isinstance(alib_result, Exception):
            logger.warning(f"[Agent3] Alibaba échoué : {alib_result}")
            alib_result = self._empty_supplier("Alibaba")

        if isinstance(cj_result,   Exception):
            logger.warning(f"[Agent3] CJ Dropshipping échoué : {cj_result}")
            cj_result = self._empty_supplier("CJ Dropshipping")

        return self._build_report(product_name, ali_result, alib_result, cj_result)

    # ──────────────────────────────────────────────
    # ALIEXPRESS — Découverte + Prix fournisseur
    # ──────────────────────────────────────────────
    def _aliexpress_search(self, keyword: str) -> dict:
        # devcake/aliexpress-products-scraper : maxProducts >= 50 requis
        run_input = {
            "searchQueries" : [keyword],
            "maxProducts"   : 50,           # minimum requis par l'actor
            "sortBy"        : "default",    # default = meilleure pertinence
            "proxyConfiguration": {
                "useApifyProxy"     : True,
                "apifyProxyGroups"  : ["RESIDENTIAL"],
                "apifyProxyCountry" : "US",
            },
        }
        run   = self.apify.actor(ACTORS["aliexpress"]).call(run_input=run_input)
        items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())
        if items and ACTORS["aliexpress"] not in self.actor_log["success"]:
            self.actor_log["success"].append(ACTORS["aliexpress"])

        products = []
        for item in items:
            # Champs réels vérifiés via l'API devcake/aliexpress-products-scraper
            price = item.get("priceCurrentMin") or item.get("priceCurrentMax")
            if not price:
                # Fallbacks supplémentaires
                for field in ["salePrice", "price", "originalPrice"]:
                    raw = item.get(field)
                    if raw is None: continue
                    if isinstance(raw, (int, float)) and raw > 0:
                        price = float(raw); break
                    if isinstance(raw, dict):
                        for sub in ["value", "min", "current"]:
                            v = raw.get(sub)
                            if v and float(v) > 0:
                                price = float(v); break
                    if price: break

            products.append({
                "title"         : (item.get("title") or "")[:80],
                "price_usd"     : float(price) if price else None,
                "rating"        : item.get("ratingValue") or item.get("avgRating") or item.get("rating"),
                "orders"        : item.get("soldCount") or item.get("orders") or item.get("totalOrders"),
                "shipping_days" : self._extract_shipping_days(item),
                "url"           : item.get("productUrl") or item.get("url", ""),
                "image"         : item.get("imageUrl") or item.get("image", ""),
                "platform"      : "AliExpress",
            })

        # Filtrer : rating >= 4.0 ET prix renseigné
        valid = [p for p in products if p["price_usd"] and (p["rating"] or 0) >= 4.0]
        valid.sort(key=lambda x: (x["orders"] or 0), reverse=True)

        return {
            "platform"    : "AliExpress",
            "products"    : valid[:5],
            "best"        : valid[0] if valid else None,
            "price_range" : self._price_range(valid),
            "trending"    : [p for p in valid if (p["orders"] or 0) >= 500],
        }

    # ──────────────────────────────────────────────
    # ALIBABA — Prix gros + tendances fabricants
    # ──────────────────────────────────────────────
    def _alibaba_search(self, keyword: str) -> dict:
        run_input = {
            "keyword"  : keyword,
            "maxItems" : 10,
        }
        run   = self.apify.actor(ACTORS["alibaba"]).call(run_input=run_input)
        items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())
        if items and ACTORS["alibaba"] not in self.actor_log["success"]:
            self.actor_log["success"].append(ACTORS["alibaba"])

        products = []
        for item in items:
            price_raw = item.get("price") or {}
            min_price = price_raw.get("min") if isinstance(price_raw, dict) else price_raw
            products.append({
                "title"     : item.get("title", "")[:80],
                "price_usd" : float(min_price) if min_price else None,
                "moq"       : item.get("minOrderQuantity") or item.get("moq"),
                "supplier"  : item.get("companyName", ""),
                "rating"    : item.get("supplierRating"),
                "url"       : item.get("url") or item.get("productUrl", ""),
                "platform"  : "Alibaba",
            })

        valid = [p for p in products if p["price_usd"]]
        return {
            "platform"   : "Alibaba",
            "products"   : valid[:5],
            "best"       : valid[0] if valid else None,
            "price_range": self._price_range(valid),
        }

    # ──────────────────────────────────────────────
    # CJ DROPSHIPPING — API directe
    # ──────────────────────────────────────────────
    def _cj_get_token(self) -> Optional[str]:
        if self._cj_token:
            return self._cj_token
        try:
            r = requests.post(
                f"{CJ_BASE_URL}/authentication/getAccessToken",
                json={"apiKey": CJ_API_KEY},
                timeout=10
            )
            data = r.json()
            if data.get("result"):
                self._cj_token = data["data"]["accessToken"]
                return self._cj_token
        except Exception as e:
            logger.warning(f"[Agent3] CJ Token : {e}")
        return None

    def _cj_search(self, keyword: str) -> dict:
        token = self._cj_get_token()
        if not token:
            return self._empty_supplier("CJ Dropshipping")

        try:
            r = requests.get(
                f"{CJ_BASE_URL}/product/list",
                headers={"CJ-Access-Token": token},
                params={
                    "productNameEn": keyword,
                    "pageNum"      : 1,
                    "pageSize"     : 10,
                },
                timeout=15
            )
            data = r.json()
            items = data.get("data", {}).get("list", [])

            products = []
            for item in items:
                products.append({
                    "title"         : item.get("productNameEn", "")[:80],
                    "price_usd"     : float(item.get("sellPrice") or 0) or None,
                    "shipping_days" : item.get("deliveryTime"),
                    "stock"         : item.get("inventory"),
                    "url"           : f"https://app.cjdropshipping.com/product-detail.html?id={item.get('pid', '')}",
                    "image"         : item.get("productImage", ""),
                    "platform"      : "CJ Dropshipping",
                    "has_us_warehouse": "US" in str(item.get("warehouseCountry", "")),
                })

            valid = [p for p in products if p["price_usd"]]
            return {
                "platform"       : "CJ Dropshipping",
                "products"       : valid[:5],
                "best"           : valid[0] if valid else None,
                "price_range"    : self._price_range(valid),
                "us_warehouse"   : any(p["has_us_warehouse"] for p in valid),
            }

        except Exception as e:
            logger.warning(f"[Agent3] CJ Search : {e}")
            return self._empty_supplier("CJ Dropshipping")

    # ──────────────────────────────────────────────
    # CALCUL DE MARGE
    # ──────────────────────────────────────────────
    def _calculate_margin(self, supplier_price: float, market: str = "USA") -> dict:
        """
        Calcule la marge nette estimée selon les règles de rentabilité.
        Hypothèses moyennes dropshipping.
        """
        if not supplier_price:
            return {}

        # Prix de vente cible = 3x le coût fournisseur (règle minimum)
        sale_price   = round(supplier_price * FINANCE["min_margin_multiplier"], 2)

        # Si en dehors du sweet spot, ajuster
        if sale_price < FINANCE["min_sale_price"]:
            sale_price = FINANCE["min_sale_price"]
        if sale_price > FINANCE["max_sale_price"]:
            sale_price = FINANCE["max_sale_price"]

        shipping      = round(sale_price * 0.10, 2)          # ~10% du prix de vente
        ads_cost      = round(sale_price * 0.20, 2)          # ~20% ROAS 5x hypothèse
        platform_fee  = round(sale_price * 0.03, 2)          # ~3% Shopify/frais
        total_costs   = supplier_price + shipping + ads_cost + platform_fee
        net_margin    = round(sale_price - total_costs, 2)
        net_margin_pct= round((net_margin / sale_price) * 100, 1)

        return {
            "supplier_cost"   : supplier_price,
            "sale_price"      : sale_price,
            "shipping"        : shipping,
            "ads_cost"        : ads_cost,
            "platform_fee"    : platform_fee,
            "net_margin_usd"  : net_margin,
            "net_margin_pct"  : net_margin_pct,
            "is_profitable"   : net_margin_pct >= FINANCE["min_net_margin_pct"],
            "multiplier"      : round(sale_price / supplier_price, 1),
        }

    # ──────────────────────────────────────────────
    # SCORING (35 pts bruts → x2.0 = 70 max)
    # ──────────────────────────────────────────────
    def _score(self, ali: dict, alib: dict, cj: dict, margin: dict) -> dict:
        points  = 0
        details = {}

        # ① Coût < 1/3 du prix de vente → 10 pts
        margin_ok = margin.get("multiplier", 0) >= FINANCE["min_margin_multiplier"]
        if margin_ok:
            points += 10
        details["margin_multiplier"] = {
            "value" : margin.get("multiplier"),
            "points": 10 if margin_ok else 0
        }

        # ② Marge nette > 25% → 10 pts
        net_ok = margin.get("net_margin_pct", 0) >= FINANCE["min_net_margin_pct"]
        if net_ok:
            points += 10
        details["net_margin"] = {
            "value" : margin.get("net_margin_pct"),
            "points": 10 if net_ok else 0
        }

        # ③ Délai livraison < 15 jours → 7 pts
        fast = (
            cj.get("us_warehouse") or
            any((p.get("shipping_days") or 99) <= FINANCE["max_delivery_days"]
                for p in ali.get("products", []))
        )
        if fast:
            points += 7
        details["delivery_speed"] = {"value": fast, "points": 7 if fast else 0}

        # ④ Fournisseur bien noté sur AliExpress → 5 pts
        best_ali = ali.get("best")
        rated_ok = best_ali and (best_ali.get("rating") or 0) >= SCORING["supplier_min_rating"]
        if rated_ok:
            points += 5
        details["supplier_rating"] = {
            "value" : best_ali.get("rating") if best_ali else None,
            "points": 5 if rated_ok else 0
        }

        # ⑤ Au moins 2 fournisseurs alternatifs → 3 pts
        sources = sum(1 for s in [ali["best"], alib["best"], cj["best"]] if s)
        has_alternatives = sources >= 2
        if has_alternatives:
            points += 3
        details["alternatives"] = {"value": sources, "points": 3 if has_alternatives else 0}

        weighted = round(points * 2.0, 1)
        return {"raw": points, "weighted": weighted, "max": 70, "details": details}

    # ──────────────────────────────────────────────
    # RAPPORT FINAL
    # ──────────────────────────────────────────────
    def _build_report(self, product: str, ali: dict, alib: dict, cj: dict) -> dict:
        # Trouver le meilleur prix fournisseur toutes sources confondues
        best_price = None
        for source in [ali, alib, cj]:
            p = source.get("best")
            if p and p.get("price_usd"):
                if best_price is None or p["price_usd"] < best_price:
                    best_price = p["price_usd"]

        margin = self._calculate_margin(best_price) if best_price else {}
        score  = self._score(ali, alib, cj, margin)

        verdict = (
            "✅ VALIDE"  if score["weighted"] >= 45 else
            "⚠️ MITIGÉ" if score["weighted"] >= 28 else
            "❌ REJETER"
        )

        return {
            "agent"      : "Agent3_Suppliers",
            "actor_log"  : self.actor_log,
            "product"  : product,
            "suppliers": {
                "aliexpress"    : self._format_supplier(ali.get("best")),
                "alibaba"       : self._format_supplier(alib.get("best")),
                "cj_dropshipping": self._format_supplier(cj.get("best")),
            },
            "trending_products": {
                "aliexpress": [p["title"] for p in ali.get("trending", [])[:3]],
            },
            "margin" : margin,
            "score"  : score,
            "verdict": verdict,
        }

    def _format_supplier(self, product: Optional[dict]) -> Optional[dict]:
        if not product:
            return None
        return {
            "name"    : product.get("platform"),
            "price"   : product.get("price_usd"),
            "rating"  : product.get("rating"),
            "orders"  : product.get("orders"),
            "url"     : product.get("url"),
            "shipping": product.get("shipping_days"),
        }

    def _price_range(self, products: list) -> dict:
        prices = [p["price_usd"] for p in products if p.get("price_usd")]
        if not prices:
            return {"min": None, "max": None, "avg": None}
        return {
            "min": round(min(prices), 2),
            "max": round(max(prices), 2),
            "avg": round(sum(prices) / len(prices), 2),
        }

    def _extract_shipping_days(self, item: dict) -> Optional[int]:
        for key in ["shippingDays", "deliveryDays", "processingTime"]:
            val = item.get(key)
            if val:
                try:
                    return int(str(val).split("-")[0])
                except:
                    pass
        return None

    def _empty_supplier(self, name: str) -> dict:
        return {"platform": name, "products": [], "best": None, "price_range": {}, "trending": []}
