"""Same configuration on Windows, Linux and Streamlit Community Cloud."""
import os
from pathlib import Path

from dotenv import dotenv_values
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

ROOT = Path(__file__).resolve().parent


def settings():
    values = dict(dotenv_values(ROOT / '.env'))
    values.update(dotenv_values(ROOT / '.env.groq.local'))
    try:
        values.update(dict(st.secrets))
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        pass
    keys = ('EXTRACTION_PROVIDER', 'GROQ_VISION_MODEL', 'GROQ_API_KEY')
    values.update({key: os.environ[key] for key in keys if key in os.environ})
    return values
