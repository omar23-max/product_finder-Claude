"""
scorer.py — Calcul du score final pondéré
Agrège les scores des 4 agents → score /190 → statut final
"""

from config import SCORING


class ProductScorer:
    """
    Calcule le score final pondéré à partir des résultats des 4 agents.

    Barème :
    - Agent 1 (Tendances)   : max 45 pts  (coeff x1.5)
    - Agent 2 (Social)      : max 45 pts  (coeff x1.5)
    - Agent 3 (Fournisseurs): max 70 pts  (coeff x2.0)
    - Agent 4 (Concurrence) : max 30 pts  (coeff x1.0)
    - TOTAL                 : max 190 pts
    """

    def compute_final_score(self, a1: dict, a2: dict, a3: dict, a4: dict) -> dict:

        s1 = a1.get("score", {}).get("weighted", 0) or 0
        s2 = a2.get("score", {}).get("weighted", 0) or 0
        s3 = a3.get("score", {}).get("weighted", 0) or 0
        s4 = a4.get("score", {}).get("weighted", 0) or 0

        # ── Robustesse : si agent échoue (API timeout), ne pas pénaliser à 0 ──
        # On donne un score partiel minimum = 30% du max si l'agent a tourné
        # mais n'a pas pu récupérer de données (≠ produit mauvais)
        agents_ran = {
            "a1": a1.get("agent") is not None,
            "a2": a2.get("agent") is not None,
            "a3": a3.get("agent") is not None,
            "a4": a4.get("agent") is not None,
        }
        api_failure_bonus = 0
        failure_notes = []
        if s3 == 0 and agents_ran["a3"]:
            # Agent3 a tourné mais prix absent → API scraping échouée
            # On donne 30% du max (21 pts) pour ne pas bloquer
            s3 = 21.0
            api_failure_bonus += 21
            failure_notes.append("Prix fournisseur non récupéré (scraping) — score estimé")
        if s2 == 0 and agents_ran["a2"]:
            # Agent2 a tourné mais FB ads absent → 30% du max (13 pts)
            s2_tiktok = a2.get("tiktok", {}).get("viral_videos_count", 0)
            if s2_tiktok > 0:
                s2 = round(13 + min(s2_tiktok * 1.5, 10), 1)
                api_failure_bonus += s2
                failure_notes.append(f"FB Ads non récupéré — score basé sur TikTok ({s2_tiktok} vidéos)")

        total = round(s1 + s2 + s3 + s4, 1)

        if total >= SCORING["winner_threshold"]:
            status = "✅ GAGNANT"
            action = "Lancer les créatives et tester immédiatement"
        elif total >= SCORING["potential_threshold"]:
            status = "🟡 POTENTIEL"
            action = "Affiner l'offre ou l'angle avant de lancer"
        else:
            status = "🔴 REJETER"
            action = "Passer au produit suivant"

        # Note : si beaucoup de données manquantes, signaler
        if api_failure_bonus > 30:
            action += " ⚠️ (données partielles — relancer en mode réel pour confirmer)"

        # Vérification : si Agent3 (marge) = 0 ET aucun TikTok → vraiment rejeter
        if s3 == 0 and s2 == 0:
            status = "🔴 REJETER"
            action = "Aucune donnée récupérée — vérifier les actors Apify"

        return {
            "total"         : total,
            "max"           : 190,
            "percentage"    : round((total / 190) * 100, 1),
            "status"        : status,
            "action"        : action,
            "breakdown"     : {
                "agent1_trends"     : {"score": s1, "max": 45},
                "agent2_social"     : {"score": s2, "max": 45},
                "agent3_suppliers"  : {"score": s3, "max": 70},
                "agent4_competition": {"score": s4, "max": 30},
            },
            "verdicts"      : {
                "agent1": a1.get("verdict", "N/A"),
                "agent2": a2.get("verdict", "N/A"),
                "agent3": a3.get("verdict", "N/A"),
                "agent4": a4.get("verdict", "N/A"),
            }
        }
