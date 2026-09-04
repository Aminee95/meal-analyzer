"""
Analyseur de repas par photo — v3
------------------------------------
Upload/scan une photo d'assiette -> l'IA identifie les aliments -> macros
détaillées -> suivi journalier complet (calories + protéines + glucides + lipides)
-> historique éditable + export CSV.
"""

import base64
import csv
import io
import json
import os
import sqlite3
import time
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
MAX_IMAGE_DIMENSION = 800
JPEG_QUALITY = 80
MAX_UPLOAD_MB = 10
MAX_RETRIES = 2

MEAL_TYPES = ["🌅 Petit-déjeuner", "☀️ Déjeuner", "🌙 Dîner", "🍎 Collation"]

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
# Base de données
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
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )

        # Migration automatique : ajoute meal_type si la base existait déjà sans cette colonne
        existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(meals)").fetchall()]
        if "meal_type" not in existing_cols:
            conn.execute("ALTER TABLE meals ADD COLUMN meal_type TEXT DEFAULT ''")


def save_meal(result: dict, meal_type: str):
    total = result.get("total", {})
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO meals (timestamp, meal_type, aliments_json, calories, proteines_g, glucides_g, lipides_g) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                meal_type,
                json.dumps(result.get("aliments", []), ensure_ascii=False),
                total.get("calories", 0),
                total.get("proteines_g", 0),
                total.get("glucides_g", 0),
                total.get("lipides_g", 0),
            ),
        )


def delete_meal(meal_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))


def get_meals(limit: int = 200):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM meals ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_today_totals() -> dict:
    today_str = date.today().isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT SUM(calories), SUM(proteines_g), SUM(glucides_g), SUM(lipides_g) "
            "FROM meals WHERE timestamp LIKE ?",
            (f"{today_str}%",),
        ).fetchone()
    cal, prot, gluc, lip = row
    return {
        "calories": cal or 0.0,
        "proteines_g": prot or 0.0,
        "glucides_g": gluc or 0.0,
        "lipides_g": lip or 0.0,
    }


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
# Image + appel API (avec réessai automatique)
# ----------------------------------------------------------------------

def compress_image(uploaded_file) -> tuple[str, str]:
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

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=1500,
                timeout=30,
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
        except json.JSONDecodeError as e:
            last_error = e
            continue  # une reformulation de la même image peut aider
        except Exception as e:
            last_error = e
            time.sleep(1)
            continue

    raise RuntimeError(f"Échec après {MAX_RETRIES + 1} tentatives : {last_error}")


# ----------------------------------------------------------------------
# Aide visuelle : couleur selon proximité de l'objectif
# ----------------------------------------------------------------------

def macro_bar(label: str, value: float, goal: float, unit: str = "g"):
    ratio = min(value / goal, 1.2) if goal else 0
    if ratio < 0.5:
        color = "🔵"
    elif ratio <= 1.05:
        color = "🟢"
    else:
        color = "🟠"
    st.write(f"{color} **{label}** — {value:.0f} / {goal:.0f} {unit}")
    st.progress(min(ratio, 1.0))


def display_result(result: dict):
    total = result.get("total", {})
    confiance = result.get("confiance", "moyenne")
    note = result.get("note", "")

    st.divider()
    st.subheader("Résumé du repas")

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
# Barre latérale — objectifs + réglages
# ----------------------------------------------------------------------

st.sidebar.header("🎯 Objectifs journaliers")
cal_goal = st.sidebar.number_input("Calories (kcal)", 500, 6000, int(get_setting("goal_cal", "2000")), 50)
prot_goal = st.sidebar.number_input("Protéines (g)", 20, 400, int(get_setting("goal_prot", "100")), 5)
gluc_goal = st.sidebar.number_input("Glucides (g)", 20, 600, int(get_setting("goal_gluc", "250")), 10)
lip_goal = st.sidebar.number_input("Lipides (g)", 10, 250, int(get_setting("goal_lip", "70")), 5)

for key, val in [("goal_cal", cal_goal), ("goal_prot", prot_goal), ("goal_gluc", gluc_goal), ("goal_lip", lip_goal)]:
    if str(val) != get_setting(key):
        set_setting(key, str(val))

