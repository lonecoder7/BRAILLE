import streamlit as st
import google.generativeai as genai
from gtts import gTTS
import base64
import os
import re
import time
import io
from PIL import Image
import streamlit.components.v1 as components

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="SenseBridge", 
    page_icon="🧠", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# --- SECURE API KEY ---
API_KEY = st.secrets.get("GOOGLE_API_KEY", None)

# --- SESSION STATE INITIALIZATION ---
if 'mode' not in st.session_state: st.session_state.mode = None 
if 'current_sentence_index' not in st.session_state: st.session_state.current_sentence_index = 0
if 'summary_sentences' not in st.session_state: st.session_state.summary_sentences = []
if 'raw_text' not in st.session_state: st.session_state.raw_text = ""
if 'full_summary' not in st.session_state: st.session_state.full_summary = ""
if 'processing_complete' not in st.session_state: st.session_state.processing_complete = False

# --- 2. CSS GENERATORS ---

def inject_visual_mode_css():
    st.markdown("""
    <style>
    /* DEEP NEURAL THEME */
    .stApp {
        background: linear-gradient(-45deg, #020024, #090979, #1c002e, #004e92);
        background-size: 400% 400%;
        color: #e0e0e0;
    }
    .sentinel-card {
        background: rgba(20, 20, 20, 0.7);
        backdrop-filter: blur(12px);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    .card-title { font-weight: bold; font-size: 1.1rem; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }
    .braille-display {
        font-size: 2.5rem; letter-spacing: 3px; font-weight: bold; color: #fff;
        text-align: center; margin: 15px 0; text-shadow: 0 0 10px rgba(255,255,255,0.5);
    }
    #MainMenu, footer, header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

def inject_reading_mode_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@400;600&display=swap');
    .stApp {
        background-color: #f7f3e9;
        color: #1a1a1a;
        font-family: 'Lexend', sans-serif !important;
    }
    .reading-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 30px;
        margin-bottom: 25px;
        box-shadow: 4px 4px 0px #2c3e50;
        border: 2px solid #2c3e50;
        color: #000;
    }
    h1, h2, h3 { font-family: 'Lexend', sans-serif !important; color: #004085; }
    p, li, div { font-size: 1.2rem !important; line-height: 1.8 !important; }
    #MainMenu, footer, header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 3. HELPER FUNCTIONS ---

def clean_text_for_audio(text):
    """
    Removes Markdown symbols so TTS reads smoothly.
    Converts '* Item' to 'Item' and removes headers/bolding chars.
    """
    # Remove asterisks, hashes, dashes used for bullets
    clean = re.sub(r'[*#•-]', ' ', text)
    # Remove multiple spaces
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def extract_text_with_gemini(image, mode):
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-flash-latest') 
        
        if mode == 'reading':
            prompt = """
            You are an assistive reading assistant.
            1. Extract the text from the image.
            2. REWRITE the content to be dyslexia-friendly:
               - Use short, simple sentences.
               - Use bullet points for key information.
               - Avoid complex jargon.
            
            Output Format:
            [EXTRACTED]
            (The raw text)
            [SUMMARY]
            (The simplified bullet-point version)
            """
        else:
            prompt = """
            You are an assistive reader for the visually impaired.
            1. Extract the text exactly.
            2. Provide a concise summary suitable for Text-to-Speech.
            
            Output Format:
            [EXTRACTED]
            (The raw text)
            [SUMMARY]
            (The audio-ready summary)
            """

        for _ in range(3):
            try:
                response = model.generate_content([prompt, image])
                text = response.text
                if "[EXTRACTED]" in text and "[SUMMARY]" in text:
                    parts = text.split("[SUMMARY]")
                    return parts[0].replace("[EXTRACTED]", "").strip(), parts[1].strip()
                return text, text 
            except Exception as e:
                time.sleep(2)
                continue
        return "Error: Server busy.", ""
    except Exception as e:
        return f"Error: {str(e)}", ""

braille_map = {
    "a": "⠁", "b": "⠃", "c": "⠉", "d": "⠙", "e": "⠑", "f": "⠋", "g": "⠛", "h": "⠓", "i": "⠊", "j": "⠚",
    "k": "⠅", "l": "⠇", "m": "⠍", "n": "⠝", "o": "⠕", "p": "⠏", "q": "⠟", "r": "⠗", "s": "⠎", "t": "⠞",
    "u": "⠥", "v": "⠧", "w": "⠺", "x": "⠭", "y": "⠽", "z": "⠵", " ": " ", ".": "⠲", ",": "⠂"
}
def translate_to_braille(text):
    return "".join([braille_map.get(char.lower(), char) for char in text])

def text_to_tts_audio(text):
    try:
        # CLEAN THE TEXT BEFORE SENDING TO TTS
        safe_text = clean_text_for_audio(text)
        if not safe_text: return ""
        
        tts = gTTS(text=safe_text, lang='en')
        filename = "temp_tts.mp3"
        tts.save(filename)
        with open(filename, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return b64
    except: return ""

# --- 4. JS COMPONENTS (FIXED COMMANDS) ---

def inject_gesture_interface():
    """
    Visual Mode Interface with Voice & Gestures.
    Fixed: 'Read', 'Next', 'Prev' commands.
    """
    js_code = """
    <div id="gesture-layer" style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 9999; background: rgba(0,0,0,0.01); touch-action: none;"></div>
    <script>
    const layer = document.getElementById('gesture-layer');
    let lastTap = 0; let touchStartY = 0;
    
    // Voice Command Engine
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true; 
        recognition.lang = 'en-US';
        
        recognition.onresult = function(e) {
            const cmd = e.results[e.results.length - 1][0].transcript.trim().toLowerCase();
            console.log("Command received:", cmd);
            
            if (cmd.includes('scan') || cmd.includes('analyze')) triggerAction('upload');
            
            // FIXED: 'Read' or 'Start' triggers the audio player
            if (cmd.includes('read') || cmd.includes('start') || cmd.includes('play')) triggerAction('play');
            
            if (cmd.includes('stop') || cmd.includes('pause')) triggerAction('pause');
            
            // FIXED: 'Next' and 'Previous' looking for buttons
            if (cmd.includes('next') || cmd.includes('forward')) triggerAction('next');
            if (cmd.includes('previous') || cmd.includes('back')) triggerAction('prev');
        };
        try { recognition.start(); } catch(e) {}
    }

    // Gestures
    layer.addEventListener('click', function(e) {
        const now = new Date().getTime();
        if (now - lastTap < 500 && now - lastTap > 0) { triggerAction('pause'); e.preventDefault(); }
        lastTap = now;
    });
    layer.addEventListener('touchstart', e => { touchStartY = e.changedTouches[0].screenY; });
    layer.addEventListener('touchend', e => {
        if (e.changedTouches[0].screenY < touchStartY - 50) triggerAction('upload');
        if (e.changedTouches[0].screenY > touchStartY + 50) parent.window.location.reload();
    });

    function triggerAction(action) {
        const btns = window.parent.document.querySelectorAll('button');
        const audio = window.parent.document.querySelector('audio');
        
        // Button Logic
        if (action === 'upload') btns.forEach(b => { if(b.innerText.includes('Analyze')) b.click(); });
        
        if (action === 'next') btns.forEach(b => { if(b.innerText.toLowerCase().includes('next')) b.click(); });
        if (action === 'prev') btns.forEach(b => { if(b.innerText.toLowerCase().includes('prev')) b.click(); });

        // Audio Logic
        if (action === 'play' && audio) audio.play();
        if (action === 'pause' && audio) audio.paused ? audio.play() : audio.pause();
        
        if (navigator.vibrate) navigator.vibrate(50);
    }
    </script>
    """
    components.html(js_code, height=0, width=0)

def render_karaoke_player(summary_text, audio_b64, mode='visual'):
    # We clean text for display if in reading mode to match audio
    display_text = summary_text.replace("*", "").replace("#", "")
    words = display_text.split()
    
    highlight_color = "#f1c40f" if mode == 'visual' else "#ffc107"
    text_color = "#ccc" if mode == 'visual' else "#000"
    
    html = f"""
    <div style="padding: 20px; border-radius: 12px; border: 2px solid {highlight_color}; background: {'rgba(30,30,30,0.6)' if mode=='visual' else '#fff'};">
        <audio id="summaryAudio" controls style="width:100%; margin-bottom:15px; {'filter: invert(1);' if mode=='visual' else ''}">
            <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
        </audio>
        <div id="summaryText" style="font-family: {'sans-serif' if mode=='visual' else 'Lexend, sans-serif'}; font-size: {'1rem' if mode=='visual' else '1.3rem'}; color: {text_color}; line-height: 1.8;">
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
                    var word = document.getElementById("w_"+i);
                    if(word) word.style.backgroundColor = "transparent";
                }}
                var el = document.getElementById("w_"+idx);
                if(el) el.style.backgroundColor = "{highlight_color}";
            }}
        }};
    </script>
    """
    components.html(html, height=400, scrolling=True)

# --- 5. INTERFACES ---

def show_mode_selection():
    st.markdown("""
    <style>
    .mode-btn { width: 100%; padding: 40px; font-size: 24px; border-radius: 15px; cursor: pointer; border: none; margin-bottom: 20px; transition: transform 0.2s;}
    .mode-btn:hover { transform: scale(1.02); }
    </style>
    <div style="text-align: center; padding-top: 50px;">
        <h1 style="font-size: 4rem;">SenseBridge</h1>
        <p style="font-size: 1.5rem; margin-bottom: 50px;">Select Your Assistance Mode</p>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("👁️ Visual Assist Mode\n(Audio, Braille, Haptics)", use_container_width=True):
            st.session_state.mode = 'visual'
            st.rerun()
    with c2:
        if st.button("📖 Reading Assist Mode\n(Dyslexia Friendly, Simplified)", use_container_width=True):
            st.session_state.mode = 'reading'
            st.rerun()

