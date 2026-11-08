"""Interface web (Streamlit) du classifieur EuroSAT.

L'interface passe par la passerelle, exactement comme un client externe :
elle est donc soumise à l'authentification et au routage canary.
"""
from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://gateway/api").rstrip("/")

DESCRIPTIONS = {
    "AnnualCrop": "Cultures annuelles", "Forest": "Forêt",
    "HerbaceousVegetation": "Végétation herbacée", "Highway": "Autoroute / route",
    "Industrial": "Zone industrielle", "Pasture": "Pâturage",
    "PermanentCrop": "Cultures permanentes (vergers, vignes)", "Residential": "Zone résidentielle",
    "River": "Rivière", "SeaLake": "Mer / lac",
}

st.set_page_config(page_title="EuroSAT — Occupation des sols", page_icon="🛰️", layout="wide")
st.title("🛰️ Classification d'occupation des sols (Sentinel-2)")

with st.sidebar:
    st.header("Authentification")
    api_key = st.text_input("Clé d'API", type="password", value=st.session_state.get("api_key", ""))
    st.session_state["api_key"] = api_key
    route = st.radio("Routage", ["Automatique", "Forcer stable", "Forcer canary"],
                     help="Permet de comparer le modèle champion et le challenger.")
    st.caption(f"API : `{API_URL}`")


def headers() -> dict:
    h = {"X-API-Key": api_key}
    if route == "Forcer stable":
        h["X-Canary"] = "never"
    elif route == "Forcer canary":
        h["X-Canary"] = "always"
    return h


def call(method: str, path: str, **kw):
    try:
        r = requests.request(method, f"{API_URL}{path}", headers=headers(), timeout=30, **kw)
    except requests.RequestException as exc:
        st.error(f"API injoignable : {exc}")
        return None, None
    if r.status_code == 401:
        st.error("Clé d'API manquante ou invalide.")
    elif r.status_code == 429:
        st.warning("Quota de requêtes dépassé, réessayez dans une minute.")
    elif not r.ok:
        st.error(f"Erreur {r.status_code} : {r.text[:300]}")
    return r, (r.json() if r.ok else None)


if not api_key:
    st.info("Renseignez votre clé d'API dans le panneau de gauche pour commencer.")
    st.stop()

tab_pred, tab_usage, tab_monitor = st.tabs(["Prédiction", "Mon usage", "Monitoring modèle"])

with tab_pred:
    files = st.file_uploader("Images satellites (RGB, idéalement 64×64 px)", type=["png", "jpg", "jpeg", "tif", "tiff"],
                             accept_multiple_files=True)
    if files and st.button("Classifier", type="primary"):
        for f in files:
            resp, data = call("POST", "/v1/predict", files={"file": (f.name, f.getvalue(), f.type)})
            if not data:
                continue
            c1, c2 = st.columns([1, 2])
            with c1:
                st.image(f.getvalue(), caption=f.name, use_container_width=True)
            with c2:
                st.subheader(f"{data['label']} — {DESCRIPTIONS.get(data['label'], '')}")
                st.metric("Confiance", f"{100 * data['confidence']:.1f} %")
                probs = pd.Series(data["probabilities"]).sort_values(ascending=True)
                st.bar_chart(probs, horizontal=True)
                m = data["model"]
                st.caption(f"Servi par **{m['track']}** · modèle v{m['version']} ({m['alias']}, {m['variant']}) "
                           f"· {data['latency_ms']:.1f} ms")
            st.divider()

with tab_usage:
    _, usage = call("GET", "/v1/me/usage")
    if usage:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Requêtes", usage["total_requests"])
        c2.metric("Images classées", usage["total_images"])
        c3.metric("Erreurs", usage["errors"])
        c4.metric("Latence moyenne", f"{usage['avg_latency_ms'] or 0:.1f} ms")
        st.caption(f"Dernière requête : {usage['last_request_at'] or '—'}")

with tab_monitor:
    _, model = call("GET", "/v1/model")
    if model:
        st.write(f"Modèle **{model['name']}** v{model['version']} — alias `{model['alias']}`, "
                 f"variante `{model['variant']}`, piste `{model['track']}`")
    _, drift = call("GET", "/v1/drift")
    if drift:
        if not drift["ready"]:
            st.info(f"Fenêtre insuffisante pour tester le drift ({drift['n_current']} échantillons).")
        else:
            (st.error if drift["drift_detected"] else st.success)(
                "Data drift détecté" if drift["drift_detected"] else "Pas de drift détecté"
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("Composantes en drift", f"{100 * drift['share_drifted_components']:.0f} %")
            c2.metric("PSI prédictions", f"{drift['prediction_psi']:.3f}")
            c3.metric("Confiance moyenne", f"{drift['mean_confidence']:.2f}")
            st.bar_chart(pd.Series(drift["p_values"], name="p-value KS",
                                   index=[f"PC{i + 1}" for i in range(len(drift["p_values"]))]))
            st.caption(f"Seuil de Bonferroni : {drift['threshold']:.4f} · fenêtre de {drift['n_current']} images")
