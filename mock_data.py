"""
mock_data.py — Données simulées réalistes pour le mode dry run
Simule les réponses de : AliExpress, Alibaba, CJ, Amazon, Facebook Ads, TikTok, Google Trends
"""

import random

# ──────────────────────────────────────────────
# TEMPLATES DE PRODUITS SIMULÉS PAR NICHE
# ──────────────────────────────────────────────
MOCK_PRODUCTS = {
    "fitness": [
        {
            "keyword"  : "resistance bands set",
            "ali_price": 3.80,
            "ali_rating": 4.7,
            "ali_orders": 12500,
            "amazon_price": 24.99,
            "amazon_reviews": 4200,
            "trends_avg": 72,
            "trends_dir": "hausse",
            "fb_advertisers": 8,
            "tiktok_viral": 5,
            "tiktok_max_views": 2_800_000,
        },
        {
            "keyword"  : "ab roller wheel",
            "ali_price": 4.20,
            "ali_rating": 4.5,
            "ali_orders": 8700,
            "amazon_price": 19.99,
            "amazon_reviews": 6100,
            "trends_avg": 58,
            "trends_dir": "stable",
            "fb_advertisers": 5,
            "tiktok_viral": 3,
            "tiktok_max_views": 950_000,
        },
        {
            "keyword"  : "posture corrector",
            "ali_price": 5.50,
            "ali_rating": 4.6,
            "ali_orders": 15200,
            "amazon_price": 29.99,
            "amazon_reviews": 9800,
            "trends_avg": 81,
            "trends_dir": "hausse",
            "fb_advertisers": 14,
            "tiktok_viral": 8,
            "tiktok_max_views": 5_200_000,
        },
        {
            "keyword"  : "massage gun mini",
            "ali_price": 18.00,
            "ali_rating": 4.8,
            "ali_orders": 22000,
            "amazon_price": 59.99,
            "amazon_reviews": 3400,
            "trends_avg": 65,
            "trends_dir": "stable",
            "fb_advertisers": 11,
            "tiktok_viral": 6,
            "tiktok_max_views": 3_100_000,
        },
        {
            "keyword"  : "jump rope weighted",
            "ali_price": 2.90,
            "ali_rating": 4.4,
            "ali_orders": 5600,
            "amazon_price": 14.99,
            "amazon_reviews": 2100,
            "trends_avg": 44,
            "trends_dir": "baisse",
            "fb_advertisers": 2,
            "tiktok_viral": 1,
            "tiktok_max_views": 180_000,
        },
    ],
    "maison": [
        {
            "keyword"  : "led strip lights smart",
            "ali_price": 6.50,
            "ali_rating": 4.7,
            "ali_orders": 31000,
            "amazon_price": 32.99,
            "amazon_reviews": 12500,
            "trends_avg": 85,
            "trends_dir": "hausse",
            "fb_advertisers": 18,
            "tiktok_viral": 12,
            "tiktok_max_views": 8_500_000,
        },
        {
            "keyword"  : "shower head filter",
            "ali_price": 7.20,
            "ali_rating": 4.6,
            "ali_orders": 9800,
            "amazon_price": 39.99,
            "amazon_reviews": 5600,
            "trends_avg": 68,
            "trends_dir": "hausse",
            "fb_advertisers": 9,
            "tiktok_viral": 7,
            "tiktok_max_views": 4_200_000,
        },
        {
            "keyword"  : "kitchen organizer drawer",
            "ali_price": 8.50,
            "ali_rating": 4.5,
            "ali_orders": 7200,
            "amazon_price": 34.99,
            "amazon_reviews": 3800,
            "trends_avg": 55,
            "trends_dir": "stable",
            "fb_advertisers": 6,
            "tiktok_viral": 4,
            "tiktok_max_views": 1_900_000,
        },
    ],
    "animaux": [
        {
            "keyword"  : "dog anxiety vest",
            "ali_price": 9.80,
            "ali_rating": 4.6,
            "ali_orders": 11200,
            "amazon_price": 44.99,
            "amazon_reviews": 7800,
            "trends_avg": 74,
            "trends_dir": "hausse",
            "fb_advertisers": 12,
            "tiktok_viral": 9,
            "tiktok_max_views": 6_800_000,
        },
        {
            "keyword"  : "cat water fountain",
            "ali_price": 12.50,
            "ali_rating": 4.7,
            "ali_orders": 18500,
            "amazon_price": 49.99,
            "amazon_reviews": 4500,
            "trends_avg": 61,
            "trends_dir": "stable",
            "fb_advertisers": 7,
            "tiktok_viral": 5,
            "tiktok_max_views": 2_300_000,
        },
        {
            "keyword"  : "pet hair remover roller",
            "ali_price": 3.20,
            "ali_rating": 4.5,
            "ali_orders": 25000,
            "amazon_price": 19.99,
            "amazon_reviews": 9200,
            "trends_avg": 78,
            "trends_dir": "hausse",
            "fb_advertisers": 15,
            "tiktok_viral": 10,
            "tiktok_max_views": 7_100_000,
        },
    ],
}

# Niche générique si mot-clé non trouvé
MOCK_GENERIC_PRODUCT = {
    "ali_price"     : 8.50,
    "ali_rating"    : 4.5,
    "ali_orders"    : 5000,
    "amazon_price"  : 35.99,
    "amazon_reviews": 2500,
    "trends_avg"    : 55,
    "trends_dir"    : "stable",
    "fb_advertisers": 5,
    "tiktok_viral"  : 3,
    "tiktok_max_views": 800_000,
}


def get_mock_product(keyword: str, niche: str) -> dict:
    """Retourne des données simulées pour un produit donné."""
    niche_data = MOCK_PRODUCTS.get(niche.lower(), [])
    for p in niche_data:
        if p["keyword"].lower() in keyword.lower() or keyword.lower() in p["keyword"].lower():
            return p
    # Générer des données aléatoires réalistes
    base = MOCK_GENERIC_PRODUCT.copy()
    base["keyword"]    = keyword
    base["ali_price"]  = round(random.uniform(3.0, 20.0), 2)
    base["trends_avg"] = random.randint(30, 85)
    base["trends_dir"] = random.choice(["hausse", "stable", "stable", "baisse"])
    base["fb_advertisers"] = random.randint(0, 16)
    base["tiktok_viral"]   = random.randint(0, 10)
    return base
