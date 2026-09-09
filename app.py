"""
Analyseur de repas par photo — v3
------------------------------------
Upload/scan une photo d'assiette -> l'IA identifie les aliments -> macros
détaillées -> suivi journalier complet (calories + protéines + glucides + lipides)
-> historique éditable + export CSV.
"""

import base64
import csv
import hashlib
import io
import json
import os
import sqlite3
import time
from datetime import date, datetime

import streamlit as st
from openai import OpenAI
from PIL import Image
import pandas as pd

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

st.set_page_config(page_title="Assiette", page_icon="🍽️", layout="centered")

dark_mode = st.sidebar.toggle("🌙 Mode sombre", key="dark_mode")
st.sidebar.divider()

if dark_mode:
    THEME = {
        "bg": "#18160F", "sidebar_bg": "#201C15", "card_bg": "#241F17", "border": "#3A3226",
        "ink": "#F3EFE4", "muted": "#A79E8C", "track": "#332C21",
    }
    MACRO_COLORS = {
        "calories": "#FF7A61", "proteines_g": "#6FA37D", "glucides_g": "#F0B857", "lipides_g": "#9686C4",
    }
else:
    THEME = {
        "bg": "#FCFBF7", "sidebar_bg": "#F5F1E8", "card_bg": "#FFFFFF", "border": "#E7E1D6",
        "ink": "#1F2A24", "muted": "#6B6459", "track": "#EFEAE0",
    }
    MACRO_COLORS = {
        "calories": "#E8543E", "proteines_g": "#4C7C59", "glucides_g": "#E8A33D", "lipides_g": "#6B5B95",
    }

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Work+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {{ font-family: 'Work Sans', sans-serif; color: {THEME["ink"]}; }}
h1, h2, h3 {{ font-family: 'Fraunces', serif !important; font-weight: 700 !important; letter-spacing: -0.01em; color: {THEME["ink"]}; }}
p, span, label, div {{ color: {THEME["ink"]}; }}
.stApp {{ background-color: {THEME["bg"]}; }}

.stButton > button, .stDownloadButton > button {{
    background-color: {MACRO_COLORS["calories"]}; color: white; border: none; border-radius: 10px;
    font-weight: 600; padding: 0.5rem 1.25rem; transition: opacity 0.15s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ opacity: 0.85; color: white; }}

.stTabs [data-baseweb="tab"] {{ font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.05rem; }}
.stTabs [aria-selected="true"] {{ color: {MACRO_COLORS["calories"]} !important; border-bottom-color: {MACRO_COLORS["calories"]} !important; }}

[data-testid="stSidebar"] {{ background-color: {THEME["sidebar_bg"]}; border-right: 1px solid {THEME["border"]}; }}
[data-testid="stSidebar"] * {{ color: {THEME["ink"]}; }}

.macro-card {{
    background: {THEME["card_bg"]}; border: 1px solid {THEME["border"]}; border-radius: 12px;
    padding: 0.85rem 1rem; margin-bottom: 0.6rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, {0.25 if dark_mode else 0.05});
}}
.macro-label {{ font-size: 0.82rem; color: {THEME["muted"]}; margin-bottom: 0.15rem; }}
.macro-value {{ font-family: 'Fraunces', serif; font-size: 1.55rem; font-weight: 700; }}
.bar-track {{ background: {THEME["track"]}; border-radius: 999px; height: 10px; width: 100%; overflow: hidden; margin-top: 0.35rem; }}
.bar-fill {{ height: 100%; border-radius: 999px; }}

.hero {{ display: flex; align-items: center; gap: 0.85rem; margin-bottom: 0.2rem; }}
.hero-mark {{
    width: 46px; height: 46px; border-radius: 13px; background: {MACRO_COLORS["calories"]};
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    box-shadow: 0 4px 14px rgba(232, 84, 62, 0.28);
}}
.hero-title {{ font-family: 'Fraunces', serif; font-weight: 700; font-size: 2rem; line-height: 1.1; margin: 0; color: {THEME["ink"]}; }}
.hero-tagline {{ color: {THEME["muted"]}; font-size: 0.98rem; margin-top: 0.15rem; }}

.badge {{
    display: inline-flex; align-items: center; gap: 0.35rem; border-radius: 999px;
    padding: 0.3rem 0.85rem; font-size: 0.82rem; font-weight: 600;
}}

[data-testid="stExpander"] {{
    border: 1px solid {THEME["border"]} !important; border-radius: 12px !important;
    background: {THEME["card_bg"]};
    box-shadow: 0 2px 8px rgba(0, 0, 0, {0.2 if dark_mode else 0.04});
}}
[data-testid="stExpander"] summary {{ font-family: 'Fraunces', serif; font-weight: 600; }}

