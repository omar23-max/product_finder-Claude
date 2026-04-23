"""
agent5_analyzer.py — Agent Analyse Produit par URL
Scrape les URLs fournies et analyse le potentiel du produit via Claude.
"""

import asyncio
import logging
import requests
from apify_client import ApifyClient
from config import APIFY_API_KEY

logger = logging.getLogger(__name__)

# Critères d'analyse (basés sur la checklist originale)
ANALYSIS_CRITERIA = """
Tu es un expert e-commerce et dropshipping. Analyse ce produit selon ces critères :

1. WOW FACTOR (score /10)
   - Réaction immédiate, effet coup de coeur
   - Facilement démontrable en vidéo
   - Aspect visuel fort, utilisation surprenante
   - Potentiel viral

2. RÉSOLUTION D'UN PROBLÈME RÉEL
   - Quel problème concret résout-il ?
   - Combien de personnes sont touchées ?
   - Intensité de la douleur/motivation d'achat

3. POTENTIEL MARCHÉ
   - Taille du marché estimée
   - Tendance : hausse / stable / baisse
   - Saisonnalité éventuelle

4. ANALYSE FOURNISSEUR & MARGE
   - Prix estimé fournisseur (AliExpress/Alibaba)
   - Prix de vente recommandé
   - Marge nette estimée (%)
   - Multiplicateur x3 possible ?

5. LOGISTIQUE
   - Poids et dimensions estimés
   - Risques de retour
   - Complexité SAV

6. CONCURRENCE
   - Niveau de saturation du marché
   - Différenciation possible
   - Présence de géants (Amazon, FNAC...)

7. MARKETING
   - Facilité à créer des créatives
   - Formats recommandés (démo, avant/après, unboxing)
   - Plateformes idéales (TikTok, Meta, YouTube)

8. POINTS FORTS
   - Liste les 3-5 points forts principaux

9. POINTS FAIBLES
   - Liste les 3-5 risques/faiblesses

10. SCORE GLOBAL (/100)
    - WOW Factor : /10
    - Résolution problème : /10
    - Marché : /10
    - Marge : /20
    - Logistique : /10
    - Concurrence : /10
    - Marketing : /15
    - Scalabilité : /15
    TOTAL : /100

11. VERDICT FINAL
    - LANCER (>70) / CREUSER (50-70) / ABANDONNER (<50)
    - Recommandation en 2-3 phrases

Réponds en JSON structuré avec ces clés exactes :
{
  "product_name": "...",
  "wow_factor": {"score": 0-10, "details": "..."},
  "problem_solved": {"description": "...", "market_size": "...", "pain_level": "fort/moyen/faible"},
  "market_potential": {"trend": "hausse/stable/baisse", "size": "...", "seasonality": "..."},
  "margin": {"supplier_price": "$X", "sale_price": "$X", "net_margin": "X%", "multiplier": "xX"},
  "logistics": {"weight": "...", "return_risk": "faible/moyen/élevé", "sav_complexity": "..."},
  "competition": {"saturation": "faible/moyen/élevé", "differentiation": "...", "giants": true/false},
  "marketing": {"creative_ease": "facile/moyen/difficile", "formats": [...], "platforms": [...]},
  "strengths": ["...", "...", "..."],
  "weaknesses": ["...", "...", "..."],
  "scores": {"wow": 0, "problem": 0, "market": 0, "margin": 0, "logistics": 0, "competition": 0, "marketing": 0, "scalability": 0, "total": 0},
  "verdict": "LANCER/CREUSER/ABANDONNER",
  "recommendation": "..."
}
"""


