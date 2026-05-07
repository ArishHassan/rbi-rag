import os
import time
import shutil
from ingest import build_documents, get_or_create_collection

PENDING_DIR = "pdfs/pending"
DONE_DIR = "pdfs/done"

def process_pending_pdfs():
    print(f"[*] Starting ingest worker. Watching '{PENDING_DIR}/' for new PDFs...")
    collection = get_or_create_collection()
    
    while True:
        try:
            # Get list of files
            file_list = [f for f in os.listdir(PENDING_DIR) if f.lower().endswith('.pdf') or f.lower().endswith('.json')]
            
            for file_name in file_list:
                file_path = os.path.join(PENDING_DIR, file_name)
                print(f"\n[Worker] Picked up: {file_name}")
                
                try:
                    if file_name.lower().endswith('.json'):
                        import json
                        with open(file_path, 'r', encoding='utf-8') as f:
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
                                if path.lower().split('?')[0].endswith(('.aspx', '.html', '.htm', '.php')):
                                    continue
                                    
                                name_to_use = current_name if current_name and current_name.strip() else last_name
                                print(f"[Worker] Fetching JSON item: {name_to_use or path}")
                                
                                texts, metadatas, ids = build_documents(path, name=name_to_use)
                                if texts:
                                    collection.upsert(documents=texts, metadatas=metadatas, ids=ids)
                                    print(f"[Worker] Successfully ingested {name_to_use or path}")
                                else:
                                    print(f"[Worker] No text found for {name_to_use or path}")
                    else:
                        texts, metadatas, ids = build_documents(file_path)
                        if texts:
                            print(f"[Worker] Upserting {len(texts)} chunks...")
                            collection.upsert(
                                documents=texts,
                                metadatas=metadatas,
                                ids=ids
                            )
                            print(f"[Worker] Successfully ingested {file_name}")
                        else:
                            print(f"[Worker] No text found in {file_name}")
                    
                    # Move to done
                    done_path = os.path.join(DONE_DIR, file_name)
                    shutil.move(file_path, done_path)
                    print(f"[Worker] Moved {file_name} to {DONE_DIR}/")
                    
                except Exception as e:
                    print(f"[Worker] Error processing {file_name}: {e}")
                    print(f"[Worker] Sleeping for 30 seconds before retrying...")
                    time.sleep(30)
                    
            time.sleep(5)
            
        except KeyboardInterrupt:
            print("\n[*] Stopping ingest worker.")
            break
        except Exception as e:
            print(f"[Worker] Critical error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    os.makedirs(PENDING_DIR, exist_ok=True)
    os.makedirs(DONE_DIR, exist_ok=True)
    process_pending_pdfs()
