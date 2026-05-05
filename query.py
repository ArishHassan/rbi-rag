import os
from dotenv import load_dotenv
load_dotenv()
from typing import List, Dict
import chromadb
from google import genai
from google.genai import types
from groq import Groq

# ── Constants ──
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "pdf_rag"
GEMINI_EMBED_MODEL = "gemini-embedding-2"
GROQ_CHAT_MODEL = "llama-3.1-8b-instant"

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
TOP_K = 5
MAX_CONTEXT_CHARS = 12_000

# ── Retrieval ──

def get_collection():
    """Get the existing ChromaDB collection."""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    embedding_fn = CustomGeminiEmbeddingFunction(
        api_key=os.environ.get("GEMINI_API_KEY"),
        model_name=GEMINI_EMBED_MODEL
    )
    return client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn
    )

def retrieve(collection, query: str, top_k: int = TOP_K) -> List[Dict]:
    """Retrieve top-k chunks from ChromaDB for the given query."""
    results = collection.query(
        query_texts=[query],
        n_results=top_k
    )
    
    chunks = []
    if results['documents'] and results['documents'][0]:
        for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
            chunks.append({
                "text": doc,
                "source": meta["source"],
                "page": meta["page"]
            })
    return chunks

def build_context(chunks: List[Dict]) -> str:
    """Build a formatted context string for the LLM prompt."""
    context_parts = []
    current_length = 0
    
    for c in chunks:
        part = f"[Source: {c['source']}, Page: {c['page']}]\n{c['text']}\n"
        if current_length + len(part) > MAX_CONTEXT_CHARS:
            break
        context_parts.append(part)
        current_length += len(part)
        
    return "\n".join(context_parts)

# ── LLM Answering ──

def ask_groq(query: str, context: str, history: List[Dict] = None) -> str:
    """Send query and context to Groq to generate a grounded answer."""
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    system_prompt = (
        "You are a helpful assistant. Use the provided context to answer the user's question. "
        "If the context does not contain the answer, say you don't know based on the document. "
        "Always cite the source filename and page number in your response when providing facts from the context."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    if history:
        messages.extend(history)
        
    messages.append({
        "role": "user",
        "content": f"Context:\n{context}\n\nQuestion: {query}"
    })
    
    response = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        messages=messages,
        temperature=0.0
    )
    
    return response.choices[0].message.content

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python query.py <query>")
        sys.exit(1)
        
    query = sys.argv[1]
    collection = get_collection()
    chunks = retrieve(collection, query)
    context = build_context(chunks)
    answer = ask_groq(query, context)
    
    print("\nAnswer:\n", answer)
