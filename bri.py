import streamlit as st
import google.generativeai as genai
from transformers import BartTokenizer, BartForConditionalGeneration
from gtts import gTTS
import base64
import os
import re
import time
import numpy as np
from scipy.io.wavfile import write
import io
from PIL import Image
import streamlit.components.v1 as components

# --- 1. CONFIGURATION & INTERACTIVE THEME ---
st.set_page_config(
    page_title="SenseBridge", 
    page_icon="⠇⠇", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# --- SECURE API KEY RETRIEVAL ---
# Updates: Checks for 'GOOGLE_API_KEY' in secrets.toml
API_KEY = st.secrets.get("GOOGLE_API_KEY", None)

st.markdown("""
    <style>
    /* 1. INTERACTIVE "NEURAL MESH" BACKGROUND */
    @keyframes gradient-animation {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    .stApp {
        background: linear-gradient(-45deg, #020024, #090979, #1c002e, #004e92);
        background-size: 400% 400%;
        animation: gradient-animation 15s ease infinite;
        color: #e0e0e0;
    }

    /* 2. GLASSMORPHISM CARDS */
    .sentinel-card {
        background: rgba(20, 20, 20, 0.7);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        border: 1px solid rgba(255, 255, 255, 0.1);
        transition: transform 0.2s ease;
    }
    
    @media (hover: hover) {
        .sentinel-card:hover {
            transform: translateY(-5px);
            border-color: rgba(255, 255, 255, 0.3);
        }
    }

    /* 3. NEON BORDERS & TEXT */
    .border-purple { border-left: 5px solid #bd93f9; }
    .border-blue   { border-left: 5px solid #8be9fd; }
    .border-green  { border-left: 5px solid #50fa7b; }
    .border-red    { border-left: 5px solid #ff5555; }

    .card-title {
        font-family: 'Segoe UI', sans-serif;
        font-weight: 700;
        font-size: 1.1rem;
        margin-bottom: 15px;
        text-transform: uppercase;
        letter-spacing: 1px;
        display: flex;
        align-items: center;
    }
    .text-purple { color: #bd93f9; text-shadow: 0 0 10px rgba(189, 147, 249, 0.4); }
    .text-blue   { color: #8be9fd; text-shadow: 0 0 10px rgba(139, 233, 253, 0.4); }
    .text-green  { color: #50fa7b; text-shadow: 0 0 10px rgba(80, 250, 123, 0.4); }
    .text-red    { color: #ff5555; text-shadow: 0 0 10px rgba(255, 85, 85, 0.4); }

    /* 4. CONTENT STYLING */
    .raw-text-box {
        font-family: 'Consolas', monospace;
        font-size: 0.9rem;
        color: #dcdcdc;
        background-color: rgba(0,0,0,0.3);
        padding: 15px;
        border-radius: 8px;
        max-height: 200px;
        overflow-y: auto;
    }

    .braille-display {
        font-size: 2.5rem; 
        letter-spacing: 2px;
        font-weight: bold;
        color: #fff;
        text-align: center;
        margin: 15px 0;
        text-shadow: 0 0 15px rgba(255,255,255,0.5);
        word-wrap: break-word; 
    }

    /* 5. MOBILE OPTIMIZATIONS */
    @media (max-width: 768px) {
        .braille-display { font-size: 1.8rem; } 
        .card-title { font-size: 1rem; }
        .stButton button { width: 100%; } 
    }

    #MainMenu, footer, header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown("""
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="font-size: 3.5rem; margin: 0; background: linear-gradient(to right, #8be9fd, #bd93f9); -webkit-background-clip: text; -webkit-text-fill-color: transparent; filter: drop-shadow(0px 0px 10px rgba(139,233,253,0.3));">
            SenseBridge
        </h1>
        <p style="font-size: 1.1rem; color: #b0b0b0; font-style: italic;">
            Qwen-2 VL centered assistive Platform
        </p>
    </div>
""", unsafe_allow_html=True)

# Session State
if 'current_sentence_index' not in st.session_state: st.session_state.current_sentence_index = 0
if 'summary_sentences' not in st.session_state: st.session_state.summary_sentences = []

# --- 2. MAPPINGS ---
braille_map = {
    "a": "⠁", "b": "⠃", "c": "⠉", "d": "⠙", "e": "⠑", "f": "⠋", "g": "⠛", "h": "⠓", "i": "⠊", "j": "⠚",
    "k": "⠅", "l": "⠇", "m": "⠍", "n": "⠝", "o": "⠕", "p": "⠏", "q": "⠟", "r": "⠗", "s": "⠎", "t": "⠞",
    "u": "⠥", "v": "⠧", "w": "⠺", "x": "⠭", "y": "⠽", "z": "⠵", " ": " ", ".": "⠲", ",": "⠂"
}

morse_code_map = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.', 'G': '--.', 'H': '....',
    'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---', 'P': '.--.',
    'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..', '1': '.----', '2': '..---', '3': '...--', '4': '....-', '5': '.....',
    '6': '-....', '7': '--...', '8': '---..', '9': '----.', '0': '-----', ' ': '/'
}

def translate_to_braille(text):
    return "".join([braille_map.get(char.lower(), char) for char in text])

def smart_split_sentences(text):
    text = text.replace('\n', ' ')
    pattern = r'(?<=[.!?])\s+(?=[A-Z])'
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]

# --- 3. AUDIO GENERATION ---
def generate_morse_audio(text):
    text = text.upper()
    sample_rate = 44100
    freq = 600
    dot_duration = 0.08
    dash_duration = 0.24
    
    audio_buffer = []

    def add_beep(duration):
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave = 0.5 * np.sin(2 * np.pi * freq * t)
        wave[:100] *= np.linspace(0, 1, 100)
        wave[-100:] *= np.linspace(1, 0, 100)
        audio_buffer.extend(wave)
    
    def add_silence(duration):
        audio_buffer.extend(np.zeros(int(sample_rate * duration)))

    for char in text:
        if char in morse_code_map:
            code = morse_code_map[char]
            if code == '/': 
                add_silence(0.2)
            else:
                for symbol in code:
                    if symbol == '.': add_beep(dot_duration)
                    elif symbol == '-': add_beep(dash_duration)
                    add_silence(0.05)
                add_silence(0.15)
        else:
            add_silence(0.1)

    if not audio_buffer: return ""
    audio_np = np.array(audio_buffer)
    audio_int16 = np.int16(audio_np * 32767)
    virtual_file = io.BytesIO()
    write(virtual_file, sample_rate, audio_int16)
    return base64.b64encode(virtual_file.getvalue()).decode()

def text_to_tts_audio(text):
    try:
        tts = gTTS(text=text, lang='en')
        filename = "temp_tts.mp3"
        tts.save(filename)
        with open(filename, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.remove(filename)
        return b64
    except:
        return ""

# --- 4. AI MODELS ---
@st.cache_resource
def load_summarizer():
    tokenizer = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
    model = BartForConditionalGeneration.from_pretrained("facebook/bart-large-cnn")
    
    def summarizer(text):
        inputs = tokenizer([text], max_length=1024, return_tensors='pt', truncation=True)
        summary_ids = model.generate(inputs['input_ids'], max_length=200, min_length=20, do_sample=False)
        return tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    return summarizer

def extract_text_with_gemini(image):
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-flash-latest') 
        for _ in range(3):
            try:
                response = model.generate_content(["Extract text exactly.", image])
                return response.text
            except Exception as e:
                if "429" in str(e): time.sleep(4); continue
                return f"Error: {str(e)}"
        return "Error: Server busy (429)."
    except Exception as e:
        return f"Error: {str(e)}"

# --- 5. JS COMPONENTS (Responsive) ---
def render_karaoke_player(summary_text, audio_b64):
    words = summary_text.split()
    html = f"""
    <div style="
        background: rgba(30, 30, 30, 0.6); 
        backdrop-filter: blur(10px); 
        border-left: 5px solid #8be9fd; 
        padding: 20px; 
        border-radius: 16px; 
        color: white; 
        border: 1px solid rgba(255,255,255,0.1);
        width: 100%; 
        box-sizing: border-box;">
        
        <div style="color:#8be9fd; font-weight:bold; margin-bottom:15px; letter-spacing:1px; font-size:0.9rem;">
            ✦ SMART SUMMARY (INTERACTIVE)
        </div>
        
        <audio id="summaryAudio" controls style="width:100%; margin-bottom:15px; filter: invert(1) hue-rotate(180deg);">
            <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
        </audio>
        
        <div id="summaryText" style="font-family:sans-serif; color:#ccc; line-height: 1.6; max-height: 200px; overflow-y: auto;">
            {' '.join([f'<span id="w_{i}">{w}</span>' for i, w in enumerate(words)])}
        </div>
    </div>
    <script>
        var aud = document.getElementById("summaryAudio");
        var len = {len(words)};
        aud.ontimeupdate = function() {{
            if(aud.duration>0){{
                var idx = Math.floor((aud.currentTime/aud.duration)*len);
                for(var i=0;i<len;i++) {{
                    var el = document.getElementById("w_"+i);
                    if(el) {{
                         el.style.color="#ccc";
                         el.style.fontWeight="normal";
                         el.style.textShadow="none";
                    }}
                }}
                var active = document.getElementById("w_"+idx);
                if(active) {{
                    active.style.color="#f1c40f";
                    active.style.fontWeight="bold";
                    active.style.textShadow="0 0 10px rgba(241, 196, 15, 0.5)";
                    active.scrollIntoView({{behavior: "smooth", block: "center"}});
                }}
            }}
        }};
    </script>
    """
    components.html(html, height=400, scrolling=True)

def inject_navigation():
    components.html("""
    <script>
    document.addEventListener('keydown', function(e) {
        if(e.key=='ArrowRight') window.parent.document.querySelectorAll('button').forEach(b=>{if(b.innerText=='Next')b.click()});
        if(e.key=='ArrowLeft') window.parent.document.querySelectorAll('button').forEach(b=>{if(b.innerText=='Prev')b.click()});
    });
    </script>
    """, height=0)

# --- 6. MAIN UI FLOW ---

uploaded_file = st.file_uploader("📂 Upload Document", type=["jpg", "png"], label_visibility="collapsed")

if uploaded_file:
    # --- FIXED: SAFE API KEY CHECK ---
    if not API_KEY or "PASTE_YOUR" in API_KEY:
        st.error("⚠️ **API Key Missing!** Please add `GOOGLE_API_KEY` to your `.streamlit/secrets.toml` file.")
    else:
        col_img, col_act = st.columns([1, 2])
        
        with col_img:
            st.markdown('<div class="sentinel-card border-purple">', unsafe_allow_html=True)
            st.caption("SOURCE INPUT")
            img = Image.open(uploaded_file)
            st.image(img, use_column_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col_act:
            st.write(" ") 
            if st.button("🚀 Analyze & Neural Processing", type="primary", use_container_width=True):
                with st.spinner("Processing neural layers..."):
                    raw = extract_text_with_gemini(img)
                    if "Error" not in raw:
                        summ_fn = load_summarizer()
                        summ_txt = summ_fn(raw)
                        st.session_state.raw = raw
                        st.session_state.full_sum = summ_txt
                        st.session_state.sents = smart_split_sentences(summ_txt)
                        st.session_state.complete = True
                        st.rerun()
                    else:
                        st.error(raw)

if st.session_state.get('complete'):
    inject_navigation()
    
    c1, c2 = st.columns(2)

    with c1:
        # Card A: Extracted Data
        st.markdown(f"""
        <div class="sentinel-card border-purple">
            <div class="card-title text-purple">📄 Extracted Data</div>
            <div class="raw-text-box">{st.session_state.raw}</div>
        </div>""", unsafe_allow_html=True)
        
        # Card B: Interactive Summary
        tts_b64 = text_to_tts_audio(st.session_state.full_sum)
        render_karaoke_player(st.session_state.full_sum, tts_b64)

    with c2:
        total = len(st.session_state.sents)
        idx = st.session_state.current_sentence_index
        cur_sent = st.session_state.sents[idx] if total > 0 else "Processing..."
        braille_out = translate_to_braille(cur_sent)

        # Card C: Braille Reader
        st.markdown(f"""
        <div class="sentinel-card border-green">
            <div class="card-title text-green">⠇⠕⠧⠑ Braille Reader ({idx+1}/{total})</div>
            <div class="braille-display">{braille_out}</div>
            <hr style="border-color:rgba(255,255,255,0.1);">
            <div style="text-align:center; color:#ddd; font-style:italic; font-size: 1.1rem;">{cur_sent}</div>
        </div>
        """, unsafe_allow_html=True)

        # Download Button
        brf_content = braille_out + "\n\n" + cur_sent
        st.download_button(
            label="📥 Download Braille (.brf)",
            data=brf_content,
            file_name=f"braille_output_{idx+1}.brf",
            mime="text/plain",
            use_container_width=True
        )

        # Card D: Audio
        st.markdown(f"""<div class="sentinel-card border-red"><div class="card-title text-red">🔊 Audio Output</div>""", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🗣️ Voice", "📟 Beep Code"])
        with tab1:
            sent_audio = text_to_tts_audio(cur_sent)
            if sent_audio:
                st.markdown(f'<audio src="data:audio/mp3;base64,{sent_audio}" controls autoplay style="width:100%;"></audio>', unsafe_allow_html=True)
        with tab2:
            st.caption("Auditory Code (Short/Long Beeps)")
            morse_b64 = generate_morse_audio(cur_sent)
            st.markdown(f'<audio src="data:audio/wav;base64,{morse_b64}" controls style="width:100%;"></audio>', unsafe_allow_html=True)

        # Navigation
        st.write("---")
        cp, cn = st.columns(2)
        with cp: 
            if st.button("Prev", use_container_width=True): 
                if idx>0: st.session_state.current_sentence_index-=1; st.rerun()
        with cn: 
            if st.button("Next", use_container_width=True): 
                if idx<total-1: st.session_state.current_sentence_index+=1; st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
