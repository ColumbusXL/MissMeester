import os
import uuid
import pandas as pd
from io import StringIO
import requests

import streamlit as st
import chess
import chess.pgn
import chess.svg
import plotly.express as px

# --- Configuratie via omgevingsvariabelen ---
LICHESS_TOKEN = os.getenv("LICHESS_TOKEN", "lip_feHcM19F7v2Tl8PkRvcM")
ANALYSE_DEPTH = int(os.getenv("ANALYSE_DEPTH", "15"))
DELTA_SMALL = 100
DELTA_LARGE = 200
APP_NAME = "Miss Meester"
LOGO_SVG = "logo.svg"

# --- Lichess API analyse ---
def analyse_fen_via_lichess(fen: str):
    headers = {
        "Authorization": f"Bearer {LICHESS_TOKEN}",
        "Accept": "application/json"
    }
    try:
        response = requests.post(
            "https://lichess.org/api/cloud-eval",
            headers=headers,
            params={"fen": fen, "multiPv": 1, "variant": "standard"}
        )
        if response.status_code == 200:
            data = response.json()
            cp = data.get("pvs", [{}])[0].get("cp", 0)
            uci = data.get("pvs", [{}])[0].get("moves", "").split()[0] if data.get("pvs") else None
            return cp, uci
    except Exception as e:
        st.warning(f"Lichess analyse mislukt: {e}")
    return 0, None

# --- Streamlit setup ---
st.set_page_config(page_title=APP_NAME, layout="wide")

def show_logo(svg_path):
    if os.path.exists(svg_path):
        with open(svg_path, "r", encoding="utf-8") as f:
            svg = f.read()
        st.components.v1.html(svg, height=200)
show_logo(LOGO_SVG)

st.title(f"♟️ {APP_NAME}")
st.caption("door Hans Hoornstra")

st.markdown(
    "1️⃣ **Upload** je PGN-bestand (meerdere partijen)  \n"
    "2️⃣ **Wacht** tot analyse is voltooid (via Lichess API)  \n"
    "3️⃣ **Oefen** met oplossingen, grafieken en naspelen van partijen"
)

example_pgn = (
    "[Event \"Voorbeeld\"]\n"
    "[White \"Wit\"]\n"
    "[Black \"Zwart\"]\n"
    "[Result \"1-0\"]\n"
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3"
)

st.download_button("Download voorbeeld PGN", example_pgn, file_name="voorbeeld.pgn")

with st.expander("Tips & Tricks 📖"):
    st.write("- Zorg voor een geldige Lichess API token in LICHESS_TOKEN  \n- De evaluatie komt van lichess.org via cloud-eval API")

uploaded = st.file_uploader("Upload PGN-bestand", type=["pgn"])
if not uploaded:
    st.stop()

pgn_text = uploaded.getvalue().decode("utf-8")
if not pgn_text.strip():
    st.error("Leeg of ongeldig PGN-bestand.")
    st.stop()

stream = StringIO(pgn_text)
games = []
while True:
    game = chess.pgn.read_game(stream)
    if game is None:
        break
    games.append(game)

if not games:
    st.warning("Geen partijen gevonden.")
    st.stop()

progress = st.progress(0)
all_tactics = []
index_map = {}

for gi, game in enumerate(games):
    board = game.board()
    prev_eval = None
    eval_seq = []
    meta = {k: game.headers.get(k, "-") for k in ['White','Black','Event','Date']}
    moves = list(game.mainline_moves())

    for ply, move in enumerate(moves):
        board.push(move)
        fen = board.fen()
        cp, best = analyse_fen_via_lichess(fen)
        eval_seq.append(cp)

        if prev_eval is not None:
            delta = cp - prev_eval
            if abs(delta) > DELTA_SMALL:
                gain = abs(prev_eval) < DELTA_SMALL and abs(cp) > DELTA_LARGE
                loss = prev_eval > DELTA_LARGE and delta < -DELTA_LARGE
                flip = prev_eval * cp < 0 and abs(delta) > DELTA_LARGE
                if gain or loss or flip:
                    tid = str(uuid.uuid4())
                    all_tactics.append({
                        **meta,
                        "id": tid,
                        "ply": ply,
                        "fen": fen,
                        "best_move": best,
                        "delta": delta,
                        "eval_seq": eval_seq.copy(),
                        "moves": [m.uci() for m in moves]
                    })
                    index_map[tid] = len(all_tactics)-1
        prev_eval = cp
    progress.progress((gi+1)/len(games))

if not all_tactics:
    st.warning("Geen tactische momenten gevonden.")
    st.stop()

if 'i' not in st.session_state:
    st.session_state.i = 0
prev_col, _, next_col = st.columns([1,2,1])
if prev_col.button("⬅ Vorige"):
    st.session_state.i = max(0, st.session_state.i - 1)
if next_col.button("Volgende ➡"):
    st.session_state.i = min(len(all_tactics) - 1, st.session_state.i + 1)
st.progress((st.session_state.i + 1) / len(all_tactics))

sel = st.experimental_get_query_params().get("opgave", [None])[0]
if sel in index_map:
    st.session_state.i = index_map[sel]

tac = all_tactics[st.session_state.i]
st.subheader(f"Opgave {st.session_state.i+1}/{len(all_tactics)} | ID: {tac['id']}")
st.markdown(f"**Partij:** {tac['White']} vs {tac['Black']} ({tac['Event']} {tac['Date'][:4]})")
st.markdown(f"**Zetnummer:** {tac['ply']} — **Δ:** {tac['delta']}")

svg_board = chess.svg.board(chess.Board(tac['fen']), size=480)
st.image('data:image/svg+xml;utf-8,' + svg_board)

col1, col2 = st.columns(2)
if col1.button("Toon oplossing"):
    col1.info(f"Beste zet volgens engine: {tac['best_move']}")
if col2.button("Toon grafiek"):
    fig = px.line(y=tac['eval_seq'], labels={'x': 'Zet', 'y': 'Centipawns'}, title="Evaluatiegrafiek")
    fig.add_hline(y=0, line_dash="dash")
    st.plotly_chart(fig, use_container_width=True)

with st.expander("Speel de hele partij na"):
    board = chess.Board()
    for i, uci in enumerate(tac['moves']):
        move = chess.Move.from_uci(uci)
        board.push(move)
        st.image('data:image/svg+xml;utf-8,' + chess.svg.board(board=board, size=480), caption=f"Zet {i+1}: {uci}")
