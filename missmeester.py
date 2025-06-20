import os
import uuid
import pandas as pd
from io import StringIO

import streamlit as st
import chess
import chess.engine
import chess.pgn
import chess.svg
import plotly.express as px

# --- Configuratie via omgevingsvariabelen ---
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "/usr/local/bin/stockfish")
ANALYSE_DEPTH = int(os.getenv("ANALYSE_DEPTH", "15"))
DELTA_SMALL = 100
DELTA_LARGE = 200
APP_NAME = "Miss Meester"
LOGO_SVG = "logo.svg"

# --- Streamlit pagina setup ---
st.set_page_config(page_title=APP_NAME, layout="wide")

# Toon logo als SVG indien aanwezig
def show_logo(svg_path):
    if os.path.exists(svg_path):
        with open(svg_path, "r", encoding="utf-8") as f:
            svg = f.read()
        st.components.v1.html(svg, height=200)
show_logo(LOGO_SVG)

# Titel en subtitel
st.title(f"♟️ {APP_NAME}")
st.caption("door Hans Hoornstra")

# Workflow-stappen voor de gebruiker
st.markdown(
    "1️⃣ **Upload** je PGN-bestand (meerdere partijen)  \n"
    "2️⃣ **Wacht** tot analyse is voltooid (voortgangsbalk)  \n"
    "3️⃣ **Oefen** met oplossingen, evaluatiegrafieken én naspelen van partijen"
)

# Voorbeeld PGN
example_pgn = (
    "[Event \"Voorbeeld\"]\n"
    "[White \"Wit\"]\n"
    "[Black \"Zwart\"]\n"
    "[Result \"1-0\"]\n"
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3"
)
st.download_button(
    label="Download voorbeeld PGN",
    data=example_pgn,
    file_name="voorbeeld.pgn",
    mime="text/plain",
    help="Gebruik dit voorbeeld om de app meteen te testen"
)

# Tips & Tricks
with st.expander("Tips & Tricks 📖", expanded=False):
    st.write(
        "- Stel `STOCKFISH_PATH` en `ANALYSE_DEPTH` in via omgevingsvariabelen.  \n"
        "- Hogere `ANALYSE_DEPTH` = nauwkeuriger, maar trager.  \n"
        "- Navigeer via knoppen of direct met URL: `?opgave=<ID>`.  \n"
        "- Exporteer opgaven naar CSV voor later gebruik."
    )

# Engine resource laden (cached)
@st.cache_resource
def init_engine(path):
    try:
        return chess.engine.SimpleEngine.popen_uci(path)
    except Exception as e:
        st.error(f"Kan Stockfish niet laden: {e}")
        st.stop()

engine = init_engine(STOCKFISH_PATH)

# PGN inlezen en parsen
uploaded = st.file_uploader(
    label="Upload PGN-bestand (batch)",
    type=["pgn"],
    help="Ondersteunt meerdere partijen in één bestand"
)
if not uploaded:
    st.stop()

pgn_text = uploaded.getvalue().decode('utf-8', errors='ignore')
if not pgn_text.strip():
    st.error("Leeg of ongeldig PGN-bestand.")
    st.stop()

games = []
stream = StringIO(pgn_text)
while True:
    game = chess.pgn.read_game(stream)
    if game is None:
        break
    games.append(game)

if not games:
    st.error("Geen partijen gevonden in het PGN-bestand.")
    st.stop()

# Analyse met voortgangsbalk
progress = st.progress(0)
all_tactics = []
index_map = {}

