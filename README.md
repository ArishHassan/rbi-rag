# RBI Document RAG Pipeline

A lightweight, local Retrieval-Augmented Generation (RAG) pipeline built to index and query Reserve Bank of India (RBI) documents. This project uses Google Gemini for embeddings, Groq for chat generation, and a local ChromaDB instance for retrieval.

## Architecture

- **Embeddings:** Google Generative AI (`models/gemini-embedding-001`). The ingest script includes built-in exponential backoff to handle Google's free-tier rate limits gracefully.
- **Vector Store:** ChromaDB (running completely locally).
- **LLM:** Groq (`llama-3.1-8b-instant`) for chat generation.
- **Ingestion Engine:** Python's `pypdf` reading URLs directly into memory.

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ArishHassan/rbi-rag.git
   cd rbi-rag
   ```

2. **Install dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Set up your API Keys:**
   Create a `.env` file in the root directory of the project and add your API keys:
   ```env
   GEMINI_API_KEY="your-gemini-key-here"
   GROQ_API_KEY="your-groq-key-here"
   ```

## Usage

### 1. Ingestion

The pipeline is designed to read remote PDF URLs directly from a JSON file. The JSON structure should follow `{"selection1": [{"name": "Doc Title", "url": "https://..."}]}`.

To ingest documents into the local Chroma database:
```bash
python3 rag.py ingest path/to/your/run_results.json
```
*(Optional: Use the `--reset` flag to wipe the existing database before ingesting)*

### 2. Querying

You can ask a single question from the terminal:
```bash
python3 rag.py query "What are the new rules for UCBs?"
```

Or you can enter an interactive chat session:
```bash
python3 rag.py query --interactive
```