.stAlert, [data-testid="stNotification"] {{ border-radius: 12px !important; }}

/* Ajustements mobile */
@media (max-width: 480px) {{
    .hero-mark {{ width: 38px; height: 38px; border-radius: 11px; }}
    .hero-title {{ font-size: 1.55rem; }}
    .hero-tagline {{ font-size: 0.85rem; }}
    .macro-card {{ padding: 0.65rem 0.75rem; }}
    .macro-value {{ font-size: 1.25rem; }}
    .stTabs [data-baseweb="tab"] {{ font-size: 0.9rem; padding: 0.4rem 0.5rem; }}
    div[data-testid="column"] {{ min-width: calc(50% - 0.5rem) !important; }}
}}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

HERO_HTML = """
<div class="hero">
  <div class="hero-mark">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="9" stroke="white" stroke-width="1.6"/>
      <circle cx="12" cy="12" r="4.5" stroke="white" stroke-width="1.6"/>
    </svg>
  </div>
  <div>
    <p class="hero-title">Assiette</p>
    <p class="hero-tagline">Photographie ton repas, connais tes macros à la seconde près.</p>
  </div>
</div>
"""

API_KEY = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "")
DAILY_API_LIMIT = int(st.secrets.get("DAILY_API_LIMIT", 60))

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
un seul élément.

Méthode à suivre pour rester cohérent : base-toi sur les valeurs nutritionnelles
standards par 100g des aliments couramment admises (tables nutritionnelles
usuelles), puis applique-les à ton estimation de portion en grammes. Ne varie
pas ta méthode de calcul d'une analyse à l'autre pour un même type d'aliment."""


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
        conn.execute(
            """CREATE TABLE IF NOT EXISTS api_usage (
                day TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS analysis_cache (
                image_hash TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
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


def get_daily_aggregates(days: int = 30) -> list[dict]:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT substr(timestamp, 1, 10) as day,
                      SUM(calories) as calories, SUM(proteines_g) as proteines_g,
                      SUM(glucides_g) as glucides_g, SUM(lipides_g) as lipides_g
               FROM meals GROUP BY day ORDER BY day DESC LIMIT ?""",
            (days,),
        ).fetchall()
    return [dict(r) for r in rows][::-1]  # ordre chronologique croissant


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


class QuotaExceededError(Exception):
    """Levée quand le quota journalier d'appels API est atteint."""


def check_and_increment_quota(daily_limit: int):
    """Vérifie le quota global du jour et l'incrémente. Lève QuotaExceededError si dépassé."""
    today_str = date.today().isoformat()
    with get_connection() as conn:
        row = conn.execute("SELECT count FROM api_usage WHERE day = ?", (today_str,)).fetchone()
        current = row[0] if row else 0
        if current >= daily_limit:
            raise QuotaExceededError(
                f"Quota journalier atteint ({daily_limit} analyses). Réessaie demain."
            )
        conn.execute(
            "INSERT INTO api_usage (day, count) VALUES (?, 1) "
            "ON CONFLICT(day) DO UPDATE SET count = count + 1",
            (today_str,),
        )


def get_quota_usage() -> int:
    today_str = date.today().isoformat()
    with get_connection() as conn:
        row = conn.execute("SELECT count FROM api_usage WHERE day = ?", (today_str,)).fetchone()
    return row[0] if row else 0


