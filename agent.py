# agent.py

# --- IMPORTS ---
import google.generativeai as genai
from sqlalchemy import create_engine, text
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Securely loads credentials from your .env file
TIDB_CONNECTION_STRING = os.environ.get("TIDB_CONNECTION_STRING")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
HUGGINGFACEHUB_API_TOKEN = os.environ.get("HUGGINGFACEHUB_API_TOKEN")

# --- SAFETY CHECK ---
if "YOUR_" in TIDB_CONNECTION_STRING or "YOUR_" in GOOGLE_API_KEY or "YOUR_" in HUGGINGFACEHUB_API_TOKEN:
    print("🚨 Please update your credentials in the script.")
    sys.exit(1)

# Configure the Google client (for embeddings)
genai.configure(api_key=GOOGLE_API_KEY)


def find_relevant_code(user_query: str) -> str:
    """Finds relevant code snippets from TiDB using Google's embedding model."""
    engine = create_engine(TIDB_CONNECTION_STRING)
    query_embedding = genai.embed_content(
        model="models/text-embedding-004",
        content=user_query,
        task_type="RETRIEVAL_QUERY"
    )['embedding']
    stmt = text("""
        SELECT code_chunk, file_path, object_name
        FROM code_embeddings
        ORDER BY VEC_COSINE_DISTANCE(embedding, :query_embed) ASC
        LIMIT 5
    """)
    with engine.connect() as connection:
        results = connection.execute(stmt, {"query_embed": str(query_embedding)}).fetchall()
    if not results:
        return "No relevant code found in the database."
    context = "\n---\n".join([f"File: {row.file_path}\nObject: {row.object_name}\nCode:\n{row.code_chunk}" for row in results])
    return context

# --- AGENTIC CHAIN DEFINITION ---

# Step 1: Define the base LLM using HuggingFaceEndpoint
llm_endpoint = HuggingFaceEndpoint(
    repo_id="meta-llama/Meta-Llama-3-8B-Instruct",
    huggingfacehub_api_token=HUGGINGFACEHUB_API_TOKEN,
    temperature=0.7,
)

# Step 2: Wrap the base LLM with the ChatHuggingFace class
llm = ChatHuggingFace(llm=llm_endpoint)

# FIXED: This prompt uses the special chat template required by the Llama 3 model.
final_prompt = PromptTemplate.from_template(
    """<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You are an expert programmer and senior software architect. Your task is to first explain the provided code snippets and then suggest improvements based on the user's question.<|eot_id|><|start_header_id|>user<|end_header_id|>
**User's Question:** {question}

**Relevant Code Snippets:**
{context}

---

Provide your analysis and suggestions below.<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""
)

# The chain structure remains the same
final_agent_chain = (
    {
        "context": lambda inputs: find_relevant_code(inputs["question"]),
        "question": lambda inputs: inputs["question"],
    }
    | final_prompt
    | llm
    | StrOutputParser()
)

if __name__ == "__main__":
    question = "How are HTTP sessions handled?"
    print(f"🤔 Asking Repo Rover: {question}\n")
    final_answer = final_agent_chain.invoke({"question": question})
    print("--- RESPONSE ---")
    print(final_answer)