"""
agent2_social.py — Agent Social & Publicité
Sources : Facebook Ads Library, TikTok vidéos virales
"""

import asyncio
import logging
from apify_client import ApifyClient
from config import APIFY_API_KEY, ACTORS, MARKETS, SCORING, TIME_WINDOWS

logger = logging.getLogger(__name__)


class Agent2Social:
    """
    Confirme l'activité publicitaire et virale autour d'un produit.
    Score max : 45 points (30 bruts x coefficient 1.5)
    """

    # Mapping mot-clé → hashtags TikTok populaires connus
    TIKTOK_HASHTAGS = {
        "dog":       ["dogsoftiktok", "dogmom", "petproducts"],
        "cat":       ["catsoftiktok", "catmom", "petproducts"],
        "pet":       ["petstiktok", "petproducts", "animalsoftiktok"],
        "baby":      ["babyproducts", "momtok", "newmom"],
        "posture":   ["posturecorrector", "backpain", "healthtok"],
        "massage":   ["massagegun", "recovery", "fitnesstok"],
        "led":       ["ledlights", "roomdecor", "aestheticroom"],
        "skincare":  ["skincaretok", "glowup", "skincareaddict"],
        "hair":      ["hairtok", "haircare", "hairproducts"],
        "kitchen":   ["kitchengadgets", "cookingtok", "foodtok"],
        "fitness":   ["fitnesstok", "gymtok", "workout"],
        "yoga":      ["yoga", "yogalife", "wellnesstok"],
        "car":       ["cartok", "cardecor", "cargadgets"],
        "desk":      ["desktour", "desksetup", "productivity"],
        "sleep":     ["sleeptok", "bettersleep", "wellness"],
        "face":      ["facemask", "skincareroutine", "beautyproducts"],
        "roller":    ["faceroller", "guasha", "skincaretok"],
        "organizer": ["organization", "cleaningtok", "organized"],
        "shower":    ["showertok", "bathroomdesign", "homegadgets"],
        "default":   ["tiktokmademebuyit", "productreview", "musthave"],
    }

    def _get_tiktok_hashtags(self, keyword: str) -> list[str]:
        """Retourne 2-3 hashtags populaires basés sur les mots du keyword."""
        kw_lower = keyword.lower()
        for term, tags in self.TIKTOK_HASHTAGS.items():
            if term in kw_lower:
                return tags
        # Hashtags génériques si aucun match
        return self.TIKTOK_HASHTAGS["default"]

    def __init__(self):
        self.apify     = ApifyClient(APIFY_API_KEY)
        self.actor_log = {"success": [], "failed": []}

    def _days_ago(self, days: int) -> str:
        """Retourne une date ISO il y a N jours."""
        from datetime import datetime, timedelta
        return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # ──────────────────────────────────────────────
    # POINT D'ENTRÉE PRINCIPAL
    # ──────────────────────────────────────────────
    async def analyze(self, product_name: str, markets: list[str], sources: list = None) -> dict:
        if sources is None:
            sources = ["facebook_ads","amazon","tiktok_videos","tiktok_comments","google_trends","aliexpress"]
        logger.info(f"[Agent2] Analyse sociale pour : {product_name}")

        fb_task     = asyncio.to_thread(self._facebook_ads, product_name, markets)
        tiktok_task = asyncio.to_thread(self._tiktok_viral, product_name)

        fb_result, tiktok_result = await asyncio.gather(
            fb_task, tiktok_task, return_exceptions=True
        )

        if isinstance(fb_result, Exception):
            logger.warning(f"[Agent2] Facebook échoué : {fb_result}")
            fb_result = self._empty_facebook()

        if isinstance(tiktok_result, Exception):
            logger.warning(f"[Agent2] TikTok échoué : {tiktok_result}")
            tiktok_result = self._empty_tiktok()

        return self._build_report(product_name, fb_result, tiktok_result)

    # ──────────────────────────────────────────────
    # FACEBOOK ADS LIBRARY via Apify
    # ──────────────────────────────────────────────
    def _facebook_ads(self, keyword: str, markets: list[str]) -> dict:
        country_codes = [MARKETS[m]["country_code"] for m in markets if m in MARKETS]
        all_ads = []

        for country in country_codes:
            try:
                # L'actor apify/facebook-ads-scraper attend des URLs Meta Ad Library
                # Format correct avec tous les paramètres de filtrage
                import urllib.parse
                kw_encoded = urllib.parse.quote(keyword)
                meta_url = (
                    f"https://www.facebook.com/ads/library/"
                    f"?active_status=active"
                    f"&ad_type=all"
                    f"&country={country}"
                    f"&q={kw_encoded}"
                    f"&search_type=keyword_unordered"
                    f"&media_type=all"
                )
                run_input = {
                    "startUrls"        : [{"url": meta_url}],
                    "resultsLimit"     : 25,
                    "activeStatus"     : "active",
                    "isDetailsPerAd"   : False,
                    "includeAboutPage" : False,
                }
                run  = self.apify.actor(ACTORS["facebook_ads"]).call(run_input=run_input)
                items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())
                if items and ACTORS["facebook_ads"] not in self.actor_log["success"]:
                    self.actor_log["success"].append(ACTORS["facebook_ads"])

                for item in items:
                    advertiser = item.get("pageName", "") or ""
                    body_text  = item.get("snapshot", {}).get("body", {}).get("text", "") or ""

                    # ── Filtre : exclure les pubs non-produit e-commerce ──
                    exclude_keywords = [
                        "credit", "loan", "insurance", "financing", "bank", "mortgage",
                        "investment", "fund", "financial", "capital", "broker", "forex",
                        "crypto", "nft", "trading", "academy", "course", "coaching",
                        "seminary", "webinar", "ebook", "donate", "charity", "non-profit",
                        "real estate", "attorney", "lawyer", "clinic", "hospital",
                    ]
                    combined = (advertiser + " " + body_text).lower()
                    if any(kw in combined for kw in exclude_keywords):
                        continue   # ← ignorer cette pub

                    all_ads.append({
                        "advertiser"     : advertiser,
                        "page_url"       : item.get("pageUrl", ""),
                        "ad_id"          : item.get("adArchiveId", ""),
                        "ad_url"         : f"https://www.facebook.com/ads/library/?id={item.get('adArchiveId', '')}",
                        "started_running": item.get("startDate", ""),
                        "impression_text": item.get("impressionsWithIndex", {}).get("impressionsText", ""),
                        "media_type"     : item.get("snapshot", {}).get("videos") and "video" or "image",
                        "country"        : country,
                        "creative_body"  : body_text[:200],
                    })

            except Exception as e:
                logger.warning(f"[Agent2] Facebook Ads {country} : {e}")
                if ACTORS["facebook_ads"] not in self.actor_log["failed"] and ACTORS["facebook_ads"] not in self.actor_log["success"]:
                    self.actor_log["failed"].append(f'{ACTORS["facebook_ads"]} ({str(e)[:60]})')

        # Déduplique par advertiser
        unique_advertisers = list({ad["advertiser"]: ad for ad in all_ads if ad["advertiser"]}.values())

        return {
            "total_ads"            : len(all_ads),
            "unique_advertisers"   : len(unique_advertisers),
            "sample_ads"           : all_ads[:5],               # 5 exemples de pubs
            "advertiser_list"      : [a["advertiser"] for a in unique_advertisers[:10]],
            "ad_links"             : [a["ad_url"] for a in all_ads[:5]],
            "dominant_media_type"  : self._dominant_media(all_ads),
        }

    def _dominant_media(self, ads: list) -> str:
        if not ads:
            return "inconnu"
        videos = sum(1 for a in ads if a.get("media_type") == "video")
        return "vidéo" if videos > len(ads) / 2 else "image"

    # ──────────────────────────────────────────────
    # TIKTOK — Vidéos virales + découverte produit
    # ──────────────────────────────────────────────
    def _tiktok_viral(self, keyword: str) -> dict:
        import random
        # Utiliser des hashtags populaires connus + recherche textuelle
        popular_tags  = self._get_tiktok_hashtags(keyword)
        search_queries = [keyword, f"best {keyword}"]
        all_videos = []

        # Combiner hashtags populaires et recherche textuelle
        terms_to_try = [
            ("hashtag", popular_tags[0]),
            ("search",  search_queries[0]),
            ("hashtag", popular_tags[1] if len(popular_tags) > 1 else popular_tags[0]),
        ]

        for i, (mode, term) in enumerate(terms_to_try):
            try:
                if mode == "search":
                    run_input = {
                        "searchQueries"       : [term],
                        "resultsPerPage"      : 20,
                        "maxItems"            : 20,
                        "shouldDownloadVideos": False,
                        "searchDatePosted"    : "2",  # 3 derniers mois
                    }
                else:
                    run_input = {
                        "hashtags"             : [term],
                        "resultsPerPage"       : 20,
                        "maxItems"             : 20,
                        "shouldDownloadVideos" : False,
                        "oldestPostDateUnified": f'{TIME_WINDOWS["tiktok_days"]} days',
                    }
                run   = self.apify.actor(ACTORS["tiktok"]).call(run_input=run_input)
                items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())
                if items and ACTORS["tiktok"] not in self.actor_log["success"]:
                    self.actor_log["success"].append(ACTORS["tiktok"])

                for item in items:
                    views = item.get("playCount") or item.get("stats", {}).get("playCount", 0)
                    all_videos.append({
                        "id"          : item.get("id", ""),
                        "url"         : item.get("webVideoUrl") or f"https://www.tiktok.com/@{item.get('authorMeta', {}).get('name', '')}/video/{item.get('id', '')}",
                        "description" : (item.get("text") or item.get("desc") or "")[:150],
                        "views"       : views,
                        "likes"       : item.get("diggCount") or item.get("stats", {}).get("diggCount", 0),
                        "shares"      : item.get("shareCount") or item.get("stats", {}).get("shareCount", 0),
                        "author"      : item.get("authorMeta", {}).get("name", ""),
                        "hashtag"     : term,
                    })

            except Exception as e:
                logger.warning(f"[Agent2] TikTok {mode}:{term} : {e}")
                if ACTORS["tiktok"] not in self.actor_log["failed"] and ACTORS["tiktok"] not in self.actor_log["success"]:
                    self.actor_log["failed"].append(f'{ACTORS["tiktok"]} ({str(e)[:60]})')

        # Trier par vues
        all_videos.sort(key=lambda x: x["views"], reverse=True)
    # ──────────────────────────────────────────────
    # REDDIT — Posts et commentaires produit
    # ──────────────────────────────────────────────
    def _reddit_search(self, keyword: str) -> dict:
        """Cherche des posts Reddit mentionnant ce produit/niche."""
        try:
            run_input = {
                "searches": [
                    {"term": keyword, "sort": "hot"},
                    {"term": f"{keyword} review", "sort": "relevance"},
                ],
                "type": "posts",
                "maxItems": 15,
                "includeComments": False,
            }
            run = self.apify.actor(ACTORS.get("reddit", "harshmaur/reddit-scraper")).call(run_input=run_input)
            items = list(self.apify.dataset(run["defaultDatasetId"]).iterate_items())

            posts = []
            for item in items[:10]:
                score = item.get("score") or item.get("upvotes") or 0
                posts.append({
                    "title"    : (item.get("title") or "")[:120],
                    "url"      : item.get("url") or item.get("link") or "",
                    "score"    : score,
                    "comments" : item.get("numComments") or item.get("comments") or 0,
                    "subreddit": item.get("communityName") or item.get("subreddit") or "",
                })

            # Score de tendance basé sur upvotes total
            total_upvotes = sum(p["score"] for p in posts)
            trend_score = min(10, round(total_upvotes / 500))

            if posts and "reddit" not in self.actor_log["success"]:
                self.actor_log["success"].append(ACTORS.get("reddit", "harshmaur/reddit-scraper"))

            return {"posts": posts, "trend_score": trend_score, "total_posts": len(posts)}

        except Exception as e:
            logger.warning(f"[Agent2] Reddit search : {e}")
            actor = ACTORS.get("reddit", "harshmaur/reddit-scraper")
            if actor not in self.actor_log["failed"] and actor not in self.actor_log["success"]:
                self.actor_log["failed"].append(f'{actor} ({str(e)[:60]})')
            return {"posts": [], "trend_score": 0, "total_posts": 0}

        viral_videos = [v for v in all_videos if v["views"] >= SCORING["tiktok_views_min"]]

        return {
            "total_videos"  : len(all_videos),
            "viral_count"   : len(viral_videos),
            "top_videos"    : all_videos[:5],
            "top_links"     : [v["url"] for v in all_videos[:5]],
            "max_views"     : all_videos[0]["views"] if all_videos else 0,
            "avg_views"     : (
                round(sum(v["views"] for v in all_videos) / len(all_videos))
                if all_videos else 0
            ),
            "creative_formats": self._detect_creative_format(all_videos),
        }

    def _detect_creative_format(self, videos: list) -> list:
        """Détecte les formats créatifs présents dans les descriptions."""
        formats = []
        keywords_map = {
            "démonstration"  : ["demo", "how", "watch", "see", "works"],
            "avant/après"    : ["before", "after", "transformation", "result"],
            "unboxing"       : ["unbox", "package", "arrived", "delivery"],
            "lifestyle"      : ["love", "life", "daily", "routine", "vibe"],
            "problème/solution": ["problem", "solution", "fix", "tired", "hate"],
        }
        all_text = " ".join(v.get("description", "").lower() for v in videos)
        for fmt, words in keywords_map.items():
            if any(w in all_text for w in words):
                formats.append(fmt)
        return formats or ["non déterminé"]

    # ──────────────────────────────────────────────
    # SCORING (30 pts bruts → x1.5 = 45 max)
    # ──────────────────────────────────────────────
    def _score(self, fb: dict, tiktok: dict) -> dict:
        points  = 0
        details = {}

        # ① > 3 annonceurs FB actifs → 10 pts
        fb_ok = fb["unique_advertisers"] >= SCORING["fb_ads_min_advertisers"]
        if fb_ok:
            points += 10
        details["fb_advertisers"] = {
            "value" : fb["unique_advertisers"],
            "points": 10 if fb_ok else 0
        }

        # ② Vidéos TikTok virales (>100K vues) → 8 pts
        tiktok_ok = tiktok["viral_count"] >= 2
        if tiktok_ok:
            points += 8
        details["tiktok_viral"] = {
            "value" : tiktok["viral_count"],
            "points": 8 if tiktok_ok else 0
        }

        # Bonus : si FB = 0 mais TikTok fort → compenser partiellement
        if fb["unique_advertisers"] == 0 and tiktok["viral_count"] >= 5:
            points += 5   # bonus signal TikTok fort sans FB
            details["tiktok_fb_compensate"] = {"value": tiktok["viral_count"], "points": 5}

        # ③ Contenu vidéo dominant (démo/avant-après = facile à faire) → 7 pts
        video_ok = fb.get("dominant_media_type") == "vidéo" or tiktok["total_videos"] > 5
        if video_ok:
            points += 7
        details["video_content"] = {
            "value" : video_ok,
            "points": 7 if video_ok else 0
        }

        # ④ Formats créatifs identifiables → 5 pts
        has_formats = len(tiktok.get("creative_formats", [])) > 1
        if has_formats:
            points += 5
        details["creative_formats"] = {
            "value" : tiktok.get("creative_formats", []),
            "points": 5 if has_formats else 0
        }

        weighted = round(points * 1.5, 1)
        return {"raw": points, "weighted": weighted, "max": 45, "details": details}

    # ──────────────────────────────────────────────
    # RAPPORT FINAL
    # ──────────────────────────────────────────────
    def _build_report(self, product: str, fb: dict, tiktok: dict) -> dict:
        score = self._score(fb, tiktok)
        verdict = (
            "✅ VALIDE"  if score["weighted"] >= 30 else
            "⚠️ MITIGÉ" if score["weighted"] >= 18 else
            "❌ REJETER"
        )

        return {
            "agent"      : "Agent2_Social",
            "actor_log"  : self.actor_log,
            "product" : product,
            "facebook": {
                "unique_advertisers": fb["unique_advertisers"],
                "sample_links"      : fb["ad_links"],
                "dominant_format"   : fb["dominant_media_type"],
                "top_advertisers"   : fb["advertiser_list"][:3],
            },
            "tiktok": {
                "viral_videos_count": tiktok["viral_count"],
                "top_links"         : tiktok["top_links"],
                "max_views"         : tiktok["max_views"],
                "creative_formats"  : tiktok["creative_formats"],
            },
            "score"  : score,
            "verdict": verdict,
        }

    def _empty_facebook(self):
        return {"total_ads": 0, "unique_advertisers": 0, "sample_ads": [], "advertiser_list": [], "ad_links": [], "dominant_media_type": "inconnu"}

    def _empty_tiktok(self):
        return {"total_videos": 0, "viral_count": 0, "top_videos": [], "top_links": [], "max_views": 0, "avg_views": 0, "creative_formats": []}
