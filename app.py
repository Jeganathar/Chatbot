import streamlit as st
from google import genai

st.set_page_config(page_title="Gemini AI Workspace", page_icon="✨", layout="centered")

API_KEY = st.secrets["GEMINI_API_KEY"].strip()

if "genai_client" not in st.session_state:
    st.session_state.genai_client = genai.Client(api_key=API_KEY)

client = st.session_state.genai_client

with st.sidebar:
    st.title("✨ Gemini Workspace")
    model_choice = st.selectbox(
        "Select Model",
        ["gemini-3.5-flash-lite", "gemini-3.8-flash"],
        index=0
    )
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.chat_session = client.chats.create(model=model_choice)
        st.rerun()
    st.divider()
    st.caption("Built with Python, Streamlit & Google Gemini API")

st.title("What can I help with?")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_model" not in st.session_state or st.session_state.current_model != model_choice:
    st.session_state.current_model = model_choice
    st.session_state.chat_session = client.chats.create(model=model_choice)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Message Gemini..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            def stream_reply():
                for chunk in st.session_state.chat_session.send_message_stream(prompt):
                    if chunk.text:
                        yield chunk.text

            full_response = st.write_stream(stream_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
        except Exception as e:
            st.error(f"⚠️ Error: {e}")
