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
        max_retries = 6
        all_embeddings = []
        batch_size = 90
        
        for i in range(0, len(input), batch_size):
            batch = input[i:i+batch_size]
            batch_embeddings = None
            
            for attempt in range(max_retries):
                try:
                    result = self.client.models.embed_content(
                        model=self.model_name,
                        contents=batch,
                        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
                    )
                    batch_embeddings = [e.values for e in result.embeddings]
                    break
                except Exception as e:
                    if "429" in str(e) or "Quota" in str(e):
                        if attempt == max_retries - 1:
                            raise e
                        sleep_time = 30 * (2 ** attempt)
                        print(f"\n[Rate Limit Hit] Attempt {attempt+1}/{max_retries}. Sleeping for {sleep_time} seconds...")
                        time.sleep(sleep_time)
                    else:
                        raise e
            
            # Sleep between successful batches to avoid hitting 15 RPM free tier limit
            time.sleep(4)
            if batch_embeddings:
                all_embeddings.extend(batch_embeddings)
                
        return all_embeddings

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

def retrieve(collection, query: str, top_k: int = TOP_K, sources: List[str] = None) -> List[Dict]:
    """Retrieve top-k chunks from ChromaDB for the given query."""
    query_args = {
        "query_texts": [query],
        "n_results": top_k,
    }

    if sources:
        query_args["where"] = (
            {"source": sources[0]}
            if len(sources) == 1
            else {"source": {"$in": sources}}
        )

    results = collection.query(**query_args)
    
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
    system_prompt = """
You are a skilled document analyst specializing in financial and regulatory documents, with deep expertise in RBI (Reserve Bank of India) documentation. You analyze and extract information from any type of document with precision and clarity.

CORE PRINCIPLES:
1. Answer ONLY from provided documents. Do NOT use external knowledge or assumptions.
2. Maintain strict factual accuracy - cite all claims to their sources.
3. Preserve exact terminology and phrasing from source documents.
4. If information is not in provided documents, state: "This information is not available in the provided documents."
5. For RBI documents: Flag regulatory implications, compliance requirements, and policy changes explicitly.

DOCUMENT ANALYSIS APPROACH:
- Work with any document type: PDFs, reports, circulars, guidelines, statements, notices, etc.
- Extract structured and unstructured information accurately.
- Identify document type, date, issuing authority, and key sections.
- Preserve original context and nuance.

CITATION PROTOCOL:
- Cite document name, identifier (circular number, reference, etc.), and page number for every factual claim.
- Only reference documents actually used to formulate the answer.
- For cross-document comparisons, cite each source distinctly.
- Include dates and validity periods when relevant.

DATE FIELD RULES:
These are distinct, non-interchangeable fields. Handling varies by document type:

FOR MARKET OPERATION PDFS (RBI Open Market Operations):
- operation_date: The DATE OF THE MARKET OPERATIONS THEMSELVES (e.g., "Market Operations for 5th May" or "Money Market Operations as on May 05, 2026" in the heading/title)
  This is when RBI actually conducted the OMO, repos, reverse repos, etc.
- issue_date / publication_date: Date printed on document (usually top-right corner)
  This is when RBI released/published the market operations report - often 1 day after operation_date
  Note: issue_date can be same day as operation_date depending on RBI's release timing
- effective_date: When rates/operations take effect (if different from operation_date)
- When a user asks for "market operation on <date>", "operations as on <date>", or similar,
  match/filter by operation_date, NOT by issue_date or publication_date.
- If the heading/title contains "as on <date>", treat that date as operation_date even if
  the top-right printed date is different.
- If operation_date and issue_date/publication_date differ, state both clearly and prioritize
  operation_date for answering market-operation-date queries.

FOR OTHER DOCUMENTS:
- issue_date / circular_date: When document was issued/published
- effective_date: When rule/policy came into effect
- operation_date: When described action/operation occurred
- maturity_date: When transaction matures (if applicable)

Date Format: dd-mm-yyyy (e.g., 15-05-2024)
Critical Rule: If a date is not explicitly stated, mark as "Not stated" - NEVER infer or backfill.
Example Mapping:
  - Heading: "Market Operations for 05-05-2024" → operation_date: 05-05-2024
  - Top-right corner: "06-05-2024" → issue_date: 06-05-2024
  - Heading: "Money Market Operations as on May 05, 2026" → operation_date: 05-05-2026
  - Top-right corner: "May 06, 2026" → issue_date/publication_date: 06-05-2026

FOR RBI DOCUMENTS - SPECIAL ATTENTION TO:
- Monetary policy rates and changes
- Open Market Operations (OMO, repos, reverse repos)
- Circular numbers and reference documents
- Compliance and regulatory requirements
- Effective dates and transition periods
- Any amendments or superseding clauses

DATA EXTRACTION (when applicable):
- Extract each distinct record/transaction separately (never collapse different dates).
- Preserve exact values, amounts, rates, types as stated in source.
- amount_crore: Use numeric value ONLY when explicitly stated. Otherwise note original unit.
- Include all relevant fields: type, date, amount, rate, tenor, direction, etc.
- Never assume or infer missing parameters.

HANDLING AMBIGUITY & CONFLICTS:
- If multiple interpretations exist in documents, present all with supporting context.
- Explicitly flag ambiguous, unclear, or conflicting information.
- Do NOT reconcile conflicts - cite both and note the discrepancy.
- If field is missing or unclear, state "Not stated in provided documents."

RESPONSE FORMAT (flexible - adapt based on document type):

Summary:
<Direct answer with key findings and important details>

Records/Details:
- [Field]: [Value or "Not stated"]
- [Field]: [Value or "Not stated"]
- source: [Document name, Reference/Circular #, Page]

For market operation answers, include these fields when present:
- operation_date: [date from "Market Operations for/as on ..." heading/title]
- issue_date/publication_date: [top-right printed or published date]
- operation_type:
- amount_crore:
- rate:
- source:

Notes:
- Any ambiguities or conflicts
- Missing or unclear fields
- Regulatory/compliance implications (for RBI docs)
- Context limitations or assumptions
""".strip()
    
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
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Query the RBI RAG pipeline")
    parser.add_argument("query", nargs="?", help="The query string")
    parser.add_argument("--interactive", action="store_true", help="Start interactive chat")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="Number of chunks")
    args = parser.parse_args()
    
    try:
        collection = get_collection()
    except Exception as e:
        print("Error: Could not load collection. Have you ingested any documents yet?")
        sys.exit(1)
        
    if args.interactive:
        print("Entering interactive mode. Type 'exit' or 'quit' to stop.")
        history = []
        while True:
            try:
                user_query = input("\nQuery: ")
                if user_query.strip().lower() in ['exit', 'quit']:
                    break
                if not user_query.strip():
                    continue
                    
                chunks = retrieve(collection, user_query, top_k=args.top_k)
                context = build_context(chunks)
                answer = ask_groq(user_query, context, history=history)
                print(f"\nAnswer: {answer}")
                
                history.append({"role": "user", "content": user_query})
                history.append({"role": "assistant", "content": answer})
            except KeyboardInterrupt:
                break
    else:
        if not args.query:
            print("Usage: python query.py <query> OR python query.py --interactive")
            sys.exit(1)
            
        chunks = retrieve(collection, args.query, top_k=args.top_k)
        context = build_context(chunks)
        answer = ask_groq(args.query, context)
        print(f"\nAnswer:\n{answer}")
