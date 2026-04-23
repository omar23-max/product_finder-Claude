# 🏆 Product Finder — Agent E-commerce Multi-Sources

Trouve automatiquement des produits gagnants en analysant en parallèle
Facebook Ads, TikTok, Amazon, AliExpress, Alibaba et CJ Dropshipping.

**URL publique** : déployé sur Render — accessible depuis n'importe où, sans localhost.

---

## 🚀 Déploiement en 3 étapes

### Étape 1 — Mettre sur GitHub

```bash
# Dans le dossier product_finder_v4_webapp
git init
git add .
git commit -m "Initial commit — Product Finder V6"

# Créer un repo sur github.com puis :
git remote add origin https://github.com/TON-USERNAME/product-finder.git
git branch -M main
git push -u origin main
```

### Étape 2 — Déployer sur Render

1. Va sur **render.com** et crée un compte gratuit
2. **New → Web Service → Connect a repository**
3. Sélectionne ton repo GitHub `product-finder`
4. Dans **Environment Variables**, ajoute :
   ```
   APIFY_API_KEY = apify_api_xxxxxxxxxxxx
   ```
5. Clique **Create Web Service**
6. Ton URL : `https://product-finder-xxxx.onrender.com`

### Étape 3 — Auto-déploiement

A chaque `git push origin main` :
- GitHub Actions lance les tests
- Si OK → Render redéploie automatiquement (~2 min)
- L'URL reste la même

```bash
git add .
git commit -m "Amélioration xyz"
git push origin main
```

---

## Variables d'environnement

| Variable | Obligatoire | Description |
|---|---|---|
| APIFY_API_KEY | Oui | Clé API Apify |
| CJ_API_KEY | Non | Clé API CJ Dropshipping |

Ne jamais commiter le fichier .env — il est dans .gitignore.

---

## Développement local

```bash
git clone https://github.com/TON-USERNAME/product-finder.git
cd product-finder
pip install -r requirements.txt
cp .env.example .env
python app.py
```