def get_cached_analysis(image_hash: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT result_json FROM analysis_cache WHERE image_hash = ?", (image_hash,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def save_cached_analysis(image_hash: str, result: dict):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO analysis_cache (image_hash, result_json, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(image_hash) DO UPDATE SET result_json = excluded.result_json",
            (image_hash, json.dumps(result, ensure_ascii=False), datetime.now().isoformat()),
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
    b64_image, media_type = compress_image(uploaded_file)

    # Si cette image exacte (après compression) a déjà été analysée, on renvoie
    # le même résultat instantanément -> zéro variation, zéro coût, zéro attente.
    image_hash = hashlib.sha256(b64_image.encode("utf-8")).hexdigest()
    cached = get_cached_analysis(image_hash)
    if cached is not None:
        return cached

    check_and_increment_quota(DAILY_API_LIMIT)  # lève QuotaExceededError si dépassé

    client = OpenAI(api_key=api_key)
    data_url = f"data:{media_type};base64,{b64_image}"

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=1500,
                timeout=30,
                temperature=0,   # réponse la plus factuelle/reproductible possible
                seed=42,         # demande au modèle de viser un résultat stable d'un appel à l'autre
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
            result = json.loads(raw_text)
            save_cached_analysis(image_hash, result)
            return result
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

def macro_bar(label: str, value: float, goal: float, macro_key: str, unit: str = "g"):
    ratio = min(value / goal, 1.2) if goal else 0
    color = MACRO_COLORS.get(macro_key, "#E8543E")
    st.markdown(
        f"""<div class="macro-card">
            <div class="macro-label">{label}</div>
            <div class="macro-value" style="color:{color}">{value:.0f} <span style="font-size:0.95rem; color:#6B6459; font-family:'Work Sans',sans-serif;">/ {goal:.0f} {unit}</span></div>
            <div class="bar-track"><div class="bar-fill" style="width:{min(ratio,1.0)*100:.0f}%; background:{color};"></div></div>
        </div>""",
        unsafe_allow_html=True,
    )


def macro_row(label: str, value: float, macro_key: str, unit: str = "g"):
    color = MACRO_COLORS.get(macro_key, "#E8543E")
    st.markdown(
        f"""<div class="macro-card">
            <div class="macro-label">{label}</div>
            <div class="macro-value" style="color:{color}">{value:.0f} {unit}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def empty_state(icon: str, title: str, subtitle: str):
    st.markdown(
        f"""<div class="macro-card" style="text-align:center; padding:2.2rem 1.5rem; border-style:dashed;">
            <div style="font-size:2rem; margin-bottom:0.4rem;">{icon}</div>
            <div style="font-family:'Fraunces',serif; font-weight:600; font-size:1.1rem; color:#1F2A24;">{title}</div>
            <div style="color:#6B6459; font-size:0.9rem; margin-top:0.3rem;">{subtitle}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def display_result(result: dict):
    total = result.get("total", {})
    confiance = result.get("confiance", "moyenne")
    note = result.get("note", "")

    st.divider()
    st.subheader("Résumé du repas")

    col1, col2, col3, col4 = st.columns(4)
    with col1: macro_row("Calories", total.get("calories", 0), "calories", "kcal")
    with col2: macro_row("Protéines", total.get("proteines_g", 0), "proteines_g")
    with col3: macro_row("Glucides", total.get("glucides_g", 0), "glucides_g")
    with col4: macro_row("Lipides", total.get("lipides_g", 0), "lipides_g")

    confiance_colors = {"haute": "#4C7C59", "moyenne": "#E8A33D", "basse": "#E8543E"}
    badge_color = confiance_colors.get(confiance, "#E8A33D")
    st.markdown(
        f"""<span class="badge" style="background:{badge_color}1A; color:{badge_color};">
            ● Confiance {confiance}</span>""",
        unsafe_allow_html=True,
    )
    if note:
        st.info(note)

    st.subheader("Détail par aliment")
    for aliment in result.get("aliments", []):
        with st.expander(f"{aliment.get('nom', 'Aliment')} — {aliment.get('portion_g', 0):.0f} g"):
            c1, c2, c3, c4 = st.columns(4)
            with c1: macro_row("Calories", aliment.get("calories", 0), "calories", "kcal")
            with c2: macro_row("Protéines", aliment.get("proteines_g", 0), "proteines_g")
            with c3: macro_row("Glucides", aliment.get("glucides_g", 0), "glucides_g")
            with c4: macro_row("Lipides", aliment.get("lipides_g", 0), "lipides_g")


# ----------------------------------------------------------------------
# Barre latérale — objectifs + réglages
# ----------------------------------------------------------------------

st.sidebar.header("🧮 Calculer mes objectifs")
with st.sidebar.expander("Estimer automatiquement", expanded=False):
    sexe = st.selectbox("Sexe", ["Femme", "Homme"])
    age = st.number_input("Âge", 14, 100, 30)
    poids = st.number_input("Poids (kg)", 35, 200, 70)
    taille = st.number_input("Taille (cm)", 130, 220, 170)
    activite = st.selectbox(
        "Niveau d'activité",
        ["Sédentaire", "Légèrement actif", "Actif", "Très actif"],
    )
    objectif_poids = st.selectbox("Objectif", ["Maintien", "Perte de poids", "Prise de masse"])

    if st.button("Calculer et appliquer"):
        bmr = (10 * poids + 6.25 * taille - 5 * age + 5) if sexe == "Homme" else (10 * poids + 6.25 * taille - 5 * age - 161)
        activity_factor = {"Sédentaire": 1.2, "Légèrement actif": 1.375, "Actif": 1.55, "Très actif": 1.725}[activite]
        tdee = bmr * activity_factor
        adjustment = {"Maintien": 0, "Perte de poids": -450, "Prise de masse": 300}[objectif_poids]
        calc_calories = max(1200, tdee + adjustment)

        calc_prot = poids * 2.0
        calc_lip = poids * 0.9
        calc_gluc = max(0, (calc_calories - (calc_prot * 4 + calc_lip * 9)) / 4)

        for key, val in [
            ("goal_cal", round(calc_calories)), ("goal_prot", round(calc_prot)),
            ("goal_gluc", round(calc_gluc)), ("goal_lip", round(calc_lip)),
        ]:
            set_setting(key, str(val))
        st.success(f"Objectifs appliqués : {calc_calories:.0f} kcal/jour")
        st.rerun()

st.sidebar.divider()
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
macro_bar("Calories", today["calories"], cal_goal, "calories", "kcal")
macro_bar("Protéines", today["proteines_g"], prot_goal, "proteines_g")
macro_bar("Glucides", today["glucides_g"], gluc_goal, "glucides_g")
macro_bar("Lipides", today["lipides_g"], lip_goal, "lipides_g")

st.sidebar.divider()
usage = get_quota_usage()
st.sidebar.caption(f"🛡️ Quota API : {usage} / {DAILY_API_LIMIT} analyses aujourd'hui")


# ----------------------------------------------------------------------
# Contenu principal
# ----------------------------------------------------------------------

st.markdown(HERO_HTML, unsafe_allow_html=True)

if APP_PASSWORD and not st.session_state.get("authenticated"):
    st.text_input("Code d'accès", type="password", key="password_input")
    if st.button("Entrer"):
        if st.session_state["password_input"] == APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Code incorrect.")
    st.stop()

if not API_KEY:
    st.warning("Aucune clé API trouvée. Ajoute OPENAI_API_KEY dans les secrets Streamlit.")

tab_analyser, tab_historique, tab_tendances = st.tabs(["📸 Analyser", "📊 Historique", "📈 Tendances"])

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
                except QuotaExceededError as e:
                    st.error(f"🛑 {e}")
                    st.stop()
                except RuntimeError as e:
                    st.error(f"L'analyse a échoué après plusieurs tentatives : {e}")
                    st.stop()

            save_meal(result, meal_type)
            st.session_state["last_result"] = result
            st.rerun()
    else:
        empty_state("📷", "Prêt quand tu l'es", "Prends ou choisis une photo de ton repas pour commencer.")

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
        empty_state("📊", "Ton historique est vide", "Chaque repas analysé apparaîtra ici avec son détail complet.")
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

with tab_tendances:
    daily = get_daily_aggregates(days=30)

    if len(daily) < 2:
        st.markdown(
            """<div class="macro-card" style="text-align:center; padding:2rem 1rem;">
                <div class="macro-label" style="font-size:1rem;">Pas encore assez de données</div>
                <div style="color:#6B6459; font-size:0.9rem; margin-top:0.3rem;">
                    Analyse quelques repas sur plusieurs jours pour voir tes tendances apparaître ici.
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        this_week = daily[-7:]
        prev_week = daily[-14:-7] if len(daily) >= 14 else []

        def avg(rows, key):
            return sum(r[key] or 0 for r in rows) / len(rows) if rows else 0

        st.subheader("Moyenne des 7 derniers jours")
        col1, col2, col3, col4 = st.columns(4)
        for col, key, label, unit in [
            (col1, "calories", "Calories", "kcal"), (col2, "proteines_g", "Protéines", "g"),
            (col3, "glucides_g", "Glucides", "g"), (col4, "lipides_g", "Lipides", "g"),
        ]:
            current_avg = avg(this_week, key)
            with col:
                macro_row(label, current_avg, key, unit)
                if prev_week:
                    prev_avg = avg(prev_week, key)
                    delta = current_avg - prev_avg
                    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
                    st.caption(f"{arrow} {abs(delta):.0f} {unit} vs semaine précédente")

        st.divider()
        st.subheader("Calories — 30 derniers jours")
        cal_by_day = {d["day"]: d["calories"] or 0 for d in daily}
        st.bar_chart(cal_by_day, color="#E8543E")

        st.subheader("Répartition des macros dans le temps")
        macro_chart_data = {
            d["day"]: [d["proteines_g"] or 0, d["glucides_g"] or 0, d["lipides_g"] or 0] for d in daily
        }
        df = pd.DataFrame(macro_chart_data.values(), index=macro_chart_data.keys(),
                           columns=["Protéines", "Glucides", "Lipides"])
        st.line_chart(df, color=["#4C7C59", "#E8A33D", "#6B5B95"])