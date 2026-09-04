"""
Analyseur de repas par photo
------------------------------
Upload une photo d'assiette -> Claude identifie les aliments
-> estimation calories / protéines / glucides / lipides.
"""

import base64
import json
import os

import streamlit as st
from openai import OpenAI

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

st.set_page_config(page_title="Analyseur de repas", page_icon="🍽️", layout="centered")

MODEL = "gpt-4o"

# La clé API vient soit des secrets Streamlit (déploiement), soit d'une
# variable d'environnement (usage local).
API_KEY = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

PROMPT = """Tu es un nutritionniste expert. Analyse cette photo de repas et identifie
chaque aliment visible avec une estimation de sa portion.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après, sans
balises markdown, au format exact suivant :

{
  "aliments": [
    {
      "nom": "nom de l'aliment",
      "portion_g": nombre_en_grammes,
      "calories": nombre,
      "proteines_g": nombre,
      "glucides_g": nombre,
      "lipides_g": nombre
    }
  ],
  "total": {
    "calories": nombre,
    "proteines_g": nombre,
    "glucides_g": nombre,
    "lipides_g": nombre
  },
  "confiance": "haute" | "moyenne" | "basse",
  "note": "courte remarque si l'estimation est incertaine, sinon chaîne vide"
}

Sois réaliste dans tes estimations de portions (regarde la taille de l'assiette
et des couverts comme référence). Si un aliment est composé (ex: un sandwich),
décompose-le en ingrédients principaux si c'est visible, sinon garde-le comme
un seul élément."""


# ----------------------------------------------------------------------
# Fonctions
# ----------------------------------------------------------------------

def encode_image(uploaded_file) -> tuple[str, str]:
    """Encode l'image uploadée en base64 et détecte son type MIME."""
    file_bytes = uploaded_file.getvalue()
    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")

    ext = uploaded_file.name.lower().split(".")[-1]
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    media_type = mime_map.get(ext, "image/jpeg")

    return b64, media_type


def analyze_meal(uploaded_file, api_key: str) -> dict:
    """Envoie l'image à GPT-4o et retourne l'analyse nutritionnelle sous forme de dict."""
    client = OpenAI(api_key=api_key)
    b64_image, media_type = encode_image(uploaded_file)
    data_url = f"data:{media_type};base64,{b64_image}"

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )

    raw_text = response.choices[0].message.content.strip()

    # Filet de sécurité si le modèle ajoute quand même des balises markdown
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    return json.loads(raw_text)


# ----------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------

st.title("🍽️ Analyseur de repas")
st.caption("Prends une photo de ton assiette, l'IA fait le reste.")

if not API_KEY:
    st.warning(
        "Aucune clé API trouvée. Ajoute OPENAI_API_KEY dans les secrets Streamlit "
        "ou en variable d'environnement pour utiliser l'application."
    )

uploaded_file = st.file_uploader("Photo du repas", type=["jpg", "jpeg", "png", "webp"])

if uploaded_file is not None:
    st.image(uploaded_file, caption="Photo envoyée", use_container_width=True)

    if st.button("Analyser mon repas", type="primary", disabled=not API_KEY):
        with st.spinner("Analyse en cours..."):
            try:
                result = analyze_meal(uploaded_file, API_KEY)
            except json.JSONDecodeError:
                st.error("Le modèle n'a pas renvoyé un JSON valide. Réessaie avec une autre photo.")
                st.stop()
            except Exception as e:
                st.error(f"Erreur pendant l'analyse : {e}")
                st.stop()

        total = result.get("total", {})
        confiance = result.get("confiance", "moyenne")
        note = result.get("note", "")

        st.divider()
        st.subheader("Résumé nutritionnel")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Calories", f"{total.get('calories', 0):.0f} kcal")
        col2.metric("Protéines", f"{total.get('proteines_g', 0):.0f} g")
        col3.metric("Glucides", f"{total.get('glucides_g', 0):.0f} g")
        col4.metric("Lipides", f"{total.get('lipides_g', 0):.0f} g")

        confiance_emoji = {"haute": "🟢", "moyenne": "🟡", "basse": "🔴"}.get(confiance, "🟡")
        st.caption(f"{confiance_emoji} Confiance de l'estimation : {confiance}")
        if note:
            st.info(note)

        st.subheader("Détail par aliment")
        for aliment in result.get("aliments", []):
            with st.expander(f"{aliment.get('nom', 'Aliment')} — {aliment.get('portion_g', 0):.0f} g"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Calories", f"{aliment.get('calories', 0):.0f}")
                c2.metric("Protéines", f"{aliment.get('proteines_g', 0):.0f} g")
                c3.metric("Glucides", f"{aliment.get('glucides_g', 0):.0f} g")
                c4.metric("Lipides", f"{aliment.get('lipides_g', 0):.0f} g")

        st.divider()
        st.caption(
            "⚠️ Ces valeurs sont des estimations basées sur une analyse visuelle et peuvent "
            "s'écarter de la réalité. Ne pas utiliser comme seule base pour un suivi médical."
        )
else:
    st.info("Uploade une photo pour commencer.")