"""
Analyseur de repas par photo — v2
------------------------------------
Upload une photo d'assiette -> l'IA identifie les aliments -> estimation
calories / macros -> historique + objectif journalier.

Optimisations perf :
- image redimensionnée + compressée avant envoi (upload + analyse plus rapides)
- modèle rapide (gpt-4o-mini) par défaut, gpt-4o en option pour plus de précision
"""

import base64
import io
import json
import os
import sqlite3
from datetime import date, datetime

import streamlit as st
from openai import OpenAI
from PIL import Image

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

st.set_page_config(page_title="Analyseur de repas", page_icon="🍽️", layout="centered")

API_KEY = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

DB_PATH = "meals.db"
MAX_IMAGE_DIMENSION = 800  # px — réduit fortement le temps d'upload/analyse
JPEG_QUALITY = 80

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
# Base de données (historique + objectif)
# ----------------------------------------------------------------------

def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                aliments_json TEXT NOT NULL,
                calories REAL, proteines_g REAL, glucides_g REAL, lipides_g REAL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )


def save_meal(result: dict):
    total = result.get("total", {})
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO meals (timestamp, aliments_json, calories, proteines_g, glucides_g, lipides_g) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                json.dumps(result.get("aliments", []), ensure_ascii=False),
                total.get("calories", 0),
                total.get("proteines_g", 0),
                total.get("glucides_g", 0),
                total.get("lipides_g", 0),
            ),
        )


def get_meals(limit: int = 100):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM meals ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_today_total() -> float:
    today_str = date.today().isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT SUM(calories) FROM meals WHERE timestamp LIKE ?", (f"{today_str}%",)
        ).fetchone()
    return row[0] or 0.0


def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


init_db()


# ----------------------------------------------------------------------
# Traitement image + appel API
# ----------------------------------------------------------------------

def compress_image(uploaded_file) -> tuple[str, str]:
    """Redimensionne et compresse l'image en JPEG avant envoi.
    Réduit fortement le poids envoyé -> analyse plus rapide et moins chère."""
    img = Image.open(uploaded_file).convert("RGB")

    img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    b64 = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")

    return b64, "image/jpeg"


def analyze_meal(uploaded_file, api_key: str, model: str) -> dict:
    client = OpenAI(api_key=api_key)
    b64_image, media_type = compress_image(uploaded_file)
    data_url = f"data:{media_type};base64,{b64_image}"

    response = client.chat.completions.create(
        model=model,
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

    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    return json.loads(raw_text)


def display_result(result: dict):
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


# ----------------------------------------------------------------------
# Interface — barre latérale (objectif + réglages perf)
# ----------------------------------------------------------------------

st.sidebar.header("🎯 Objectif journalier")
current_goal = get_setting("daily_goal", "2000")
new_goal = st.sidebar.number_input(
    "Objectif calorique (kcal)", min_value=500, max_value=6000,
    value=int(current_goal), step=50,
)
if str(new_goal) != current_goal:
    set_setting("daily_goal", str(new_goal))

st.sidebar.divider()
st.sidebar.header("⚡ Performance")
fast_mode = st.sidebar.toggle("Mode rapide (gpt-4o-mini)", value=True)
st.sidebar.caption(
    "Le mode rapide analyse en ~2x moins de temps et coûte moins cher. "
    "Désactive-le si tu veux une estimation plus précise sur des plats complexes."
)
MODEL = "gpt-4o-mini" if fast_mode else "gpt-4o"

today_total = get_today_total()
progress_ratio = min(today_total / new_goal, 1.0) if new_goal else 0
st.sidebar.divider()
st.sidebar.subheader("Aujourd'hui")
st.sidebar.progress(progress_ratio)
st.sidebar.caption(f"{today_total:.0f} / {new_goal} kcal")


# ----------------------------------------------------------------------
# Interface — contenu principal
# ----------------------------------------------------------------------

st.title("🍽️ Analyseur de repas")
st.caption("Prends une photo de ton assiette, l'IA fait le reste.")

if not API_KEY:
    st.warning(
        "Aucune clé API trouvée. Ajoute OPENAI_API_KEY dans les secrets Streamlit "
        "ou en variable d'environnement pour utiliser l'application."
    )

tab_analyser, tab_historique = st.tabs(["📸 Analyser", "📊 Historique"])

with tab_analyser:
    source = st.radio(
        "Comment veux-tu fournir la photo ?",
        ["📷 Prendre une photo", "🖼️ Choisir depuis la galerie"],
        horizontal=True,
    )

    if source == "📷 Prendre une photo":
        uploaded_file = st.camera_input("Photo du repas")
    else:
        uploaded_file = st.file_uploader("Photo du repas", type=["jpg", "jpeg", "png", "webp"])

    if uploaded_file is not None:
        if source != "📷 Prendre une photo":
            st.image(uploaded_file, caption="Photo envoyée", use_container_width=True)

        if st.button("Analyser mon repas", type="primary", disabled=not API_KEY):
            with st.spinner(f"Analyse en cours ({MODEL})..."):
                try:
                    result = analyze_meal(uploaded_file, API_KEY, MODEL)
                except json.JSONDecodeError:
                    st.error("Le modèle n'a pas renvoyé un JSON valide. Réessaie avec une autre photo.")
                    st.stop()
                except Exception as e:
                    st.error(f"Erreur pendant l'analyse : {e}")
                    st.stop()

            save_meal(result)
            display_result(result)

            st.divider()
            st.caption(
                "⚠️ Ces valeurs sont des estimations basées sur une analyse visuelle et peuvent "
                "s'écarter de la réalité. Ne pas utiliser comme seule base pour un suivi médical."
            )
            st.rerun()
    else:
        st.info("Uploade une photo pour commencer.")

with tab_historique:
    meals = get_meals()

    if not meals:
        st.info("Aucun repas analysé pour le moment. Va dans l'onglet Analyser pour commencer.")
    else:
        chart_data = {}
        for m in meals:
            day = m["timestamp"][:10]
            chart_data[day] = chart_data.get(day, 0) + (m["calories"] or 0)

        st.subheader("Calories par jour")
        st.bar_chart(dict(sorted(chart_data.items())))

        st.subheader("Repas récents")
        for m in meals[:20]:
            ts = datetime.fromisoformat(m["timestamp"]).strftime("%d/%m %H:%M")
            with st.expander(f"{ts} — {m['calories']:.0f} kcal"):
                aliments = json.loads(m["aliments_json"])
                for a in aliments:
                    st.write(f"- {a.get('nom', '')} ({a.get('portion_g', 0):.0f} g) — {a.get('calories', 0):.0f} kcal")