class Agent5Analyzer:
    """
    Analyse le potentiel d'un produit à partir d'URLs.
    Scrape le contenu puis utilise Claude pour l'analyse.
    """

    def __init__(self):
        self.apify = ApifyClient(APIFY_API_KEY)

    async def analyze(self, urls: list[str]) -> dict:
        """Point d'entrée principal — scrape les URLs puis analyse."""
        logger.info(f"[Agent5] Analyse de {len(urls)} URL(s)")

        # 1. Scraper le contenu de chaque URL
        scraped_contents = await asyncio.to_thread(self._scrape_urls, urls)

        # 2. Analyser avec Claude
        analysis = await asyncio.to_thread(self._analyze_with_claude, scraped_contents, urls)

        return analysis

    # ──────────────────────────────────────────────
    # SCRAPING DES URLS
    # ──────────────────────────────────────────────
    def _scrape_urls(self, urls: list[str]) -> list[dict]:
        """Scrape le contenu de chaque URL selon sa plateforme."""
        contents = []

        for url in urls[:5]:  # Max 5 URLs
            content = self._scrape_single_url(url)
            if content:
                contents.append(content)

        return contents

    def _scrape_single_url(self, url: str) -> dict:
        """Détecte la plateforme et scrape en conséquence."""
        url_lower = url.lower()

        try:
            if "tiktok.com" in url_lower:
                return self._scrape_tiktok(url)
            elif "amazon.com" in url_lower or "amazon.fr" in url_lower or "amazon.ca" in url_lower:
                return self._scrape_amazon(url)
            elif "aliexpress.com" in url_lower:
                return self._scrape_aliexpress(url)
            elif "instagram.com" in url_lower:
                return self._scrape_generic(url, "Instagram")
            elif "youtube.com" in url_lower or "youtu.be" in url_lower:
                return self._scrape_generic(url, "YouTube")
            elif "facebook.com" in url_lower:
                return self._scrape_generic(url, "Facebook")
            else:
                return self._scrape_generic(url, "Web")
        except Exception as e:
            logger.warning(f"[Agent5] Scraping échoué pour {url} : {e}")
            return {"url": url, "platform": "unknown", "content": f"URL: {url}", "error": str(e)}

    def _scrape_tiktok(self, url: str) -> dict:
        """Scrape une vidéo TikTok."""
        try:
            run_input = {
                "postURLs": [url],
                "shouldDownloadVideos": False,
                "resultsPerPage": 1,
                "maxItems": 1,
            }
            run = self.apify.actor("clockworks/tiktok-scraper").call(run_input=run_input)
            items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())

            if items:
                item = items[0]
                return {
                    "url": url,
                    "platform": "TikTok",
                    "title": item.get("text") or item.get("desc") or "",
                    "views": item.get("playCount") or item.get("stats", {}).get("playCount", 0),
                    "likes": item.get("diggCount") or 0,
                    "shares": item.get("shareCount") or 0,
                    "comments": item.get("commentCount") or 0,
                    "author": item.get("authorMeta", {}).get("name", ""),
                    "content": f"TikTok vidéo — {item.get('text','')} | Vues: {item.get('playCount',0)} | Likes: {item.get('diggCount',0)}",
                }
        except Exception as e:
            logger.warning(f"[Agent5] TikTok scrape : {e}")
        return {"url": url, "platform": "TikTok", "content": f"URL TikTok: {url}"}

    def _scrape_amazon(self, url: str) -> dict:
        """Scrape une page produit Amazon."""
        try:
            run_input = {
                "categoryOrProductUrls": [{"url": url}],
                "maxItemsPerStartUrl": 1,
                "scrapeProductDetails": True,
            }
            run = self.apify.actor("junglee/Amazon-crawler").call(run_input=run_input)
            items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())

            if items:
                item = items[0]
                price = item.get("price")
                if isinstance(price, dict):
                    price = price.get("value") or price.get("amount")
                return {
                    "url": url,
                    "platform": "Amazon",
                    "title": item.get("title") or item.get("name") or "",
                    "price": price,
                    "rating": item.get("stars") or item.get("rating"),
                    "reviews_count": item.get("reviewsCount") or item.get("ratingsTotal"),
                    "description": (item.get("description") or "")[:500],
                    "best_seller": item.get("isBestSeller", False),
                    "content": f"Amazon — {item.get('title','')} | Prix: ${price} | Rating: {item.get('stars','')} | Reviews: {item.get('reviewsCount','')}",
                }
        except Exception as e:
            logger.warning(f"[Agent5] Amazon scrape : {e}")
        return {"url": url, "platform": "Amazon", "content": f"URL Amazon: {url}"}

    def _scrape_aliexpress(self, url: str) -> dict:
        """Scrape une page produit AliExpress."""
        try:
            run_input = {
                "productUrls": [url],
                "maxProducts": 50,
            }
            run = self.apify.actor("devcake/aliexpress-products-scraper").call(run_input=run_input)
            items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())

            if items:
                item = items[0]
                return {
                    "url": url,
                    "platform": "AliExpress",
                    "title": item.get("title") or "",
                    "price": item.get("priceCurrentMin") or item.get("priceCurrentMax"),
                    "rating": item.get("ratingValue"),
                    "sold": item.get("soldCount"),
                    "content": f"AliExpress — {item.get('title','')} | Prix: ${item.get('priceCurrentMin','')} | Vendus: {item.get('soldCount','')}",
                }
        except Exception as e:
            logger.warning(f"[Agent5] AliExpress scrape : {e}")
        return {"url": url, "platform": "AliExpress", "content": f"URL AliExpress: {url}"}

    def _scrape_generic(self, url: str, platform: str) -> dict:
        """Scrape générique pour autres URLs via rag-web-browser."""
        try:
            run_input = {
                "startUrls": [{"url": url}],
                "maxCrawlPages": 1,
            }
            run = self.apify.actor("apify/rag-web-browser").call(run_input=run_input)
            items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())

            if items:
                item = items[0]
                text = item.get("text") or item.get("markdown") or ""
                return {
                    "url": url,
                    "platform": platform,
                    "title": item.get("metadata", {}).get("title") or "",
                    "content": text[:1000],
                }
        except Exception as e:
            logger.warning(f"[Agent5] Generic scrape {platform} : {e}")
        return {"url": url, "platform": platform, "content": f"URL {platform}: {url}"}

    # ──────────────────────────────────────────────
    # ANALYSE AVEC CLAUDE
    # ──────────────────────────────────────────────
    def _analyze_with_claude(self, contents: list[dict], urls: list[str]) -> dict:
        """Envoie les données scrapées à Claude pour analyse."""
        import json

        # Préparer le contexte produit
        product_context = "\n\n".join([
            f"--- Source {i+1}: {c.get('platform','?')} ---\n{c.get('content','')}"
            for i, c in enumerate(contents)
        ])

        if not product_context.strip():
            product_context = f"URLs fournies: {', '.join(urls)}"

        prompt = f"""Voici les données collectées sur un produit e-commerce :

{product_context}

{ANALYSIS_CRITERIA}

Analyse ce produit et retourne UNIQUEMENT le JSON demandé, sans texte avant ou après."""

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )

            data = response.json()
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            # Nettoyer et parser le JSON
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip().rstrip("```").strip()

            analysis = json.loads(text)
            analysis["urls"] = urls
            analysis["scraped_count"] = len(contents)
            return analysis

        except Exception as e:
            logger.error(f"[Agent5] Claude analyze : {e}")
            return self._fallback_analysis(urls, contents)

    def _fallback_analysis(self, urls: list[str], contents: list[dict]) -> dict:
        """Analyse de secours si Claude échoue."""
        return {
            "product_name": "Analyse non disponible",
            "urls": urls,
            "error": "Analyse Claude indisponible",
            "scraped_count": len(contents),
            "scores": {"total": 0},
            "verdict": "ERREUR",
            "recommendation": "Relancer l'analyse — vérifier les URLs fournies.",
            "strengths": [],
            "weaknesses": [],
        }
