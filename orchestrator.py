"""
orchestrator.py — Agent 0 : Orchestrateur Principal
Coordonne les 4 subagents en parallèle et génère les fiches produits finales.
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional
from typing import Optional

from config import TARGET_PRODUCTS, SCORING, MARKETS
from agents.agent1_trends    import Agent1Trends
from agents.agent2_social    import Agent2Social
from agents.agent3_suppliers import Agent3Suppliers
from agents.agent4_competition import Agent4Competition
from utils.scorer   import ProductScorer
from utils.exporter import ProductExporter

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("product_finder.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Agent 0 — Chef d'orchestre du système multi-agents.
    Lance les subagents en parallèle, agrège les résultats, calcule les scores finaux.
    """

    def __init__(self):
        self.agent1   = Agent1Trends()
        self.agent2   = Agent2Social()
        self.agent3   = Agent3Suppliers()
        self.agent4   = Agent4Competition()
        self.scorer   = ProductScorer()
        self.exporter = ProductExporter()

    # ──────────────────────────────────────────────
    # DÉMARRAGE — Questions initiales
    # ──────────────────────────────────────────────
    def ask_startup_questions(self) -> dict:
        """Pose les 3 questions de démarrage à l'utilisateur."""
        print("\n" + "="*60)
        print("🤖  PRODUCT FINDER — Recherche de produits gagnants")
        print("="*60)

        print("\n📌 Question 1/3 — Quelle niche ou quel produit veux-tu explorer ?")
        print("   (ex : 'maison', 'animaux', 'fitness', 'cuisine', 'je ne sais pas')")
        niche = input("   → ").strip()
        if not niche or niche.lower() in ["je ne sais pas", "surprise", "surprends moi"]:
            niche = self._suggest_trending_niche()
            print(f"   💡 Niche suggérée automatiquement : {niche}")

        print("\n📌 Question 2/3 — Marché(s) prioritaire(s) ?")
        print("   1. USA seulement")
        print("   2. Canada seulement")
        print("   3. Europe (FR, DE, UK)")
        print("   4. Tous les marchés")
        market_choice = input("   → Choix (1/2/3/4) : ").strip()
        markets = {
            "1": ["USA"],
            "2": ["Canada"],
            "3": ["France", "UK", "Germany"],
            "4": ["USA", "Canada", "France", "UK"],
        }.get(market_choice, ["USA", "Canada", "France"])

        print("\n📌 Question 3/3 — Budget pub estimé pour tester ?")
        print("   1. < 500$")
        print("   2. 500$ – 2 000$")
        print("   3. > 2 000$")
        budget_choice = input("   → Choix (1/2/3) : ").strip()
        budget = {"1": "< 500$", "2": "500$ – 2 000$", "3": "> 2 000$"}.get(budget_choice, "500$ – 2 000$")

        return {"niche": niche, "markets": markets, "budget": budget}

    def _suggest_trending_niche(self) -> str:
        """Niche de repli si l'utilisateur ne sait pas."""
        import random
        niches = ["gadgets maison", "accessoires animaux", "fitness à domicile",
                  "organisation bureau", "beauté & skincare", "cuisine innovante"]
        return random.choice(niches)

    # ──────────────────────────────────────────────
    # PRÉ-FILTRE RAPIDE
    # ──────────────────────────────────────────────
    def _pre_filter(self, product: str) -> tuple[bool, list[str]]:
        """
        Filtre express avant de lancer les 4 agents.
        Si 2 NON → abandonner le produit immédiatement.
        Retourne (passer, liste_des_raisons).
        """
        reasons = []
        fails   = 0

        # Ces vérifications sont basées sur le nom du produit
        # Dans une version avancée, enrichir avec des données réelles
        blacklist_keywords = [
            "nike", "apple", "samsung", "disney", "lego", "gucci", "louis vuitton",
            "iphone", "playstation", "xbox",
        ]
        if any(kw in product.lower() for kw in blacklist_keywords):
            reasons.append(f"❌ Marque déposée détectée dans : '{product}'")
            fails += 1

        # Vérification longueur/poids implicite (heuristique)
        heavy_keywords = ["treadmill", "tapis roulant", "sofa", "canapé", "matelas", "mattress", "furniture"]
        if any(kw in product.lower() for kw in heavy_keywords):
            reasons.append(f"❌ Produit potentiellement lourd/volumineux : '{product}'")
            fails += 1

        # Saisonnier sans alternative
        seasonal_only = ["christmas tree", "halloween costume", "sapin de noël"]
        if any(kw in product.lower() for kw in seasonal_only):
            reasons.append(f"⚠️ Produit 100% saisonnier détecté : '{product}'")
            fails += 1

        passed = fails < 2
        return passed, reasons

    # ──────────────────────────────────────────────
    # ANALYSE D'UN PRODUIT (tous agents en parallèle)
    # ──────────────────────────────────────────────
    async def _analyze_product(self, product: str, markets: list[str]) -> Optional[dict]:
        """Lance les 4 agents en parallèle pour un produit donné."""

        # Pré-filtre
        passed, reasons = self._pre_filter(product)
        if not passed:
            logger.info(f"[Orchestrateur] {product} → REJETÉ au pré-filtre : {reasons}")
            return None

        logger.info(f"[Orchestrateur] Analyse de : {product} sur {markets}")

        # Lancement parallèle des 4 agents
        results = await asyncio.gather(
            self.agent1.analyze(product, markets),
            self.agent2.analyze(product, markets),
            self.agent3.analyze(product),
            self.agent4.analyze(product, markets),
            return_exceptions=True
        )

        a1, a2, a3, a4 = results

        # Remplacer les exceptions par des résultats vides
        if isinstance(a1, Exception):
            logger.error(f"[Agent1] Erreur : {a1}")
            a1 = {"score": {"weighted": 0, "max": 45}, "verdict": "❌ ERREUR", "product": product}
        if isinstance(a2, Exception):
            logger.error(f"[Agent2] Erreur : {a2}")
            a2 = {"score": {"weighted": 0, "max": 45}, "verdict": "❌ ERREUR", "product": product}
        if isinstance(a3, Exception):
            logger.error(f"[Agent3] Erreur : {a3}")
            a3 = {"score": {"weighted": 0, "max": 70}, "verdict": "❌ ERREUR", "product": product}
        if isinstance(a4, Exception):
            logger.error(f"[Agent4] Erreur : {a4}")
            a4 = {"score": {"weighted": 0, "max": 30}, "verdict": "❌ ERREUR", "product": product}

        # Score final
        final_score = self.scorer.compute_final_score(a1, a2, a3, a4)

        # Agréger les logs actors de tous les agents
        all_success, all_failed = [], []
        for agent in [a1, a2, a3, a4]:
            log = agent.get("actor_log", {})
            for s in log.get("success", []):
                if s not in all_success:
                    all_success.append(s)
            for f in log.get("failed", []):
                # Ne mettre en failed que si pas déjà en success
                base = f.split(" (")[0]
                if base not in all_success and f not in all_failed:
                    all_failed.append(f)

        return {
            "product"    : product,
            "markets"    : markets,
            "timestamp"  : datetime.now().isoformat(),
            "agent1"     : a1,
            "agent2"     : a2,
            "agent3"     : a3,
            "agent4"     : a4,
            "final_score": final_score,
            "actor_log"  : {"success": all_success, "failed": all_failed},
        }

    # ──────────────────────────────────────────────
    # SESSION COMPLÈTE — Recherche de 20 produits
    # ──────────────────────────────────────────────
    async def run_session(self, config: dict) -> list[dict]:
        """
        Lance une session complète de recherche.
        Génère une liste de produits candidats, les analyse, retourne les 20 meilleurs.
        """
        niche   = config["niche"]
        markets = config["markets"]
        budget  = config["budget"]

        print(f"\n🚀 Démarrage de la session...")
        print(f"   Niche    : {niche}")
        print(f"   Marchés  : {', '.join(markets)}")
        print(f"   Budget   : {budget}")
        print(f"   Objectif : {TARGET_PRODUCTS} produits gagnants\n")

        # Générer la liste des produits candidats à analyser
        candidates = self._generate_candidates(niche)
        print(f"📋 {len(candidates)} produits candidats identifiés pour la niche '{niche}'")

        results = []
        analyzed = 0

        seen_products = set()   # déduplication sur la session

        for i, product in enumerate(candidates):
            # Normaliser pour déduplication (ignorer casse et petites variations)
            product_key = product.lower().strip()
            if product_key in seen_products:
                print(f"\n[{i+1}/{len(candidates)}] ⤼ Doublon ignoré : {product}")
                continue
            seen_products.add(product_key)

            print(f"\n[{i+1}/{len(candidates)}] Analyse de : {product}")
            result = await self._analyze_product(product, markets)

            if result:
                results.append(result)
                status = result["final_score"]["status"]
                score  = result["final_score"]["total"]
                print(f"   ✓ Score : {score}/190 — {status}")
                analyzed += 1
            else:
                print(f"   ✗ Rejeté au pré-filtre")

            # Arrêter si on a suffisamment de produits GAGNANTS
            winners = [r for r in results if r["final_score"]["status"] == "✅ GAGNANT"]
            if len(winners) >= TARGET_PRODUCTS:
                print(f"\n🏆 {TARGET_PRODUCTS} produits gagnants trouvés — arrêt de la recherche")
                break

        # Trier par score décroissant
        results.sort(key=lambda x: x["final_score"]["total"], reverse=True)
        top_products = results[:TARGET_PRODUCTS]

        print(f"\n{'='*60}")
        print(f"✅ SESSION TERMINÉE — {len(top_products)} produits sélectionnés")
        print(f"{'='*60}")

        return top_products

    # ──────────────────────────────────────────────
    # GÉNÉRATION DES CANDIDATS
    # ──────────────────────────────────────────────
    # Mapping niche → produits réels et spécifiques
    NICHE_PRODUCTS = {
        "Health & Wellness": [
            "posture corrector back brace", "red light therapy device",
            "massage gun percussive", "acupressure mat set",
            "cold therapy ice roller face", "blue light blocking glasses",
            "sleep eye mask 3d contoured", "magnesium supplement spray",
            "nasal breathing strips", "fascia blaster tool",
        ],
        "Pets": [
            "dog anxiety vest calming", "cat water fountain automatic",
            "pet hair remover roller", "dog paw cleaner portable",
            "automatic pet feeder camera", "cat window perch hammock",
            "dog cooling mat summer", "retractable dog leash",
            "pet grooming glove", "dog treat dispenser ball",
        ],
        "Home & Decor": [
            "led strip lights smart wifi", "shower head filter hard water",
            "kitchen drawer organizer bamboo", "motion sensor night light",
            "magnetic knife holder wall", "foam tape weather stripping",
            "drawer dividers adjustable", "toilet night light motion",
            "shower caddy tension pole", "pot rack hanging ceiling",
        ],
        "Beauty & Cosmetics": [
            "gua sha facial tool rose quartz", "led face mask red light",
            "scalp massager shampoo brush", "eyebrow stamp kit stencil",
            "heated eyelash curler", "facial steamer nano ionic",
            "dermaplaning tool face", "lip plumper device natural",
            "ice roller face puffiness", "nail art stamping kit",
        ],
        "Tech & Gadgets": [
            "wireless charger stand 3in1", "cable management box wood",
            "laptop stand adjustable aluminum", "monitor riser bamboo desk",
            "ring light clip phone holder", "usb hub multiport adapter",
            "smart plug wifi schedule", "webcam cover privacy slider",
            "screen privacy filter laptop", "cable organizer velcro straps",
        ],
        "Sport & Outdoor": [
            "resistance bands set loop", "ab roller wheel core",
            "pull up bar doorway no screw", "jump rope speed cable",
            "foam roller high density", "balance board wobble",
            "grip strength trainer", "ankle weights set adjustable",
            "yoga block set cork", "sliders core workout",
        ],
        "Baby & Parenting": [
            "baby monitor split screen", "diaper bag backpack waterproof",
            "white noise machine portable", "bath seat ring non slip",
            "teething toy silicone set", "stroller organizer bag",
            "nursing pillow adjustable", "baby knee pads crawling",
            "pacifier clip holder", "baby food maker steam blend",
        ],
        "Car Accessories": [
            "car phone mount magnetic", "car organizer back seat",
            "car seat gap filler organizer", "dash cam front rear 4k",
            "car vacuum cleaner portable", "steering wheel desk tray",
            "trunk organizer collapsible", "blind spot mirror wide angle",
            "car air freshener vent clip", "car phone charger fast",
        ],
        "Gifts": [
            "custom night sky map print", "personalized cutting board",
            "engraved whiskey glass set", "spa gift basket relaxation",
            "funny coffee mug novelty", "puzzle custom photo pieces",
            "scented candle set luxury", "digital picture frame wifi",
            "star map constellation custom", "photo book custom memory",
        ],
        "Fashion & Accessories": [
            "minimalist leather watch", "stackable rings set gold",
            "crossbody bag small leather", "silk scrunchie hair set",
            "custom name necklace", "baseball cap embroidered",
            "tote bag canvas personalized", "sunglasses polarized uv400",
            "wallet rfid blocking slim", "stainless steel earrings set",
        ],
        "Hobbies & Passions": [
            "diamond painting kit large", "acrylic paint set beginner",
            "hand embroidery kit beginner", "macrame cord kit wall hanging",
            "resin art kit mold silicone", "watercolor brush pen set",
            "knitting kit starter beginner", "calligraphy pen set beginner",
            "sketchbook set spiral", "origami paper set colored",
        ],
        "DIY": [
            "laser level self leveling", "electric screwdriver rechargeable",
            "stud finder wall scanner", "heat gun variable temperature",
            "cordless drill lightweight", "utility knife box cutter",
            "knee pads construction", "safety glasses anti fog",
            "work gloves cut resistant", "measuring tape magnetic",
        ],
        "Ecology & Sustainable": [
            "beeswax wraps reusable set", "bamboo toothbrush set",
            "reusable produce bags mesh", "bamboo cutting board set",
            "solar garden lights outdoor", "stainless steel straws set",
            "silicone food storage bags", "loofah natural organic",
            "compostable trash bags", "fabric shower curtain liner",
        ],
        "Luxury & Premium Lifestyle": [
            "cashmere socks luxury women", "silk pillowcase premium",
            "crystal wine decanter set", "personalized jewelry box",
            "monogram robe luxury", "champagne flutes crystal set",
            "essential oil diffuser premium", "weighted blanket luxury",
            "gold plated jewelry set", "premium leather phone case",
        ],
        "Wedding": [
            "wedding favor boxes mini", "bridesmaid proposal box",
            "champagne flutes wedding set", "custom wedding vow book",
            "bridal shower sash ribbon", "wedding card box rustic",
            "ring dish jewelry holder", "honeymoon survival kit",
            "bride gift bag set", "wedding guest book alternative",
        ],
        "Funny": [
            "cat butt tissue holder", "funny wine glass stemless",
            "novelty socks funny print", "funny coffee mug novelty",
            "gag gift box elaborate", "funny apron cooking adult",
            "funny bobblehead custom", "toilet paper gold novelty",
            "dad joke book collection", "prank gift box",
        ],
        "Productivity & Education": [
            "standing desk converter", "noise canceling earmuffs",
            "pomodoro timer mechanical", "desk pad large leather",
            "book stand adjustable reading", "lap desk with cushion",
            "planner weekly undated", "whiteboard wall sticker",
            "headphone stand wood", "cable management raceway",
        ],
        "Surprise Me": [
            "posture corrector back brace", "dog anxiety vest calming",
            "led strip lights smart wifi", "gua sha facial tool",
            "resistance bands set loop", "car phone mount magnetic",
            "vegetable chopper manual", "wireless charger stand 3in1",
            "custom night sky map print", "diamond painting kit",
            "beeswax wraps reusable", "laser level self leveling",
            "baby monitor split screen", "silk pillowcase premium",
            "funny wine glass stemless",
        ],
    }

    def _generate_candidates(self, niche: str) -> list[str]:
        """
        Retourne des produits réels et spécifiques pour la niche choisie.
        Cherche d'abord dans NICHE_PRODUCTS (correspondance exacte ou partielle),
        puis génère des variantes avec les mots-clés utilisateur.
        """
        import random

        # Mode Surprise : mélanger et prendre 8 produits aléatoires
        if niche in ("__surprise__", "Surprise Me"):
            pool = self.NICHE_PRODUCTS.get("Surprise Me", []).copy()
            random.shuffle(pool)
            return pool[:8]

        # Correspondance exacte
        if niche in self.NICHE_PRODUCTS:
            products = self.NICHE_PRODUCTS[niche].copy()
            random.shuffle(products)
            return products[:10]

        # Correspondance partielle (ex: "Sport & Outdoor" → "Sport")
        for key, products in self.NICHE_PRODUCTS.items():
            if any(word.lower() in key.lower() for word in niche.split() if len(word) > 3):
                return products[:10]

        # Fallback : utiliser le nom de la niche comme préfixe de recherche réaliste
        base_products = [
            "organizer storage solution", "gadget tool kit",
            "portable device mini", "smart accessory",
            "premium set gift", "beginner kit starter",
            "professional tool quality", "eco friendly set",
            "wireless charging stand", "adjustable holder rack",
        ]
        return [f"{niche} {p}" for p in base_products[:10]]

    # ──────────────────────────────────────────────
    # POINT D'ENTRÉE PRINCIPAL
    # ──────────────────────────────────────────────
    async def start(self, config: dict = None):
        """Point d'entrée principal."""
        if config is None:
            config = self.ask_startup_questions()

        products = await self.run_session(config)

        # Export des résultats
        print("\n📁 Export des résultats...")
        output_path = self.exporter.export_all(products, config)
        print(f"   ✅ Fichier exporté : {output_path}")

        return products


# ──────────────────────────────────────────────
# LANCEMENT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    orchestrator = Orchestrator()
    asyncio.run(orchestrator.start())
