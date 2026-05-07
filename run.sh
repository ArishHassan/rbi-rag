#!/bin/bash
mkdir -p pdfs/pending pdfs/done

echo "Starting background ingest worker..."
PYTHONDONTWRITEBYTECODE=1 python3 ingest_worker.py &
WORKER_PID=$!

echo "Starting FastAPI web server..."
PYTHONDONTWRITEBYTECODE=1 python3 -m uvicorn app:app --host 0.0.0.0 --port 8000

echo "Stopping background worker..."
kill $WORKER_PID
wait $WORKER_PID 2>/dev/null
