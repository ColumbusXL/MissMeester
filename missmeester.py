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
DELTA_SMALL = 50
DELTA_LARGE = 100
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
            cp = data.get("pvs", [{}])[0].get("cp", None)
            uci = data.get("pvs", [{}])[0].get("moves", "").split()[0] if data.get("pvs") else None
            return cp, uci
    except Exception as e:
        st.warning(f"Lichess analyse mislukt: {e}")
    return None, None

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
    "3️⃣ **Bekijk per partij de evaluatiegrafiek en eventuele tactische momenten"
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
all_results = []

for gi, game in enumerate(games):
    with st.spinner(f"Analyseren van partij {gi+1} van {len(games)}: {game.headers.get('White', '-')} vs {game.headers.get('Black', '-')}"):
        board = game.board()
        prev_eval = None
        eval_seq = []
        meta = {k: game.headers.get(k, "-") for k in ['White','Black','Event','Date']}
        moves = list(game.mainline_moves())
        tactics = []

        for ply, move in enumerate(moves):
            board.push(move)
            fen = board.fen()
            cp, best = analyse_fen_via_lichess(fen)
            eval_seq.append(cp if cp is not None else None)

            if cp is not None and prev_eval is not None:
                delta = cp - prev_eval
                if abs(delta) > DELTA_SMALL:
                    gain = abs(prev_eval) < DELTA_SMALL and abs(cp) > DELTA_LARGE
                    loss = prev_eval > DELTA_LARGE and delta < -DELTA_LARGE
                    flip = prev_eval * cp < 0 and abs(delta) > DELTA_LARGE
                    if gain or loss or flip:
                        tactics.append({
                            "ply": ply,
                            "fen": fen,
                            "best_move": best,
                            "delta": delta
                        })
            if cp is not None:
                prev_eval = cp

        all_results.append({
            "meta": meta,
            "eval_seq": eval_seq,
            "tactics": tactics,
            "moves": [m.uci() for m in moves]
        })
        progress.progress((gi+1)/len(games))

# Interface per partij
for i, result in enumerate(all_results):
    meta = result["meta"]
    st.header(f"Partij {i+1}: {meta['White']} vs {meta['Black']} ({meta['Event']} {meta['Date'][:4]})")

    # Evaluatiegrafiek
    valid_scores = [v if v is not None else None for v in result['eval_seq']]
    fig = px.line(y=valid_scores, labels={'x': 'Zet', 'y': 'Centipawns'}, title="Evaluatieverloop")
    fig.add_hline(y=0, line_dash="dash")

    # Markeer tactische momenten als stippen
    if result['tactics']:
        tactic_indices = [t['ply'] for t in result['tactics']]
        tactic_values = [result['eval_seq'][t['ply']] for t in result['tactics']]
        fig.add_scatter(x=tactic_indices, y=tactic_values, mode='markers', marker=dict(color='red', size=8), name='Tactisch moment')

    st.plotly_chart(fig, use_container_width=True)

    # Tactische momenten
    if result['tactics']:
        for t in result['tactics']:
            st.markdown(f"**Zetnummer:** {t['ply']} — **Δ:** {t['delta']}")
            st.image('data:image/svg+xml;utf-8,' + chess.svg.board(chess.Board(t['fen']), size=400))
            st.info(f"Beste zet volgens engine: {t['best_move']}")
    else:
        st.success("Geen duidelijke tactische momenten gedetecteerd.")

    with st.expander("Speel deze partij na"):
        board = chess.Board()
        for j, uci in enumerate(result['moves']):
            try:
                move = chess.Move.from_uci(uci)
                if move in board.legal_moves:
                    board.push(move)
                else:
                    st.warning(f"Ongeldige zet: {uci}")
                    break
                svg = chess.svg.board(board=board, size=480)
                st.image('data:image/svg+xml;utf-8,' + svg, caption=f"Zet {j+1}: {uci}")
            except Exception as e:
                st.error(f"Fout bij zetten naspelen: {e}")