for gi, game in enumerate(games, start=1):
    board = game.board()
    prev_eval = None
    eval_seq = []
    meta = {k: game.headers.get(k, "-") for k in ['White', 'Black', 'Event', 'Date']}
    game_moves = list(game.mainline_moves())
    
    for ply, mv in enumerate(game_moves):
        board.push(mv)
        try:
            res = engine.analyse(board, chess.engine.Limit(depth=ANALYSE_DEPTH))
            score = res['score'].relative.score(mate_score=True) or 0
        except Exception:
            score = prev_eval if prev_eval is not None else 0
        eval_seq.append(score)

        if prev_eval is not None:
            delta = score - prev_eval
            if abs(delta) > DELTA_SMALL:
                gain = abs(prev_eval) < DELTA_SMALL and abs(score) > DELTA_LARGE
                loss = prev_eval > DELTA_LARGE and delta < -DELTA_LARGE
                flip = prev_eval * score < 0 and abs(delta) > DELTA_LARGE

                if gain or loss or flip:
                    tid = str(uuid.uuid4())
                    tactic = {
                        **meta,
                        'id': tid,
                        'ply': ply,
                        'fen': board.fen(),
                        'best_move': res.get('pv', [None])[0],
                        'delta': delta,
                        'eval_seq': eval_seq.copy(),
                        'moves': [m.uci() for m in game_moves]
                    }
                    index_map[tid] = len(all_tactics)
                    all_tactics.append(tactic)
        prev_eval = score
    progress.progress(gi / len(games))

engine.quit()

# Exporteer opgaven naar CSV
if all_tactics:
    df = pd.DataFrame(all_tactics)
    csv_out = df[['id', 'White', 'Black', 'Event', 'Date', 'ply', 'delta']].to_csv(index=False)
    st.download_button(
        label="Exporteer opgaven naar CSV",
        data=csv_out,
        file_name=f"{APP_NAME}_opgaven.csv",
        mime="text/csv",
        help="Download voor later gebruik"
    )
else:
    st.warning("Geen tactische momenten gevonden.")

# Navigatie tussen opgaven
if all_tactics:
    if 'i' not in st.session_state:
        st.session_state.i = 0
    prev_col, _, next_col = st.columns([1, 2, 1])
    if prev_col.button('⬅ Vorige', help='Vorige opgave'):
        st.session_state.i = max(0, st.session_state.i - 1)
    if next_col.button('Volgende ➡', help='Volgende opgave'):
        st.session_state.i = min(len(all_tactics) - 1, st.session_state.i + 1)
    st.progress((st.session_state.i + 1) / len(all_tactics))

    sel = st.experimental_get_query_params().get('opgave', [None])[0]
    if sel in index_map:
        st.session_state.i = index_map[sel]

    tac = all_tactics[st.session_state.i]
    st.subheader(f"Opgave {st.session_state.i + 1}/{len(all_tactics)} | ID: {tac['id']}")
    st.markdown(f"**Partij:** {tac['White']} vs {tac['Black']} ({tac['Event']} {tac['Date'][:4]})")
    st.markdown(f"**Zetnummer:** {tac['ply']} — **Δ:** {tac['delta']}")

    svg_board = chess.svg.board(chess.Board(tac['fen']), size=480)
    st.image('data:image/svg+xml;utf-8,' + svg_board)

    sc1, sc2 = st.columns(2)
    if sc1.button('Toon oplossing', key=tac['id'], help='Toon beste zet'):
        sc1.info(f"Beste zet: {tac['best_move']}")
    if sc2.button('Toon grafiek', key=tac['id'] + '_g', help='Bekijk evaluatiegrafiek'):
        fig = px.line(
            y=tac['eval_seq'],
            labels={'x': 'Zet', 'y': 'Centipawns'},
            title=f"Evaluatie: {tac['White']} vs {tac['Black']}"
        )
        fig.add_hline(y=0, line_dash='dash', line_color='gray')
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Speel de hele partij na"):
        board = chess.Board()
        for i, uci in enumerate(tac['moves']):
            move = chess.Move.from_uci(uci)
            board.push(move)
            st.image('data:image/svg+xml;utf-8,' + chess.svg.board(board=board, size=480), caption=f"Zet {i+1}: {uci}")

    st.info("Gebruik de navigatieknoppen of '?opgave=<ID>' voor directe toegang.")

# --- Einde programma ---