st.sidebar.divider()
st.sidebar.header("⚡ Performance")
fast_mode = st.sidebar.toggle("Mode rapide (gpt-4o-mini)", value=True)
st.sidebar.caption("Plus rapide et moins cher. Désactive pour plus de précision sur des plats complexes.")
MODEL = "gpt-4o-mini" if fast_mode else "gpt-4o"

st.sidebar.divider()
st.sidebar.subheader("📅 Aujourd'hui")
today = get_today_totals()
macro_bar("Calories", today["calories"], cal_goal, "kcal")
macro_bar("Protéines", today["proteines_g"], prot_goal)
macro_bar("Glucides", today["glucides_g"], gluc_goal)
macro_bar("Lipides", today["lipides_g"], lip_goal)


# ----------------------------------------------------------------------
# Contenu principal
# ----------------------------------------------------------------------

st.title("🍽️ Analyseur de repas")
st.caption("Prends une photo de ton assiette, l'IA fait le reste.")

if not API_KEY:
    st.warning("Aucune clé API trouvée. Ajoute OPENAI_API_KEY dans les secrets Streamlit.")

tab_analyser, tab_historique = st.tabs(["📸 Analyser", "📊 Historique"])

with tab_analyser:
    meal_type = st.selectbox("Type de repas", MEAL_TYPES)

    source = st.radio("Photo", ["📷 Prendre une photo", "🖼️ Depuis la galerie"], horizontal=True)
    uploaded_file = (
        st.camera_input("Photo du repas") if source == "📷 Prendre une photo"
        else st.file_uploader("Photo du repas", type=["jpg", "jpeg", "png", "webp"])
    )

    if uploaded_file is not None:
        if uploaded_file.size > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(f"Image trop lourde (max {MAX_UPLOAD_MB} Mo). Choisis une photo plus légère.")
            st.stop()

        if source != "📷 Prendre une photo":
            st.image(uploaded_file, caption="Photo envoyée", use_container_width=True)

        if st.button("Analyser mon repas", type="primary", disabled=not API_KEY):
            with st.spinner(f"Analyse en cours ({MODEL})..."):
                try:
                    result = analyze_meal(uploaded_file, API_KEY, MODEL)
                except RuntimeError as e:
                    st.error(f"L'analyse a échoué après plusieurs tentatives : {e}")
                    st.stop()

            save_meal(result, meal_type)
            st.session_state["last_result"] = result
            st.rerun()
    else:
        st.info("Prends ou choisis une photo pour commencer.")

    if "last_result" in st.session_state:
        display_result(st.session_state["last_result"])
        st.divider()
        st.caption(
            "⚠️ Estimations basées sur une analyse visuelle, à titre indicatif. "
            "Ne pas utiliser comme seule base pour un suivi médical."
        )
        if st.button("Effacer ce résultat"):
            del st.session_state["last_result"]
            st.rerun()

with tab_historique:
    meals = get_meals()

    if not meals:
        st.info("Aucun repas analysé pour le moment.")
    else:
        chart_data = {}
        for m in meals:
            day = m["timestamp"][:10]
            chart_data[day] = chart_data.get(day, 0) + (m["calories"] or 0)

        st.subheader("Calories par jour")
        st.bar_chart(dict(sorted(chart_data.items())))

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["Date", "Type de repas", "Calories", "Protéines (g)", "Glucides (g)", "Lipides (g)"])
        for m in meals:
            writer.writerow([m["timestamp"], m["meal_type"], m["calories"], m["proteines_g"], m["glucides_g"], m["lipides_g"]])
        st.download_button("⬇️ Exporter en CSV", csv_buffer.getvalue(), file_name="historique_repas.csv", mime="text/csv")

        st.subheader("Repas récents")
        for m in meals[:30]:
            ts = datetime.fromisoformat(m["timestamp"]).strftime("%d/%m %H:%M")
            label = f"{m['meal_type']} — {ts} — {m['calories']:.0f} kcal"
            with st.expander(label):
                aliments = json.loads(m["aliments_json"])
                for a in aliments:
                    st.write(
                        f"- {a.get('nom', '')} ({a.get('portion_g', 0):.0f} g) — "
                        f"{a.get('calories', 0):.0f} kcal · P {a.get('proteines_g', 0):.0f}g · "
                        f"G {a.get('glucides_g', 0):.0f}g · L {a.get('lipides_g', 0):.0f}g"
                    )
                if st.button("🗑️ Supprimer cette entrée", key=f"del_{m['id']}"):
                    delete_meal(m["id"])
                    st.rerun()