def show_visual_interface():
    inject_visual_mode_css()
    inject_gesture_interface()
    
    st.markdown('<div style="text-align: center; margin-bottom: 20px;"><h2>👁️ Visual Assist Active</h2></div>', unsafe_allow_html=True)
    
    if st.button("⬅️ Change Mode"):
        st.session_state.mode = None
        st.rerun()

    uploaded_file = st.file_uploader("📂 Upload Document", type=["jpg", "png"], label_visibility="collapsed")
    
    if uploaded_file and not st.session_state.processing_complete:
        if st.button("🚀 Analyze Document", type="primary", use_container_width=True):
            with st.spinner("Processing..."):
                raw, summ = extract_text_with_gemini(Image.open(uploaded_file), 'visual')
                st.session_state.raw_text = raw
                st.session_state.full_summary = summ
                st.session_state.summary_sentences = re.split(r'(?<=[.!?])\s+', summ)
                st.session_state.processing_complete = True
                st.rerun()

    if st.session_state.processing_complete:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div class="sentinel-card"><div class="card-title" style="color:#bd93f9">📄 Extracted Text</div><div style="color:#ccc">{st.session_state.raw_text[:500]}...</div></div>', unsafe_allow_html=True)
            tts = text_to_tts_audio(st.session_state.full_summary)
            render_karaoke_player(st.session_state.full_summary, tts, 'visual')
        
        with c2:
            idx = st.session_state.current_sentence_index
            sent = st.session_state.summary_sentences[idx] if st.session_state.summary_sentences else ""
            braille = translate_to_braille(sent)
            
            st.markdown(f"""
            <div class="sentinel-card" style="border-left: 5px solid #50fa7b;">
                <div class="card-title" style="color:#50fa7b">⠇⠕⠧⠑ Braille Reader</div>
                <div class="braille-display">{braille}</div>
                <div style="text-align:center; color:#ddd;">{sent}</div>
            </div>
            """, unsafe_allow_html=True)
            
            c_p, c_n = st.columns(2)
            # IMPORTANT: Text must match JS logic 'Prev' and 'Next'
            if c_p.button("⬅️ Prev"): 
                if idx > 0: st.session_state.current_sentence_index -= 1; st.rerun()
            if c_n.button("Next ➡️"): 
                if idx < len(st.session_state.summary_sentences)-1: st.session_state.current_sentence_index += 1; st.rerun()

