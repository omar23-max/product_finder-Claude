"""
config.py — Clés API et paramètres globaux
Remplace les valeurs par tes vraies clés avant de lancer.
"""

import os
from dotenv import load_dotenv

load_dotenv()   # charge automatiquement le fichier .env

# ─────────────────────────────────────────────
# CLÉS API — À renseigner dans un fichier .env
# ─────────────────────────────────────────────
APIFY_API_KEY       = os.getenv("APIFY_API_KEY", "TON_API_KEY_APIFY")
CJ_API_KEY          = os.getenv("CJ_API_KEY", "TON_API_KEY_CJ")

# ─────────────────────────────────────────────
# APIFY — IDs des Actors (meilleurs disponibles)
# ─────────────────────────────────────────────
ACTORS = {
    # Facebook Ads — actor officiel Apify ✅ 18 161 users, 99.5% succès
    "facebook_ads" : "apify/facebook-ads-scraper",

    # TikTok — meilleur actor ✅ 161 836 users, 4.73⭐, 96% succès
    "tiktok"       : "clockworks/tiktok-scraper",

    # Amazon — ✅ 4.89⭐, 14 289 users, 97.7% succès
    "amazon"       : "junglee/Amazon-crawler",

    # AliExpress — ✅ 95.6% succès, prix + ratings + orders
    "aliexpress"   : "devcake/aliexpress-products-scraper",

    # Alibaba — bulk scraper AliExpress comme alternative
    "alibaba"      : "hello.datawizards/aliexpress-bulk-scraper-pro",

    # Reddit — 4.93⭐, 98.7% succès
    "reddit"       : "harshmaur/reddit-scraper",

    # Pinterest — 5⭐, 99.9% succès
    "pinterest"    : "silentflow/pinterest-scraper-ppr",

    # YouTube — scraper vidéos/reviews produit
    "youtube"      : "streamers/youtube-scraper",
}

# Actors de secours si les principaux échouent
ACTORS_FALLBACK = {
    "facebook_ads" : "easyapi/facebook-ads-library-scraper",
    "tiktok"       : "clockworks/free-tiktok-scraper",
    "amazon"       : "junglee/amazon-scraper",
    "aliexpress"   : "hello.datawizards/aliexpress-bulk-scraper-pro",
}

# Actors de secours si les principaux échouent
ACTORS_FALLBACK = {
    "facebook_ads" : "easyapi/facebook-ads-library-scraper",
    "tiktok"       : "clockworks/free-tiktok-scraper",
    "amazon"       : "junglee/amazon-scraper",
    "aliexpress"   : "devcake/aliexpress-products-scraper",
    "alibaba"      : "epctex/alibaba-scraper",
}

# ─────────────────────────────────────────────
# MARCHÉS CIBLES
# ─────────────────────────────────────────────
MARKETS = {
    "USA"    : {"country_code": "US", "currency": "USD", "amazon_domain": "amazon.com"},
    "Canada" : {"country_code": "CA", "currency": "CAD", "amazon_domain": "amazon.ca"},
    "France" : {"country_code": "FR", "currency": "EUR", "amazon_domain": "amazon.fr"},
    "UK"     : {"country_code": "GB", "currency": "GBP", "amazon_domain": "amazon.co.uk"},
    "Germany": {"country_code": "DE", "currency": "EUR", "amazon_domain": "amazon.de"},
}

# ─────────────────────────────────────────────
# PARAMÈTRES FINANCIERS (règles de rentabilité)
# ─────────────────────────────────────────────
FINANCE = {
    "min_sale_price"       : 25,    # $ minimum prix de vente
    "max_sale_price"       : 150,   # $ maximum prix de vente
    "min_margin_multiplier": 3.0,   # règle x3 : prix vente >= 3x coût fournisseur
    "min_net_margin_pct"   : 25,    # % marge nette minimale
    "max_shipping_pct"     : 15,    # % max que représente la livraison / prix vente
    "max_weight_kg"        : 1.0,   # poids max en kg
    "max_delivery_days"    : 15,    # délai de livraison max (jours)
}

# ─────────────────────────────────────────────
# SEUILS DE SCORING (pré-filtre + score pondéré)
# ─────────────────────────────────────────────
SCORING = {
    "google_trends_min_index" : 50,
    "amazon_reviews_min"      : 50,
    "tiktok_views_min"        : 100_000,
    "fb_ads_min_advertisers"  : 3,
    "monthly_search_vol_min"  : 5_000,
    "supplier_min_rating"     : 4.5,
    "supplier_min_orders"     : 500,
    # Seuils de décision finale
    "winner_threshold"        : 145,   # /190
    "potential_threshold"     : 100,   # /190
}

# ─────────────────────────────────────────────
# FENÊTRES TEMPORELLES — Ne pas remonter trop loin
# ─────────────────────────────────────────────
TIME_WINDOWS = {
    # Google Trends : 3 mois glissants (pas 12 mois)
    "google_trends"     : "today 3-m",

    # Facebook Ads : uniquement les pubs actives des 90 derniers jours
    "facebook_ads_days" : 90,

    # TikTok : vidéos postées dans les 60 derniers jours
    "tiktok_days"       : 60,

    # Amazon : produits avec des avis récents (90 jours)
    "amazon_days"       : 90,

    # AliExpress : trier par "orders" récents, ignorer les produits > 2 ans
    "aliexpress_days"   : 180,

    # CJ Dropshipping : stock actif uniquement
    "cj_active_only"    : True,
}

# ─────────────────────────────────────────────
# NOMBRE DE PRODUITS À RETOURNER PAR SESSION
# ─────────────────────────────────────────────
TARGET_PRODUCTS = 20
