import argparse
import sys
import glob
import os
import json
from ingest import build_documents, get_or_create_collection
from query import get_collection, retrieve, build_context, ask_groq, TOP_K

# ── Constants ──
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "pdf_rag"

# ── CLI Commands ──

def cmd_ingest(args):
    """Handle the ingest subcommand."""
    items_to_process = []
    
    if args.path.endswith('.json'):
        with open(args.path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                if len(data) == 1 and isinstance(list(data.values())[0], list):
                    data = list(data.values())[0]
                else:
                    data = [data]
            
            last_name = None
            for item in data:
                current_name = item.get("name")
                if current_name and current_name.strip():
                    last_name = current_name.strip()
                    
                path = item.get("url") or item.get("link")
                if not path:
                    continue
                    
                # Skip known HTML pages to avoid unnecessary downloads and errors
                if path.lower().split('?')[0].endswith(('.aspx', '.html', '.htm', '.php')):
                    continue
                    
                name_to_use = current_name if current_name and current_name.strip() else last_name
                items_to_process.append({"path": path, "name": name_to_use})
    elif os.path.isdir(args.path):
        files = glob.glob(os.path.join(args.path, "*.pdf"))
        items_to_process = [{"path": f, "name": None} for f in files]
    else:
        items_to_process = [{"path": args.path, "name": args.name}]
        
    if not items_to_process:
        print(f"No PDF files or valid URLs found at {args.path}")
        return
        
    collection = get_or_create_collection(reset=args.reset)
    
    total_chunks = 0
    for item in items_to_process:
        path = item["path"]
        name = item["name"]
        print(f"Ingesting {name or path}...")
        try:
            texts, metadatas, ids = build_documents(path, name=name)
            if texts:
                collection.upsert(
                    documents=texts,
                    metadatas=metadatas,
                    ids=ids
                )
                total_chunks += len(texts)
        except Exception as e:
            print(f"Error processing {path}: {e}")
            
    print(f"Ingestion complete! Upserted {total_chunks} total chunks.")

def cmd_query(args):
    """Handle the query subcommand."""
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
                if args.verbose:
                    print(f"\n[Verbose] Retrieved {len(chunks)} chunks:")
                    for i, c in enumerate(chunks):
                        print(f"  {i+1}. {c['source']} page {c['page']}")
                        
                context = build_context(chunks)
                answer = ask_groq(user_query, context, history=history)
                print(f"\nAnswer: {answer}")
                
                history.append({"role": "user", "content": user_query})
                history.append({"role": "assistant", "content": answer})
            except KeyboardInterrupt:
                break
    else:
        if not args.query:
            print("Error: query string is required in non-interactive mode.")
            sys.exit(1)
            
        chunks = retrieve(collection, args.query, top_k=args.top_k)
        if args.verbose:
            print(f"\n[Verbose] Retrieved {len(chunks)} chunks:")
            for i, c in enumerate(chunks):
                print(f"  {i+1}. {c['source']} page {c['page']}")
                
        context = build_context(chunks)
        answer = ask_groq(args.query, context)
        print(f"\nAnswer:\n{answer}")

def cmd_status(args):
    """Handle the status subcommand."""
    try:
        collection = get_collection()
        count = collection.count()
        print(f"Collection '{COLLECTION_NAME}' contains {count} chunks.")
    except Exception as e:
        print("Collection does not exist or could not be loaded.")

# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="PDF RAG Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Ingest parser
    parser_ingest = subparsers.add_parser("ingest", help="Ingest PDF files")
    parser_ingest.add_argument("path", help="Path to a PDF file, directory, JSON file, or URL")
    parser_ingest.add_argument("--name", help="Optional name to use when ingesting a single URL")
    parser_ingest.add_argument("--reset", action="store_true", help="Reset the ChromaDB collection before ingesting")
    
    # Query parser
    parser_query = subparsers.add_parser("query", help="Query the ingested documents")
    parser_query.add_argument("query", nargs="?", help="The query string")
    parser_query.add_argument("--top-k", type=int, default=TOP_K, help=f"Number of chunks to retrieve (default: {TOP_K})")
    parser_query.add_argument("--verbose", action="store_true", help="Print retrieved chunk metadata")
    parser_query.add_argument("--interactive", action="store_true", help="Start an interactive chat session")
    
    # Status parser
    parser_status = subparsers.add_parser("status", help="Show collection status")
    
    args = parser.parse_args()
    
    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "status":
        cmd_status(args)

if __name__ == "__main__":
    main()