def show_reading_interface():
    inject_reading_mode_css()
    
    st.markdown('<div style="text-align: center; margin-bottom: 20px; color: #004085;"><h2>📖 Reading Assist Active</h2></div>', unsafe_allow_html=True)
    
    if st.button("⬅️ Change Mode"):
        st.session_state.mode = None
        st.rerun()

    uploaded_file = st.file_uploader("📂 Upload Document", type=["jpg", "png"])
    
    if uploaded_file and not st.session_state.processing_complete:
        if st.button("✨ Simplify Text", type="primary", use_container_width=True):
            with st.spinner("Making text easier to read..."):
                raw, summ = extract_text_with_gemini(Image.open(uploaded_file), 'reading')
                st.session_state.raw_text = raw
                st.session_state.full_summary = summ
                st.session_state.processing_complete = True
                st.rerun()

    if st.session_state.processing_complete:
        st.markdown(f"""
        <div class="reading-card">
            <h3>🔹 Simplified Summary</h3>
            <div style="font-size: 1.3rem; line-height: 2;">
                {st.session_state.full_summary.replace("•", "<br>•")}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### 🔊 Listen Along")
        tts = text_to_tts_audio(st.session_state.full_summary)
        render_karaoke_player(st.session_state.full_summary, tts, 'reading')
        
        with st.expander("View Original Raw Text"):
            st.write(st.session_state.raw_text)

# --- 6. MAIN CONTROLLER ---

if API_KEY is None or "PASTE_YOUR" in API_KEY:
    st.error("⚠️ API Key Missing. Check secrets.toml")
else:
    if st.session_state.mode is None:
        show_mode_selection()
    elif st.session_state.mode == 'visual':
        show_visual_interface()
    elif st.session_state.mode == 'reading':
        show_reading_interface()
