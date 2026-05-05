import os
from dotenv import load_dotenv
load_dotenv()
import hashlib
from typing import List, Dict, Tuple
from pypdf import PdfReader
import chromadb
from google import genai
from google.genai import types

# ── Constants ──
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "pdf_rag"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
GEMINI_EMBED_MODEL = "gemini-embedding-2"

class CustomGeminiEmbeddingFunction(chromadb.EmbeddingFunction):
    def __init__(self, api_key: str, model_name: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def __call__(self, input: List[str]) -> List[List[float]]:
        import time
        max_retries = 4
        for attempt in range(max_retries):
            try:
                result = self.client.models.embed_content(
                    model=self.model_name,
                    contents=input,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
                )
                return [e.values for e in result.embeddings]
            except Exception as e:
                if "429" in str(e) or "Quota" in str(e):
                    if attempt == max_retries - 1:
                        raise e
                    print(f"\n[Rate Limit Hit] Sleeping for 30 seconds before retrying...")
                    time.sleep(30)
                else:
                    raise e

    def name(self) -> str:
        return "custom_gemini"

# ── Extraction & Chunking ──

def extract_pages(pdf_path: str) -> List[Dict[str, str]]:
    """Extract text page by page from a PDF file or URL."""
    if pdf_path.startswith("http://") or pdf_path.startswith("https://"):
        import requests, io
        response = requests.get(pdf_path)
        response.raise_for_status()
        file_obj = io.BytesIO(response.content)
    else:
        file_obj = pdf_path
        
    reader = PdfReader(file_obj)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            pages.append({
                "page": i + 1,
                "text": text
            })
    return pages

def chunk_text(text: str) -> List[str]:
    """Split text into overlapping chunks of CHUNK_SIZE."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

# ── Document Prep ──

def build_documents(pdf_path: str, name: str = None) -> Tuple[List[str], List[Dict[str, str]], List[str]]:
    """Build lists of texts, metadatas, and ids for ChromaDB upsertion."""
    pages = extract_pages(pdf_path)
    texts = []
    metadatas = []
    ids = []
    
    source_name = name if name else os.path.basename(pdf_path)
    
    for p in pages:
        page_chunks = chunk_text(p["text"])
        for i, chunk in enumerate(page_chunks):
            # Create a deterministic ID
            chunk_hash = hashlib.md5(chunk.encode("utf-8")).hexdigest()
            doc_id = f"{source_name}_p{p['page']}_{i}_{chunk_hash[:8]}"
            
            texts.append(chunk)
            metadatas.append({
                "source": source_name,
                "page": p["page"],
            })
            ids.append(doc_id)
            
    return texts, metadatas, ids

# ── ChromaDB Setup ──

def get_or_create_collection(reset: bool = False):
    """Get or create the ChromaDB collection with OpenAI embeddings."""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
            
    embedding_fn = CustomGeminiEmbeddingFunction(
        api_key=os.environ.get("GEMINI_API_KEY"),
        model_name=GEMINI_EMBED_MODEL
    )
    
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn
    )
    return collection

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <path_to_pdf>")
        sys.exit(1)
        
    pdf_path = sys.argv[1]
    texts, metadatas, ids = build_documents(pdf_path)
    if texts:
        collection = get_or_create_collection()
        collection.upsert(
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Ingested {len(texts)} chunks from {pdf_path}.")
    else:
        print("No text found to ingest.")
