# 🍽️ Assiette

**Photographie ton repas. Connais tes macros à la seconde près.**

Une application d'analyse nutritionnelle par IA : prends en photo (ou upload) ton
assiette, et une vision par ordinateur multimodale identifie chaque aliment,
estime les portions, et calcule calories + protéines + glucides + lipides —
avec suivi journalier, tendances, et objectifs personnalisés.

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991)

---

## ✨ Fonctionnalités

- 📷 **Scan en un geste** — appareil photo ou galerie, directement depuis le mobile
- 🧠 **Analyse IA multimodale** — identification des aliments + estimation des portions par vision par ordinateur
- 🎯 **Objectifs personnalisés** — calculés automatiquement (formule de Mifflin-St Jeor) selon poids, taille, âge et niveau d'activité
- 📊 **Suivi journalier complet** — calories et macros (protéines/glucides/lipides), pas seulement les calories
- 📈 **Tendances** — évolution sur 30 jours, comparaison semaine par semaine
- 🗂️ **Historique éditable** — export CSV, suppression d'entrées, classement par type de repas
- ⚡ **Optimisé perf** — compression d'image, cache de résultats, modèle rapide par défaut
- 🛡️ **Robuste** — réessai automatique, migration de base de données, résultats reproductibles (temperature=0)

## 🏗️ Stack technique

| Composant | Techno |
|---|---|
| Interface | Streamlit |
| IA vision | OpenAI GPT-4o / GPT-4o-mini |
| Stockage | SQLite (local, zéro dépendance externe) |
| Traitement image | Pillow |
| Déploiement | Streamlit Community Cloud |

## 🚀 Lancer en local

```bash
python -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate

pip install -r requirements.txt

# Crée .streamlit/secrets.toml avec :
# OPENAI_API_KEY = "ta-clé-ici"

streamlit run app.py
```

## 🌍 Déploiement

Déployé gratuitement sur [Streamlit Community Cloud](https://share.streamlit.io) :
connecte le dépôt GitHub, ajoute la clé API dans les secrets, et l'app est en
ligne avec une URL publique en 2 minutes — accessible et installable comme une
app depuis n'importe quel téléphone.

## 📌 Pourquoi ce projet

Ce projet a été pensé comme un exercice d'ingénierie IA de bout en bout :
intégration d'un modèle multimodal, conception d'un prompt structuré et
reproductible, gestion des coûts et de la latence (compression d'image, cache,
choix de modèle), persistance des données, et une interface pensée pour être
utilisée au quotidien — pas juste une démo technique.

## ⚠️ Avertissement

Les estimations nutritionnelles sont basées sur une analyse visuelle et sont
indicatives. Ne pas utiliser comme seule base pour un suivi médical ou un
régime strict.