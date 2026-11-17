import json, time, uuid
import streamlit as st
from pypdf import PdfReader
from google import genai
from google.genai import types
from groq import Groq

st.set_page_config(page_title="NeuroChat AI Studio", page_icon="✨", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
#MainMenu, footer { visibility: hidden; }
header { background: transparent !important; }
.stApp { background: radial-gradient(circle at top right, #161b2e 0%, #0b0e17 50%, #07090f 100%); color: #f1f5f9; }
section[data-testid="stSidebar"] { background-color: #0d111c !important; border-right: 1px solid rgba(255,255,255,0.08); }
.hero-title { font-size: 2rem; font-weight: 700; background: linear-gradient(90deg, #60a5fa, #a78bfa, #f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.status-bar { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 18px 0; }
.status-pill { background: rgba(30,41,59,0.75); border: 1px solid rgba(148,163,184,0.2); padding: 4px 12px; border-radius: 999px; font-size: 0.78rem; color: #cbd5e1; }
.status-pill b { color: #38bdf8; }
div[data-testid="stChatMessage"] { background: rgba(17,24,39,0.65); border: 1px solid rgba(255,255,255,0.07); border-radius: 16px; padding: 1rem; margin-bottom: 0.7rem; }
.metrics-badge { display: inline-block; margin-top: 8px; padding: 4px 10px; border-radius: 8px; background: rgba(15,23,42,0.85); border: 1px solid rgba(99,102,241,0.3); font-size: 0.75rem; color: #94a3b8; }
</style>
""", unsafe_allow_html=True)

# Safe API Key Loading via Streamlit Secrets (or Sidebar fallback)
GEMINI_KEY = st.secrets.get("GEMINI_KEY", "")
GROQ_KEY = st.secrets.get("GROQ_KEY", "")

if "chat_sessions" not in st.session_state:
    fid = str(uuid.uuid4())[:8]
    st.session_state.chat_sessions = {fid: {"title": "New Conversation", "messages": [], "summary": ""}}
    st.session_state.current_session_id = fid
if "queued_prompt" not in st.session_state:
    st.session_state.queued_prompt = None

curr_id = st.session_state.current_session_id
curr_session = st.session_state.chat_sessions[curr_id]

with st.sidebar:
    st.markdown("### ✨ NeuroChat Studio")
    if st.button("＋ New Chat", type="primary", use_container_width=True):
        nid = str(uuid.uuid4())[:8]
        st.session_state.chat_sessions[nid] = {"title": "New Conversation", "messages": [], "summary": ""}
        st.session_state.current_session_id = nid
        st.rerun()

    st.markdown("##### 🕒 Recent Chats")
    for sid, sdata in reversed(list(st.session_state.chat_sessions.items())):
        prefix = "🔹" if sid == curr_id else "💬"
        if st.button(f"{prefix} {sdata['title']}", key=f"s_{sid}", use_container_width=True):
            st.session_state.current_session_id = sid
            st.rerun()

    st.divider()
    with st.expander("🤖 Model Engine (Gemini & Groq)", expanded=True):
        model_choice = st.selectbox("Model", [
            "Gemini | gemini-3.5-flash-lite",
            "Gemini | gemini-3.8-flash",
            "Groq | openai/gpt-oss-120b",
            "Groq | qwen/qwen3.8-27b",
        ], label_visibility="collapsed")
        provider, model_name = model_choice.split(" | ")

    with st.expander("🔑 API Keys (Optional Override)", expanded=False):
        GEMINI_KEY = st.text_input("Gemini API Key", value=GEMINI_KEY, type="password")
        GROQ_KEY = st.text_input("Groq API Key", value=GROQ_KEY, type="password")

    with st.expander("🧠 Context & Grounding (Day 2)", expanded=False):
        use_personal_ctx = st.toggle("Personal Profile", value=True)
        user_name = st.text_input("Name", value="S. Jeganathar")
        user_role = st.text_input("Role", value="Applied AI Instructor")
        personal_notes = st.text_area("Notes", value="Teaching Python, Streamlit, Context & Prompt Engineering.", height=65)
        uploaded_doc = st.file_uploader("Upload PDF / TXT", type=["pdf", "txt"])
        doc_text = ""
        if uploaded_doc:
            if uploaded_doc.name.endswith(".pdf"):
                doc_text = "\n".join(p.extract_text() or "" for p in PdfReader(uploaded_doc).pages)
            else:
                doc_text = uploaded_doc.read().decode("utf-8")
            st.success(f"Loaded {len(doc_text):,} chars")

    with st.expander("✍️ Prompt Studio (Day 3)", expanded=False):
        bot_role = st.selectbox("Persona", ["Default Helpful Assistant", "Senior AI & Python Architect", "Strict Technical Interviewer", "Beginner-Friendly Educator", "Data Analyst & JSON Extractor"])
        prompt_technique = st.selectbox("Technique", ["Zero-Shot (Direct)", "One-Shot (1 Example)", "Few-Shot (Multi-Example)", "Constraint-Based (Strict Rules)"])
        output_format = st.selectbox("Format", ["Standard Markdown", "Markdown Table", "Strict JSON"])
        constraint_rule = st.text_input("Constraint", value="Keep explanations concise and under 150 words.")

    with st.expander("⚙️ Parameters & Memory", expanded=False):
        temperature = st.slider("Temperature", 0.0, 2.0, 0.5, 0.1)
        max_tokens = st.slider("Max Tokens", 50, 2048, 700, 50)
        top_p = st.slider("Top-P", 0.1, 1.0, 0.95, 0.05)
        history_window = st.slider("Memory Window", 2, 20, 8, 2)

    with st.expander("📊 Metrics & Revise Chat", expanded=False):
        show_latency = st.checkbox("Latency (s)", value=True)
        show_speed = st.checkbox("Speed (tok/s)", value=True)
        show_tokens = st.checkbox("Tokens (In/Out)", value=True)
        show_cost = st.checkbox("Cost ($)", value=True)
        if st.button("✨ Revise & Summarize Chat", use_container_width=True):
            if len(curr_session["messages"]) >= 2:
                convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in curr_session["messages"])
                rp = f"Summarize and revise the key topics and Q&A from this chat in 5 bullet points:\n\n{convo}"
                try:
                    if provider == "Gemini":
                        g_client = genai.Client(api_key=GEMINI_KEY.strip())
                        curr_session["summary"] = g_client.models.generate_content(model=model_name, contents=rp).text
                    else:
                        q_client = Groq(api_key=GROQ_KEY.strip())
                        curr_session["summary"] = q_client.chat.completions.create(model=model_name, messages=[{"role": "user", "content": rp}]).choices[0].message.content
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Chat at least 1 turn first!")
        if curr_session["summary"]:
            st.info(curr_session["summary"])
        if curr_session["messages"]:
            st.download_button("⬇️ Export JSON", data=json.dumps(curr_session["messages"], indent=2), file_name=f"chat_{curr_id}.json", mime="application/json", use_container_width=True)
        if st.button("🗑️ Delete Chat", use_container_width=True):
            if len(st.session_state.chat_sessions) > 1:
                del st.session_state.chat_sessions[curr_id]
                st.session_state.current_session_id = list(st.session_state.chat_sessions.keys())[-1]
            else:
                curr_session.update({"title": "New Conversation", "messages": [], "summary": ""})
            st.rerun()

st.markdown('<div class="hero-title">✨ NeuroChat AI Studio</div>', unsafe_allow_html=True)
st.markdown(f"""
<div class="status-bar">
    <span class="status-pill">🤖 Engine: <b>{provider} · {model_name}</b></span>
    <span class="status-pill">🎭 Role: <b>{bot_role}</b></span>
    <span class="status-pill">✍️ Technique: <b>{prompt_technique}</b></span>
    <span class="status-pill">📐 Format: <b>{output_format}</b></span>
    <span class="status-pill">🧠 Context: <b>{'ON' if use_personal_ctx else 'OFF'}</b></span>
</div>
""", unsafe_allow_html=True)

if not curr_session["messages"]:
    st.markdown("#### 💡 Quick Start Prompts")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🧠 Suggest 3 AI project ideas for my profile", use_container_width=True):
            st.session_state.queued_prompt = "Suggest 3 practical AI project ideas tailored to my profile."
            st.rerun()
        if st.button("📊 Compare Prompt vs Context Engineering", use_container_width=True):
            st.session_state.queued_prompt = "Compare Prompt Engineering vs Context Engineering across 4 key points."
            st.rerun()
    with c2:
        if st.button("⚡ Explain RAG architecture with an example", use_container_width=True):
            st.session_state.queued_prompt = "Explain Retrieval-Augmented Generation (RAG) with a real-world example."
            st.rerun()
        if st.button("🧩 Create a 3-day LLM API study roadmap", use_container_width=True):
            st.session_state.queued_prompt = "Create a 3-day study roadmap for mastering LLM APIs and parameters."
            st.rerun()

for msg in curr_session["messages"]:
    with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "✨"):
        if msg.get("format") == "Strict JSON":
            st.code(msg["content"], language="json")
        else:
            st.markdown(msg["content"])
        if msg.get("metrics"):
            st.markdown(f'<div class="metrics-badge">{msg["metrics"]}</div>', unsafe_allow_html=True)

sys_parts = [f"Adopt the role of: {bot_role}."]
if use_personal_ctx:
    sys_parts.append(f"User Profile: Name is {user_name}, Role is {user_role}. Notes: {personal_notes}.")
if doc_text:
    sys_parts.append(f"Reference Document:\n{doc_text[:15000]}")
if prompt_technique == "One-Shot (1 Example)":
    sys_parts.append("Follow One-Shot style:\nQ: What is an API?\nA: **Definition:** Bridge between apps. **Example:** Weather app.")
elif prompt_technique == "Few-Shot (Multi-Example)":
    sys_parts.append("Follow Few-Shot pattern:\nInput: Python -> Output: Type: Language | Use: AI & Web\nInput: SQL -> Output: Type: Query | Use: Database")
elif prompt_technique == "Constraint-Based (Strict Rules)":
    sys_parts.append(f"STRICT CONSTRAINT: {constraint_rule}")
if output_format == "Markdown Table":
    sys_parts.append("IMPORTANT: Format entire response as a clean Markdown Table.")
elif output_format == "Strict JSON":
    sys_parts.append('IMPORTANT: Return ONLY valid JSON with keys: "topic", "summary", "key_points", "example".')

master_sys = "\n\n".join(sys_parts)
typed = st.chat_input("Ask NeuroChat anything...")
active_prompt = typed or st.session_state.queued_prompt
st.session_state.queued_prompt = None

if active_prompt:
    if curr_session["title"] == "New Conversation":
        curr_session["title"] = active_prompt[:25] + ("..." if len(active_prompt) > 25 else "")
    curr_session["messages"].append({"role": "user", "content": active_prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(active_prompt)

    filtered = curr_session["messages"][-history_window:]
    with st.chat_message("assistant", avatar="✨"):
        with st.spinner(f"Thinking with {model_name}..."):
            t0 = time.time()
            try:
                if provider == "Gemini":
                    if not GEMINI_KEY:
                        st.error("Please add GEMINI_KEY in Streamlit Secrets or Sidebar!")
                        st.stop()
                    g_client = genai.Client(api_key=GEMINI_KEY.strip())
                    contents = [types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part.from_text(text=m["content"])]) for m in filtered]
                    cfg = dict(system_instruction=master_sys, temperature=temperature, max_output_tokens=max_tokens, top_p=top_p)
                    if output_format == "Strict JSON":
                        cfg["response_mime_type"] = "application/json"
                    res = g_client.models.generate_content(model=model_name, contents=contents, config=types.GenerateContentConfig(**cfg))
                    reply, in_t, out_t = res.text, res.usage_metadata.prompt_token_count, res.usage_metadata.candidates_token_count
                else:
                    if not GROQ_KEY:
                        st.error("Please add GROQ_KEY in Streamlit Secrets or Sidebar!")
                        st.stop()
                    q_client = Groq(api_key=GROQ_KEY.strip())
                    msgs = [{"role": "system", "content": master_sys}] + [{"role": m["role"], "content": m["content"]} for m in filtered]
                    kw = dict(model=model_name, messages=msgs, temperature=temperature, max_tokens=max_tokens, top_p=top_p)
                    if output_format == "Strict JSON":
                        kw["response_format"] = {"type": "json_object"}
                    res = q_client.chat.completions.create(**kw)
                    reply, in_t, out_t = res.choices[0].message.content, res.usage.prompt_tokens, res.usage.completion_tokens

                lat = round(time.time() - t0, 2)
                tps = round(out_t / lat, 1) if lat > 0 else 0
                cost = (in_t / 1_000_000 * 0.30) + (out_t / 1_000_000 * 2.50)
                items = [f"🤖 {model_name}"]
                if show_latency: items.append(f"⏱️ {lat}s")
                if show_speed: items.append(f"⚡ {tps} tok/s")
                if show_tokens: items.append(f"📥 {in_t} · 📤 {out_t} tok")
                if show_cost: items.append(f"💰 ${cost:.6f}")
                m_str = " &nbsp;|&nbsp; ".join(items)

                if output_format == "Strict JSON":
                    st.code(reply, language="json")
                else:
                    st.markdown(reply)
                st.markdown(f'<div class="metrics-badge">{m_str}</div>', unsafe_allow_html=True)
                curr_session["messages"].append({"role": "assistant", "content": reply, "metrics": m_str, "format": output_format})
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ API Error ({provider}): {e}")
