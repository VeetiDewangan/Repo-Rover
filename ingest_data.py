# ingest.py

import tempfile
import shutil
import stat
import os
import ast
from git import Repo
import google.generativeai as genai
from sqlalchemy import create_engine, text
import sys
from dotenv import load_dotenv

load_dotenv()



# Securely loads credentials from .env file
TIDB_CONNECTION_STRING = os.environ.get("TIDB_CONNECTION_STRING")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")


# --- SAFETY CHECK ---
if "YOUR_TIDB_CONNECTION_STRING" in TIDB_CONNECTION_STRING or "YOUR_GOOGLE_API_KEY" in GOOGLE_API_KEY:
    print("🚨 Please update your TIDB_CONNECTION_STRING and GOOGLE_API_KEY in the script.")
    sys.exit(1)

# Configure the Gemini API client
genai.configure(api_key=GOOGLE_API_KEY)

#helper function 
def handle_remove_readonly(func, path, exc):
    """
    Error handler for shutil.rmtree.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.
    """
    excvalue = exc[1]
    if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno == 5: # errno.EACCES
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise


# NEW FUNCTION: Splits large text into smaller chunks for the API
def chunk_text(text_to_chunk, chunk_size=8000, overlap=200):
    """Splits text into overlapping chunks."""
    if len(text_to_chunk) <= chunk_size:
        return [text_to_chunk]
    
    chunks = []
    start = 0
    while start < len(text_to_chunk):
        end = start + chunk_size
        chunks.append(text_to_chunk[start:end])
        start += chunk_size - overlap
    return chunks


def get_functions_and_classes(filepath):
    """Parses a Python file and yields the name and source code of each function/class."""
    with open(filepath, "r", encoding="utf-8") as source_file:
        try:
            content = source_file.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    yield node.name, ast.get_source_segment(content, node)
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"Could not parse {filepath}: {e}")

def get_embedding(text, model="models/text-embedding-004"):
    """Generates an embedding for a given text using the Google Gemini API."""
    try:
        # For indexing, the task_type is RETRIEVAL_DOCUMENT
        result = genai.embed_content(model=model, content=text, task_type="RETRIEVAL_DOCUMENT")
        return result['embedding']
    except Exception as e:
        print(f"Error getting embedding for text chunk: {e}")
        return None


def ingest_repo(repo_url):
    """Clones, parses, embeds, and stores a Git repository in TiDB."""
    
    temp_dir = tempfile.mkdtemp()
    print(f"Created temporary directory: {temp_dir}")

     #Create the engine once. It manages a pool of connections.
    engine = create_engine(TIDB_CONNECTION_STRING)
    
    try:
        # 1. Clone the repository into the unique temp directory
        print(f"Cloning {repo_url} to {temp_dir}...")
        Repo.clone_from(repo_url, temp_dir)
        print("Clone complete.")

        # 2. Connect to the database and ingest data
        for root, _, files in os.walk(temp_dir):
            for file in files:
                  if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    for name, code in get_functions_and_classes(filepath):
                        if not code:
                            continue

                         # Chunk the code before embedding
                        code_chunks = chunk_text(code)

                        for chunk in code_chunks:
                            print(f"Indexing chunk from {file} -> {name}...")
                            embedding = get_embedding(chunk)

                            if embedding:
                                # Get a connection from the pool and use it right away.
                                with engine.connect() as connection:
                                    stmt = text("""
                                        INSERT INTO code_embeddings (repo_url, file_path, object_name, code_chunk, embedding)
                                        VALUES (:repo, :path, :name, :code, :embed)
                                    """)
                                    connection.execute(stmt, {
                                        "repo": repo_url,
                                        "path": filepath.replace(temp_dir, ""),
                                        "name": name,
                                        "code": chunk, # Insert the chunk, not the full code
                                        "embed": str(embedding)
                                    })
                                    connection.commit()
        print("✅ Ingestion complete!")

    finally:
    # 3. ALWAYS attempt to clean up the temporary directory
        print(f"Cleaning up temporary directory: {temp_dir}")
        try:
            shutil.rmtree(temp_dir, onerror=handle_remove_readonly)
        except PermissionError:
            print(f"⚠️ Warning: Could not remove temporary directory {temp_dir}.")
            print("This can happen on Windows if a process lock persists; it can be ignored.")


# --- SCRIPT EXECUTION ---

if __name__ == "__main__":
    target_repo = "https://github.com/pallets/flask"
    ingest_repo(target_repo)