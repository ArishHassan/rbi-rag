from fastapi import FastAPI, UploadFile, File, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import shutil
from typing import List
import json
import time
import uuid
from query import get_collection, retrieve, build_context, ask_groq
from rbi_press import fetch_latest_press_releases

app = FastAPI(title="RBI RAG Pipeline API")

# Ensure directories exist
os.makedirs("static", exist_ok=True)
os.makedirs("pdfs/pending", exist_ok=True)

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    from fastapi.responses import FileResponse
    return FileResponse("static/index.html")

@app.post("/api/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    query = data.get("query")
    history = data.get("history", [])
    sources = data.get("sources", [])
    
    if not query:
        return JSONResponse(status_code=400, content={"error": "Query is required"})
        
    try:
        collection = get_collection()
        chunks = retrieve(collection, query, sources=sources)
        context = build_context(chunks)
        answer = ask_groq(query, context, history=history)
        
        return {"answer": answer}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.pdf', '.json')):
        return JSONResponse(status_code=400, content={"error": "Only .pdf and .json files are allowed"})
        
    file_path = os.path.join("pdfs/pending", file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"message": f"File {file.filename} queued for ingestion."}

class URLRequest(BaseModel):
    url: str

@app.post("/api/upload-url")
async def upload_url(req: URLRequest):
    url = req.url.strip()
    if not url.startswith("http"):
        return JSONResponse(status_code=400, content={"error": "Invalid URL"})
        
    filename = f"url_ingest_{int(time.time())}_{str(uuid.uuid4())[:8]}.json"
    file_path = os.path.join("pdfs/pending", filename)
    
    data = [{"url": url}]
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
        
    return {"message": "URL queued for ingestion."}


@app.get("/api/rbi-press-releases")
async def rbi_press_releases(search: str = "", limit: int = 50):
    try:
        releases = fetch_latest_press_releases(search=search, limit=limit)
        return {"releases": releases}
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


class RBIReleaseSelection(BaseModel):
    releases: List[dict]


@app.post("/api/rbi-press-releases/queue")
async def queue_rbi_press_releases(req: RBIReleaseSelection):
    selected = []
    for item in req.releases:
        pdf_url = str(item.get("pdf_url", "")).strip()
        title = str(item.get("title", "")).strip()
        source_name = str(item.get("source_name", "")).strip() or title

        if not pdf_url.lower().startswith("http") or not pdf_url.lower().endswith(".pdf"):
            continue

        selected.append({
            "name": source_name,
            "url": pdf_url,
            "title": title,
            "published_date": item.get("published_date", ""),
            "detail_url": item.get("detail_url", ""),
        })

    if not selected:
        return JSONResponse(status_code=400, content={"error": "Select at least one RBI PDF release."})

    filename = f"rbi_press_{int(time.time())}_{str(uuid.uuid4())[:8]}.json"
    file_path = os.path.join("pdfs/pending", filename)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)

    return {
        "message": f"{len(selected)} RBI press release(s) queued for ingestion.",
        "sources": [item["name"] for item in selected],
    }
