# app.py

import streamlit as st

# Import the main functions from your other scripts.
# Make sure the filenames are correct (e.g., ingest.py, agent.py).
from ingest_data import ingest_repo
from agent import final_agent_chain

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Repo Rover",
    page_icon="🧭",
    layout="wide"
)

# --- APP TITLE AND DESCRIPTION ---
st.title("Repo Rover 🧭")
st.write("Your AI-powered codebase navigator, built with TiDB Serverless and modern LLMs.")

# --- INITIALIZE SESSION STATE ---
# This helps the app remember if a repository has been indexed.
if 'indexed' not in st.session_state:
    st.session_state.indexed = False
if 'repo_url' not in st.session_state:
    st.session_state.repo_url = ""

# --- SIDEBAR FOR REPOSITORY INPUT ---
with st.sidebar:
    st.header("1. Index a Repository")
    repo_url_input = st.text_input(
        "Enter a public GitHub Repository URL:", 
        placeholder="https://github.com/pallets/flask"
    )

    if st.button("Index Repo"):
        if repo_url_input:
            with st.spinner(f"Ingesting {repo_url_input}... This may take a few minutes."):
                try:
                    # Run the ingestion process from ingest.py
                    ingest_repo(repo_url_input)
                    st.session_state.indexed = True
                    st.session_state.repo_url = repo_url_input
                    st.success("Repository indexed successfully!")
                except Exception as e:
                    st.error(f"An error occurred during ingestion: {e}")
        else:
            st.warning("Please enter a repository URL.")

    # Display the currently indexed repository
    if st.session_state.indexed:
        st.success(f"Indexed: {st.session_state.repo_url}")
    else:
        st.info("No repository has been indexed in this session.")

# --- MAIN CHAT INTERFACE ---
st.header("2. Ask a Question")

# Only allow asking questions if a repository has been indexed
if st.session_state.indexed:
    user_question = st.text_input("Ask a question about the codebase:", placeholder="e.g., How are HTTP sessions handled?")

    if st.button("Ask Repo Rover"):
        if user_question:
            with st.spinner("Searching the codebase and thinking..."):
                try:
                    # Call the agent chain from agent.py
                    response = final_agent_chain.invoke({"question": user_question})
                    st.markdown("### Response")
                    st.markdown(response)
                except Exception as e:
                    st.error(f"An error occurred while getting the answer: {e}")
        else:
            st.warning("Please enter a question.")
else:
    st.warning("Please index a repository in the sidebar before asking a question.")