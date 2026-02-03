from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Response, Depends, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import models, schemas, auth, database, midtrans_client
from database import engine, get_db
from dotenv import load_dotenv
import os

load_dotenv()

models.Base.metadata.create_all(bind=engine)

from pydantic import BaseModel
import subprocess
import json
import signal
import psutil
from typing import Optional, List
import pandas as pd
import threading
import time
import requests
import re
from PIL import Image
from datetime import datetime
import io
import pytesseract
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import urllib.parse
import random

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://blast.ve-lora.my.id",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth Metadata
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        from jose import jwt
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except Exception:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user

CONFIG_FILE = "env_parameters.json"
SCRAPER_SCRIPT = "script_no_api.py"

# active_scrapers = {} # DEPRECATED: Moved to Database

class ConfigModel(BaseModel):
    # API Key is now optional/unused
    GOOGLE_MAPS_API_KEY: Optional[str] = ""
    GOOGLE_MAPS_LINK: Optional[str] = ""
    RADIUS: int = 5000
    MESSAGE_LIMIT: int = 10
    search_phrase: str
    WHATSAPP_PHONE_NUMBER: Optional[str] = ""
    APPOINTMENT_DATE: str
    APPOINTMENT_TIME: str
    CHROME_DRIVER_PATH: str = os.getenv("CHROME_DRIVER_PATH", "/usr/bin/chromedriver")
    CHROME_USER_DATA_DIR: str = os.getenv("CHROME_USER_DATA_DIR", "/home/mahinutsmannawawi/.config/google-chrome")
    CHROME_PROFILE_NAME: str = os.getenv("CHROME_PROFILE_NAME", "Default")
    country_code_file: str = "country_codes.csv"
    message_file: str = "prep_message.txt"
    # Telegram Config
    TELEGRAM_CHAT_ID: Optional[str] = ""
    TELEGRAM_CHAT_ID_NOTIF: Optional[str] = ""

# --- Telegram Business Notification Helper ---
def send_business_notification(message: str):
    """Send notification to Blast Notif Telegram group"""
    try:
        # Prioritize Environment Variables
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID_NOTIF")
        
        # Fallback to config file
        if (not bot_token or not chat_id) and os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            bot_token = bot_token or config.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = chat_id or config.get("TELEGRAM_CHAT_ID_NOTIF", "")
            
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"⚠️ Telegram notification error: {e}")

@app.get("/config")
def get_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

@app.post("/config")
def update_config(config: ConfigModel):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config.dict(), f, indent=4)
    return {"message": "Config updated successfully"}

@app.post("/start")
def start_scraper(background_tasks: BackgroundTasks, current_user: models.User = Depends(get_current_user)):
    global active_scrapers
    
    user_id = current_user.id
    
    # Check if already running for this user
@app.post("/start")
def start_scraper(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    user_id = current_user.id
    
    # Check if already running in DB
    existing_job = db.query(models.ScrapingJob).filter(
        models.ScrapingJob.owner_id == user_id,
        models.ScrapingJob.status == "running"
    ).first()
    
    if existing_job:
        # Verify if process is actually alive
        if psutil.pid_exists(existing_job.pid):
            return {"status": "error", "message": "Scraper is already running (Job ID: " + str(existing_job.id) + ")"}
        else:
            # Zombie record, mark as failed
            existing_job.status = "failed"
            db.commit()

    # Read config for metadata
    keyword = "Unknown"
    limit = 50
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                keyword = cfg.get("search_phrase", "Unknown")
                limit = cfg.get("max_results", 50)
        except: pass

    # Define user-specific paths
    log_file = f"logs/scraper_{user_id}.log"
    output_dir = f"results/{user_id}"
    
    # Ensure log directory exists
    os.makedirs("logs", exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # Run the script with arguments
    try:
        cmd = ["python3", SCRAPER_SCRIPT, "--owner_id", str(user_id), "--log_file", log_file, "--output_dir", output_dir]
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Create Job in DB
        new_job = models.ScrapingJob(
            owner_id=user_id,
            keyword=keyword,
            limit=limit,
            status="running",
            pid=proc.pid,
            log_file_path=log_file,
            result_file_path=output_dir
        )
        db.add(new_job)
        db.commit()
        
        return {"status": "success", "message": "Scraper started", "pid": proc.pid, "job_id": new_job.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop")
@app.post("/stop")
def stop_scraper(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    user_id = current_user.id
    
    # Find running job
    job = db.query(models.ScrapingJob).filter(
        models.ScrapingJob.owner_id == user_id,
        models.ScrapingJob.status == "running"
    ).first()
    
    if job and job.pid:
        try:
            if psutil.pid_exists(job.pid):
                parent = psutil.Process(job.pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
            
            job.status = "stopped"
            db.commit()
            return {"status": "success", "message": "Scraper stopped"}
        except Exception as e:
            job.status = "error" # Mark error but consider stopped
            db.commit()
            return {"status": "error", "message": f"Error stopping: {str(e)}"}
            
    return {"status": "error", "message": "No scraper running"}

@app.get("/status")
@app.get("/status")
def get_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    user_id = current_user.id
    
    job = db.query(models.ScrapingJob).filter(
        models.ScrapingJob.owner_id == user_id
    ).order_by(models.ScrapingJob.created_at.desc()).first()
    
    if job and job.status == "running":
        if psutil.pid_exists(job.pid):
             return {"status": "running", "pid": job.pid, "job_id": job.id}
        else:
             # Auto-update status if process died silently
             job.status = "completed"
             db.commit()
             
    return {"status": "stopped"}

@app.get("/logs")
def get_logs(current_user: models.User = Depends(get_current_user)):
    user_id = current_user.id
    log_file = f"logs/scraper_{user_id}.log"
    
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            # Read last 100 lines for efficiency
            lines = f.readlines()
            return {"logs": "".join(lines[-100:])}
    return {"logs": "No logs yet..."}

# --- Evolution API Integration ---

EVOLUTION_URL = os.getenv("EVOLUTION_URL", "http://localhost:8081")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "velora123")

def get_evolution_headers():
    return {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }

@app.get("/whatsapp/sessions")
def get_whatsapp_sessions(current_user: models.User = Depends(get_current_user)):
    """Get all Evolution instances for current user"""
    try:
        res = requests.get(f"{EVOLUTION_URL}/instance/fetchInstances", headers=get_evolution_headers())
        if res.status_code != 200:
            return {"sessions": [], "max_senders": 0, "used": 0}
        
        all_instances = res.json() # list of objects
        
        # Filter (convention: instanceName starts with u{id}_)
        prefix = f"u{current_user.id}_"
        user_instances = []
        
        for inst in all_instances:
            if isinstance(inst, dict):
                name = inst.get("name") or inst.get("instanceName") or inst.get("instance", {}).get("instanceName")
                status = inst.get("status") or inst.get("instance", {}).get("status") or "STOPPED"
                
                if name and name.startswith(prefix):
                    user_instances.append({
                        "name": name,
                        "status": status, # connected, open, close, connecting
                        "config": {}
                    })

        # Max Limit Logic
        max_limit = 1
        if current_user.email == OWNER_EMAIL:
            max_limit = 999
        else:
            db = next(get_db())
            pkg = db.query(models.Package).filter(models.Package.name == current_user.package_type).first()
            if pkg:
                max_limit = pkg.max_senders
            db.close()
            
        return {
            "sessions": user_instances,
            "max_senders": max_limit,
            "used": len(user_instances)
        }
    except Exception as e:
        print(f"Evolution Error: {e}")
        return {"sessions": [], "max_senders": 0, "used": 0, "error": str(e)}

@app.post("/whatsapp/session")
def create_whatsapp_session(session_name: str = Body(..., embed=True), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Create a new Evolution instance"""
    # 1. Check Limits (Reused logic)
    max_limit = 1
    if current_user.email == OWNER_EMAIL:
        max_limit = 999
    else:
        pkg = db.query(models.Package).filter(models.Package.name == current_user.package_type).first()
        if pkg:
            max_limit = pkg.max_senders
            
    # Fetch existing to count
    try:
        res = requests.get(f"{EVOLUTION_URL}/instance/fetchInstances", headers=get_evolution_headers(), timeout=10)
        if res.status_code == 200:
            all_instances = res.json()
            prefix = f"u{current_user.id}_"
            count = 0
            for inst in all_instances:
                name = inst.get("name") or inst.get("instanceName")
                if name and name.startswith(prefix):
                    count += 1
            
            if count >= max_limit:
                 raise HTTPException(status_code=403, detail=f"Batas akun WhatsApp tercapai ({max_limit} akun).")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error checking instances: {e}")

    try:
        full_session_name = f"u{current_user.id}_{session_name.replace(' ', '_')}"
        import secrets
        token = secrets.token_hex(16)
        
        payload = {
            "instanceName": full_session_name,
            "token": token,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS"
        }
        
        create_res = requests.post(
            f"{EVOLUTION_URL}/instance/create", 
            json=payload, 
            headers=get_evolution_headers(),
            timeout=15
        )
        
        if create_res.status_code == 403:
            # Instance might already exist, try to connect
            pass
        elif create_res.status_code not in [200, 201]:
            error_detail = create_res.text[:200] if create_res.text else "Unknown error"
            raise HTTPException(status_code=500, detail=f"Failed to create instance: {error_detail}")
        
        # Try to initiate connection immediately to generate QR
        try:
            connect_res = requests.get(
                f"{EVOLUTION_URL}/instance/connect/{full_session_name}",
                headers=get_evolution_headers(),
                timeout=10
            )
            print(f"Connect response: {connect_res.status_code}")
        except Exception as ce:
            print(f"Connect error (non-fatal): {ce}")
            
        return {
            "name": full_session_name,
            "status": "created",
            "message": "Session created. Poll /whatsapp/qr/{session_name} for QR code."
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Create session error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/whatsapp/qr/{session_name}")
def get_whatsapp_qr(session_name: str, current_user: models.User = Depends(get_current_user)):
    """Get QR Code (Base64 -> Image) from Evolution"""
    if not session_name.startswith(f"u{current_user.id}_"):
         raise HTTPException(status_code=403, detail="Access denied")
         
    try:
        # First, try to connect/initiate the instance if not already
        connect_res = requests.get(
            f"{EVOLUTION_URL}/instance/connect/{session_name}", 
            headers=get_evolution_headers(),
            timeout=10
        )
        
        # Check if we got QR in connect response
        if connect_res.status_code == 200:
            data = connect_res.json()
            b64 = data.get("base64") or data.get("code") or data.get("qrcode", {}).get("base64")
            
            if b64:
                # Remove header if present "data:image/png;base64,"
                if "," in b64:
                    b64 = b64.split(",")[1]
                import base64
                img_data = base64.b64decode(b64)
                return Response(content=img_data, media_type="image/png")
        
        # If connect didn't give QR, try fetchInstances to check status
        fetch_res = requests.get(
            f"{EVOLUTION_URL}/instance/fetchInstances",
            headers=get_evolution_headers(),
            timeout=10
        )
        
        if fetch_res.status_code == 200:
            instances = fetch_res.json()
            for inst in instances:
                name = inst.get("name") or inst.get("instanceName") or inst.get("instance", {}).get("instanceName")
                if name == session_name:
                    status = inst.get("status") or inst.get("instance", {}).get("status")
                    if status in ["open", "connected", "working"]:
                        # Already connected, no QR needed
                        raise HTTPException(status_code=200, detail="Already connected")
        
        # QR not ready yet
        raise HTTPException(status_code=404, detail="QR not ready, please wait and retry")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"QR Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/whatsapp/logout")
def logout_whatsapp(session_name: str = Body(..., embed=True), current_user: models.User = Depends(get_current_user)):
    if not session_name.startswith(f"u{current_user.id}_"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Evolution delete instance
    try:
        requests.delete(f"{EVOLUTION_URL}/instance/delete/{session_name}", headers=get_evolution_headers())
        return {"status": "success"}
    except Exception as e:
         return {"status": "error", "detail": str(e)}

@app.get("/results")
def get_results(current_user: models.User = Depends(get_current_user)):
    """List all result folders and their CSV contents for the current user"""
    user_id = current_user.id
    data_dir = f"results/{user_id}"
    results = []
    
    try:
        if os.path.exists(data_dir):
            folders = [f for f in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, f)) and not f.startswith(".")]
            for folder in folders:
                folder_path = os.path.join(data_dir, folder)     
                files = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
                for file in files:
                    results.append({
                        "folder": folder,
                        "file": file,
                        "path": os.path.join(folder_path, file)
                    })
    except Exception as e:
        print(f"Error listing results: {e}")
        
    return {"results": results}

@app.get("/results/content")
def get_result_content(path: str, current_user: models.User = Depends(get_current_user)):
    """Read content of a result CSV file safely"""
    user_id = current_user.id
    
    # Path Traversal Protection
    # Ensure path starts with results/{user_id}/ and contains no ..
    safe_base = os.path.abspath(f"results/{user_id}")
    requested_path = os.path.abspath(path)
    
    if not requested_path.startswith(safe_base):
        raise HTTPException(status_code=403, detail="Access denied: Invalid file path")
        
    if not os.path.exists(requested_path) or not requested_path.endswith(".csv"):
         raise HTTPException(status_code=404, detail="File not found or invalid format")
         
    try:
        df = pd.read_csv(requested_path)
        # return first 50 rows preview + columns
        preview = df.head(50).fillna("").to_dict(orient="records")
        return {"columns": list(df.columns), "data": preview, "total_rows": len(df)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

# --- Phase 4 & 5: OCR and Master Data ---

MASTER_DATA_FILE = "master_data.csv"

def ensure_master_structure():
    if not os.path.exists(MASTER_DATA_FILE):
        df = pd.DataFrame(columns=["Phone", "Name", "Business", "Source", "Date"])
        df.to_csv(MASTER_DATA_FILE, index=False)

def append_to_master(db: Session, owner_id: int, new_data: List[dict]):
    """Saves new leads to the database table with owner_id"""
    for item in new_data:
        # Check if lead already exists for this owner
        existing = db.query(models.Lead).filter(
            models.Lead.phone == str(item['Phone']).strip(),
            models.Lead.owner_id == owner_id
        ).first()
        
        if not existing:
            new_lead = models.Lead(
                phone=str(item['Phone']).strip(),
                name=item.get('Name', '-'),
                business_name=item.get('Business', '-'),
                source=item.get('Source', 'Manual'),
                status=item.get('Status', 'Pending'),
                owner_id=owner_id
            )
            db.add(new_lead)
    db.commit()
        
    df_new = pd.DataFrame(new_data)
    
    # Merge logic: Append and Deduplicate by Phone
    if not df_new.empty:
        df_combined = pd.concat([df_master, df_new])
        df_combined['Phone'] = df_combined['Phone'].astype(str).str.strip()
        df_combined = df_combined.drop_duplicates(subset=['Phone'], keep='first')
        df_combined.to_csv(MASTER_DATA_FILE, index=False)

def send_to_telegram(image_bytes, caption, config):
    try:
        token = config.get("TELEGRAM_BOT_TOKEN")
        chat_id = config.get("TELEGRAM_CHAT_ID")
        
        if not token or not chat_id:
            print("Telegram not configured.")
            return

        import requests
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        files = {"photo": ("image.jpg", image_bytes)}
        data = {"chat_id": chat_id, "caption": caption}
        
        requests.post(url, data=data, files=files)
        print("Telegram message sent.")
    except Exception as e:
        print(f"Failed to send Telegram: {e}")

# ... (Imports remain the same)
import threading
import time
import requests # Ensure requests is imported

# ... (Previous code remains)

# ... (Previous code)

# --- Shared Logic ---

def process_image_for_ocr(db: Session, owner_id: int, image_bytes, source_label="OCR Upload"):
    """Reusable OCR Logic with Database storage"""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        
        phone_pattern = re.compile(r'(\+?62\s?|0)(\d{3,4}[-\s]?\d{3,5}[-\s]?\d{0,4})')
        matches = phone_pattern.findall(text)
        
        extracted_data = []
        unique_numbers = set()
        
        for match in matches:
            full_number = f"{match[0]}{match[1]}".replace(" ", "").replace("-", "")
            if full_number.startswith("0"):
                full_number = "62" + full_number[1:]
            
            if len(full_number) > 9 and full_number not in unique_numbers: 
                unique_numbers.add(full_number)
                extracted_data.append({
                    "Phone": full_number,
                    "Name": "-",
                    "Business": "-",
                    "Source": source_label,
                    "Status": "Pending"
                })
                
        # Save to Database
        if extracted_data:
            append_to_master(db, owner_id, extracted_data)
            
        return unique_numbers, len(extracted_data), text
    except Exception as e:
        print(f"OCR Processing Error: {e}")
        return set(), 0, ""

# --- Master Data Management ---

MASTER_DATA_FILE = "master_data.csv"

def ensure_master_structure():
    if not os.path.exists(MASTER_DATA_FILE):
        df = pd.DataFrame(columns=["Phone", "Name", "Business", "Source", "Date", "Status"])
        df.to_csv(MASTER_DATA_FILE, index=False)
    else:
        # Migrate if Status missing
        df = pd.read_csv(MASTER_DATA_FILE)
        if "Status" not in df.columns:
            df["Status"] = "Pending"
            df.to_csv(MASTER_DATA_FILE, index=False)

def append_to_master(new_data: List[dict]):
    ensure_master_structure()
    try:
        df_master = pd.read_csv(MASTER_DATA_FILE)
    except:
        df_master = pd.DataFrame(columns=["Phone", "Name", "Business", "Source", "Date", "Status"])
        
    df_new = pd.DataFrame(new_data)
    if "Status" not in df_new.columns:
        df_new["Status"] = "Pending"
    
    # Merge logic: Append and Deduplicate by Phone
    if not df_new.empty:
        df_combined = pd.concat([df_master, df_new])
        df_combined['Phone'] = df_combined['Phone'].astype(str).str.strip()
        df_combined = df_combined.drop_duplicates(subset=['Phone'], keep='first')
        df_combined.to_csv(MASTER_DATA_FILE, index=False)

# --- Validation Logic ---

@app.post("/clean-master")
def clean_master_phones():
    """Format Standardizer: 08x -> 628x, Remove symbols"""
    ensure_master_structure()
    try:
        df = pd.read_csv(MASTER_DATA_FILE)
        
        def clean_phone(p):
            p = str(p).strip().replace("-", "").replace(" ", "").replace("(", "").replace(")", "").replace("+", "")
            if p.startswith("0"):
                p = "62" + p[1:]
            return p

        df['Phone'] = df['Phone'].apply(clean_phone)
        df['Status'] = df['Status'].apply(lambda x: x if pd.notna(x) else "Pending") 
        # Mark as formatted if it looks right
        df.loc[df['Phone'].str.startswith("62"), 'Status'] = "Formatted"
        
        df = df.drop_duplicates(subset=['Phone'], keep='first')
        df.to_csv(MASTER_DATA_FILE, index=False)
        return {"status": "success", "message": f"Cleaned {len(df)} records."}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/validate-wa")
def validate_whatsapp(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Deep Validation using Selenium (Background)"""
    background_tasks.add_task(run_wa_check, current_user.id)
    return {"status": "success", "message": "WhatsApp validation started in background."}

@app.post("/clean-leads")
def clean_leads(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Clean and standardize phone numbers in database leads"""
    import re
    
    def clean_phone(p):
        if not p:
            return None
        # Remove all non-digit characters
        p = re.sub(r'\D', '', str(p))
        # Convert 08x to 628x
        if p.startswith("0"):
            p = "62" + p[1:]
        # Remove leading 62 if doubled
        if p.startswith("6262"):
            p = p[2:]
        # Validate length (Indonesian mobile: 62 + 9-12 digits)
        if len(p) < 10 or len(p) > 15:
            return None
        # Must start with 62
        if not p.startswith("62"):
            return None
        return p
    
    leads = db.query(models.Lead).filter(models.Lead.owner_id == current_user.id).all()
    cleaned_count = 0
    removed_count = 0
    
    for lead in leads:
        cleaned = clean_phone(lead.phone)
        if cleaned:
            if cleaned != lead.phone:
                lead.phone = cleaned
                lead.status = "Formatted"
                cleaned_count += 1
        else:
            # Invalid number - mark for reference but don't delete
            lead.status = "Invalid"
            removed_count += 1
    
    db.commit()
    return {
        "status": "success", 
        "message": f"Cleaned {cleaned_count} nomor, {removed_count} nomor invalid ditandai.",
        "cleaned": cleaned_count,
        "invalid": removed_count
    }

def run_wa_check(owner_id: int):
    """Selenium script to check WA existence for specific owner"""
    print(f"🕵️‍♂️ Starting WA Validation for User {owner_id}...")
    db = database.SessionLocal()
    try:
        leads = db.query(models.Lead).filter(
            models.Lead.owner_id == owner_id,
            models.Lead.status.in_(["Pending", "Formatted"])
        ).all()
        
        if not leads:
            print("No numbers to validate.")
            return

        options = webdriver.ChromeOptions()
        options.add_argument("--user-data-dir=/home/mahinutsmannawawi/.config/google-chrome") 
        options.add_argument("--profile-directory=Default")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        try:
            for lead in leads:
                phone = lead.phone
                print(f"Checking {phone}...")
                driver.get(f"https://web.whatsapp.com/send?phone={phone}&text=hi")
                
                try:
                    WebDriverWait(driver, 20).until_not(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='startup-progress']"))
                    )
                    time.sleep(2)
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    
                    if "Phone number shared via url is invalid" in body_text:
                        lead.status = "Invalid"
                    elif "Type a message" in body_text or "ketik pesan" in body_text.lower():
                        lead.status = "WA Active"
                    else:
                        inputs = driver.find_elements(By.CSS_SELECTOR, "div[contenteditable='true']")
                        if inputs:
                             lead.status = "WA Active"
                        else:
                             lead.status = "Unknown"
                             
                except Exception as e:
                    print(f"Error checking {phone}: {e}")
                    lead.status = "Error"
                
                db.commit() # Save each result
        finally:
            driver.quit()
    finally:
        db.close()

# ... (Previous code)

# ... (Previous imports)

# --- Template Manager Logic ---
TEMPLATE_FILE = "templates.json"

def get_templates():
    if not os.path.exists(TEMPLATE_FILE):
        return []
    try:
        with open(TEMPLATE_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_templates(templates):
    with open(TEMPLATE_FILE, "w") as f:
        json.dump(templates, f)


# --- Template Endpoints ---

@app.get("/templates", response_model=List[schemas.TemplateResponse])
def get_templates(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Template).filter(models.Template.owner_id == current_user.id).all()

@app.post("/templates", response_model=schemas.TemplateResponse)
def create_template(template: schemas.TemplateCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    new_template = models.Template(
        name=template.name,
        content=template.content,
        owner_id=current_user.id
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return new_template

@app.put("/templates/{template_id}", response_model=schemas.TemplateResponse)
def update_template(template_id: int, template: schemas.TemplateCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_template = db.query(models.Template).filter(models.Template.id == template_id, models.Template.owner_id == current_user.id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    db_template.name = template.name
    db_template.content = template.content
    db.commit()
    db.refresh(db_template)
    return db_template

@app.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_template = db.query(models.Template).filter(models.Template.id == template_id, models.Template.owner_id == current_user.id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
        
    db.delete(db_template)
    db.commit()
    return {"message": "Template deleted"}


# --- WhatsApp Connection Helper ---

# --- Broadcast Logic (Evolution API + Anti-Detection) ---

import threading
import random
import time

broadcast_state = {
    "status": "idle",  # idle, running, stopped, finished, error
    "total": 0,
    "sent": 0,
    "failed": 0,
    "progress": 0,     # 0-100 percentage
    "current_phone": "",
    "current_delay": 0,
    "logs": [],
    "session_used": ""
}
broadcast_stop_event = threading.Event()

# Anti-Detection Configuration
ANTI_DETECTION_CONFIG = {
    "min_delay_between_messages": 15,  # Minimum seconds between messages
    "max_delay_between_messages": 45,  # Maximum seconds between messages
    "typing_simulation_min": 2,        # Min seconds to simulate typing
    "typing_simulation_max": 5,        # Max seconds to simulate typing
    "cooldown_every_n_messages": 15,   # Take break after N messages
    "cooldown_duration_min": 120,      # Min cooldown in seconds (2 min)
    "cooldown_duration_max": 300,      # Max cooldown in seconds (5 min)
    "daily_limit_per_session": 200,    # Max messages per session per day
    "random_skip_probability": 0.05,   # 5% chance to skip (looks more human)
}

def process_spintax(text):
    """Process spintax like {Hi|Hello|Hey} -> random choice"""
    import re
    pattern = r'\{([^{}]+)\}'
    while re.search(pattern, text):
        match = re.search(pattern, text)
        choices = match.group(1).split('|')
        text = text[:match.start()] + random.choice(choices) + text[match.end():]
    return text

def get_user_evolution_session(db, owner_id):
    """Get first connected Evolution session for user"""
    try:
        res = requests.get(f"{EVOLUTION_URL}/instance/fetchInstances", headers=get_evolution_headers(), timeout=10)
        if res.status_code == 200:
            instances = res.json()
            prefix = f"u{owner_id}_"
            for inst in instances:
                name = inst.get("name") or inst.get("instanceName") or inst.get("instance", {}).get("instanceName")
                status = inst.get("status") or inst.get("instance", {}).get("status") or ""
                if name and name.startswith(prefix) and status.lower() in ["open", "connected", "working"]:
                    return name
    except Exception as e:
        print(f"Error getting session: {e}")
    return None

def send_message_via_evolution(session_name: str, phone: str, message: str):
    """Send message via Evolution API with proper formatting"""
    # Normalize phone number
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "62" + phone[1:]
    if not phone.startswith("62"):
        phone = "62" + phone
    
    # Ensure phone ends with @s.whatsapp.net for Evolution
    jid = f"{phone}@s.whatsapp.net"
    
    payload = {
        "number": phone,
        "text": message
    }
    
    try:
        res = requests.post(
            f"{EVOLUTION_URL}/message/sendText/{session_name}",
            json=payload,
            headers=get_evolution_headers(),
            timeout=30
        )
        
        if res.status_code in [200, 201]:
            return {"success": True, "data": res.json()}
        else:
            return {"success": False, "error": res.text[:200]}
            
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def broadcast_worker(owner_id: int, leads: List[dict], template_content: str, min_delay=15, max_delay=45, rotate=False, session_name=None):
    """Background worker for broadcasting with Evolution API + Anti-Detection"""
    global broadcast_state, broadcast_stop_event
    
    db = database.SessionLocal()
    config = ANTI_DETECTION_CONFIG.copy()
    
    # Override delays from request
    config["min_delay_between_messages"] = max(min_delay, 10)  # Force minimum 10s
    config["max_delay_between_messages"] = max(max_delay, min_delay + 10)
    
    # Load templates if rotation enabled
    stored_templates = []
    if rotate:
        templates = db.query(models.Template).filter(models.Template.owner_id == owner_id).all()
        stored_templates = [t.content for t in templates]
        if not stored_templates:
            print("⚠️ No templates found, using single template")
            rotate = False
    
    # Get Evolution session
    if not session_name:
        session_name = get_user_evolution_session(db, owner_id)
    
    if not session_name:
        broadcast_state["status"] = "error"
        broadcast_state["logs"].append("❌ No connected WhatsApp session found! Please connect WhatsApp first.")
        db.close()
        return
    
    broadcast_state["status"] = "running"
    broadcast_state["total"] = len(leads)
    broadcast_state["sent"] = 0
    broadcast_state["failed"] = 0
    broadcast_state["progress"] = 0
    broadcast_state["logs"] = []
    broadcast_state["session_used"] = session_name
    
    print(f"🚀 Broadcast Started for User {owner_id} via {session_name}")
    broadcast_state["logs"].append(f"🚀 Starting broadcast to {len(leads)} contacts...")
    broadcast_state["logs"].append(f"📱 Using session: {session_name}")
    
    try:
        messages_since_cooldown = 0
        
        for i, lead in enumerate(leads):
            # Check stop signal
            if broadcast_stop_event.is_set():
                broadcast_state["status"] = "stopped"
                broadcast_state["logs"].append("🛑 Broadcast stopped by user.")
                break
            
            phone = str(lead.get("Phone", "") or lead.get("phone", "")).strip()
            name = lead.get("Name", "-") or lead.get("name", "-") or "-"
            
            if not phone or len(phone) < 10:
                broadcast_state["failed"] += 1
                broadcast_state["logs"].append(f"⏭️ Skipped invalid: {phone}")
                continue
            
            # Random skip (looks more human)
            if random.random() < config["random_skip_probability"]:
                broadcast_state["logs"].append(f"⏭️ Random skip: {phone} (will retry later)")
                continue
            
            # Prepare message
            current_template = template_content
            if rotate and stored_templates:
                current_template = random.choice(stored_templates)
            
            message = current_template.replace("{name}", name).replace("{Name}", name)
            message = process_spintax(message)
            
            # Update state
            broadcast_state["current_phone"] = phone
            
            # Simulate typing delay (anti-detection)
            typing_delay = random.uniform(
                config["typing_simulation_min"],
                config["typing_simulation_max"]
            )
            broadcast_state["logs"].append(f"⌨️ Typing to {phone}...")
            time.sleep(typing_delay)
            
            if broadcast_stop_event.is_set():
                break
            
            # Send via Evolution API
            result = send_message_via_evolution(session_name, phone, message)
            
            if result["success"]:
                broadcast_state["sent"] += 1
                broadcast_state["logs"].append(f"✅ Sent to {phone}")
                messages_since_cooldown += 1
            else:
                broadcast_state["failed"] += 1
                error_msg = result.get("error", "Unknown")[:50]
                broadcast_state["logs"].append(f"❌ Failed {phone}: {error_msg}")
            
            # Update progress percentage
            processed = i + 1
            broadcast_state["progress"] = int((processed / len(leads)) * 100)
            
            # Cooldown check
            if messages_since_cooldown >= config["cooldown_every_n_messages"]:
                cooldown = random.uniform(
                    config["cooldown_duration_min"],
                    config["cooldown_duration_max"]
                )
                broadcast_state["logs"].append(f"☕ Cooldown {int(cooldown)}s (anti-spam protection)...")
                broadcast_state["current_delay"] = int(cooldown)
                
                for _ in range(int(cooldown)):
                    if broadcast_stop_event.is_set():
                        break
                    time.sleep(1)
                
                messages_since_cooldown = 0
                continue
            
            # Random delay between messages
            delay = random.uniform(
                config["min_delay_between_messages"],
                config["max_delay_between_messages"]
            )
            
            # Add extra randomness
            delay += random.uniform(-3, 5)
            delay = max(10, delay)  # Never less than 10s
            
            broadcast_state["current_delay"] = int(delay)
            broadcast_state["logs"].append(f"⏳ Waiting {int(delay)}s before next...")
            
            for _ in range(int(delay)):
                if broadcast_stop_event.is_set():
                    break
                time.sleep(1)
                
    except Exception as e:
        print(f"Broadcast error: {e}")
        import traceback
        traceback.print_exc()
        broadcast_state["status"] = "error"
        broadcast_state["logs"].append(f"🔥 Critical error: {str(e)[:100]}")
    
    finally:
        if not broadcast_stop_event.is_set():
            broadcast_state["status"] = "finished"
            broadcast_state["progress"] = 100
            broadcast_state["logs"].append(f"🏁 Done! Sent: {broadcast_state['sent']}, Failed: {broadcast_state['failed']}")
        db.close()

class BroadcastRequest(BaseModel):
    template: str = ""
    target: str  # "verified" or "all"
    min_delay: int = 15
    max_delay: int = 45
    rotate: bool = False
    session_name: str = ""  # Optional: specific session to use

class TestBroadcastRequest(BaseModel):
    phone: str
    message: str
    session_name: str = "" # Optional

@app.post("/broadcast/test")
def start_test_broadcast(
    req: TestBroadcastRequest, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Send a single test message to a specific number"""
    
    # Cleaning phone number
    clean_number = clean_master_phones.clean_phone(req.phone)
    if not clean_number:
        raise HTTPException(status_code=400, detail="Invalid phone number format")
        
    session_name = req.session_name
    if not session_name:
        # Auto-select session
        sessions = get_user_evolution_session(db, current_user.id)
        if not sessions:
            raise HTTPException(status_code=400, detail="No connected WhatsApp session found")
        session_name = sessions[0]
        
    # Send message
    result = send_message_via_evolution(session_name, clean_number, req.message)
    
    if result["success"]:
        return {"status": "success", "message": f"Test message sent to {clean_number}"}
    else:
        return {"status": "error", "message": result.get("error", "Unknown error")}

@app.post("/broadcast/start")
def start_broadcast(
    req: BroadcastRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    global broadcast_state, broadcast_stop_event
    
    if broadcast_state["status"] == "running":
        raise HTTPException(status_code=400, detail="Broadcast already running")

    if not req.rotate and not req.template:
        raise HTTPException(status_code=400, detail="Template required if rotation is disabled")

    # Get leads from database
    if req.target == "verified":
        leads_query = db.query(models.Lead).filter(
            models.Lead.owner_id == current_user.id, 
            models.Lead.status == "WA Active"
        ).all()
    else:
        leads_query = db.query(models.Lead).filter(
            models.Lead.owner_id == current_user.id
        ).all()
    
    leads = [{"Phone": l.phone, "Name": l.name or l.business_name or "-"} for l in leads_query]
    
    if not leads:
        raise HTTPException(status_code=400, detail="No leads found for target selection")

    # Check for connected Evolution session
    session_to_use = req.session_name if req.session_name else None
    if not session_to_use:
        session_to_use = get_user_evolution_session(db, current_user.id)
    
    if not session_to_use:
        raise HTTPException(
            status_code=400, 
            detail="No connected WhatsApp session. Please connect WhatsApp in Broadcast tab first."
        )

    broadcast_stop_event.clear()
    background_tasks.add_task(
        broadcast_worker, 
        current_user.id, 
        leads, 
        req.template, 
        req.min_delay, 
        req.max_delay, 
        req.rotate,
        session_to_use
    )
    
    return {
        "status": "success", 
        "message": f"Broadcast started for {len(leads)} leads via {session_to_use}",
        "session": session_to_use,
        "total_leads": len(leads)
    }

@app.post("/broadcast/stop")
def stop_broadcast(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    global broadcast_stop_event
    broadcast_stop_event.set()
    
    # Validasi dan update status di DB
    campaign = db.query(models.BroadcastCampaign).filter(
        models.BroadcastCampaign.owner_id == current_user.id,
        models.BroadcastCampaign.status == "running"
    ).first()
    
    if campaign:
        campaign.status = "stopped"
        db.commit()
        
    return {"status": "success", "message": "Stopping broadcast..."}

@app.get("/broadcast/status")
def get_broadcast_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Find latest campaign
    campaign = db.query(models.BroadcastCampaign).filter(
        models.BroadcastCampaign.owner_id == current_user.id
    ).order_by(models.BroadcastCampaign.created_at.desc()).first()
    
    if not campaign:
        return {"status": "idle", "total": 0, "sent": 0, "failed": 0, "progress": 0, "logs": [], "session_used": ""}
        
    # Get recent logs
    logs = db.query(models.BroadcastLog).filter(
        models.BroadcastLog.campaign_id == campaign.id
    ).order_by(models.BroadcastLog.id.desc()).limit(20).all()
    
    formatted_logs = []
    for log in reversed(logs):
        icon = "✅" if log.status == "sent" else "❌" if log.status == "failed" else "⏳"
        msg = f"{icon} {log.phone}"
        if log.error_message:
             msg += f": {log.error_message}"
        formatted_logs.append(msg)
        
    # Calculate progress
    progress = 0
    if campaign.total_recipients > 0:
        progress = int(((campaign.success_count + campaign.failed_count) / campaign.total_recipients) * 100)
    elif campaign.status == "completed":
        progress = 100
        
    return {
        "status": campaign.status,
        "total": campaign.total_recipients,
        "sent": campaign.success_count,
        "failed": campaign.failed_count,
        "progress": progress,
        "logs": formatted_logs,
        "session_used": campaign.session_used or ""
    }

# ... (Rest remains same)

def telegram_listener():
    """Polls Telegram for new photos and links them to the correct user via telegram_chat_id"""
    print("🤖 Telegram Multi-User Listener Started...")
    offset = 0
    
    while True:
        db = database.SessionLocal()
        try:
            # Load token from environment variable (highest priority)
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            
            # Fallback to config file if not in env
            if not token and os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    token = config.get("TELEGRAM_BOT_TOKEN")

            if not token:
                time.sleep(10)
                continue
                
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset + 1}&timeout=20"
            resp = requests.get(url, timeout=25)
            data = resp.json()
            
            if data.get("ok"):
                for result in data.get("result", []):
                    update_id = result.get("update_id")
                    offset = max(offset, update_id)
                    
                    message = result.get("message", {})
                    chat_id = str(message.get("chat", {}).get("id"))
                    
                    # Find user by telegram_chat_id
                    user = db.query(models.User).filter(models.User.telegram_chat_id == chat_id).first()
                    
                    if not user:
                        # For now, just notify that it's unlinked.
                        if "photo" in message or "text" in message:
                            send_telegram_message(token, chat_id, f"⚠️ Akun Anda belum terhubung. Silakan masukkan Chat ID ini di Dashboard Velora Blast: {chat_id}")
                        continue

                    # Check for Photo
                    if "photo" in message:
                        # RESTRICTION: Only Admin can use OCR via Telegram
                        if user.role != "admin":
                            send_telegram_message(token, chat_id, "🚫 Fitur OCR via Telegram ini khusus untuk Owner/Admin saja. Terima kasih!")
                            continue

                        print(f"📸 Photo received from {user.email}")
                        file_id = message["photo"][-1]["file_id"]
                        
                        file_info_url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
                        file_info = requests.get(file_info_url).json()
                        
                        if file_info.get("ok"):
                            file_path = file_info["result"]["file_path"]
                            download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                            img_data = requests.get(download_url).content
                            
                            # Process OCR and Save to DB for this specific user
                            numbers, count, _ = process_image_for_ocr(db, user.id, img_data, source_label="Telegram Bot")
                            
                            reply_text = f"✅ OCR Berhasil untuk {user.email}!\n\n"
                            if count > 0:
                                reply_text += f"📞 Ditemukan {count} nomor baru."
                            else:
                                reply_text += "❌ Tidak ada nomor HP yang terbaca."
                            send_telegram_message(token, chat_id, reply_text)
                            
        except Exception as e:
            print(f"Telegram Loop Error: {e}")
            time.sleep(5)
        finally:
            db.close()
        
        time.sleep(1)

# --- Auth Endpoints ---

@app.patch("/me", response_model=schemas.UserResponse)
def update_profile(
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if user_update.telegram_chat_id is not None:
        # Check if chat id is already taken
        existing = db.query(models.User).filter(models.User.telegram_chat_id == user_update.telegram_chat_id).first()
        if existing and existing.id != current_user.id:
            raise HTTPException(status_code=400, detail="Telegram Chat ID sudah digunakan akun lain.")
        current_user.telegram_chat_id = user_update.telegram_chat_id
    
    db.commit()
    db.refresh(current_user)
    return current_user

@app.post("/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Send Telegram notification
    notif_msg = f"🆕 <b>USER BARU DAFTAR!</b>\n\n📧 Email: {new_user.email}\n📅 Waktu: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    send_business_notification(notif_msg)
    
    return new_user

@app.post("/login", response_model=schemas.Token)
def login_for_access_token(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if not user or not auth.verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# Dependency to get current user
@app.get("/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# --- Endpoints ---

@app.on_event("startup")
def startup_event():
    # Seed Admin User
    db = database.SessionLocal()
    try:
        admin_email = "nawawimahinutsman@gmail.com"
        admin = db.query(models.User).filter(models.User.email == admin_email).first()
        if not admin:
            hashed_pw = auth.get_password_hash("Mahin_123")
            admin_user = models.User(
                email=admin_email, 
                hashed_password=hashed_pw, 
                role="admin", 
                subscription_status="active"
            )
            db.add(admin_user)
            db.commit()
            print(f"✅ Admin user {admin_email} seeded.")
    except Exception as e:
        print(f"❌ seeding error: {e}")
    finally:
        db.close()

    # Start Telegram Listener in Background
    t = threading.Thread(target=telegram_listener, daemon=True)
    t.start()


@app.post("/upload-ocr")
async def upload_ocr_image(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        contents = await file.read()
        unique_numbers, count, text = process_image_for_ocr(db, current_user.id, contents, source_label="OCR Upload")
             
        # Send to Telegram if Configured
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not token and os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    token = config.get("TELEGRAM_BOT_TOKEN")
            
            caption = f"✅ OCR Success (User: {current_user.email})!\nFound {count} numbers."
            send_to_telegram(contents, caption, {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID")})
        except: pass
            
        return {
            "status": "success", 
            "extracted_count": count, 
            "extracted_numbers": list(unique_numbers),
            "raw_text_preview": text[:200] + "..."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/sync-master")
def sync_master_data(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Reads all scraper CSV results and merges them into Master Data Table for current user"""
    data_dir = "."
    new_records = []
    
    try:
        folders = [f for f in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, f)) and not f.startswith(".")]
        for folder in folders:
            if folder in ["Scraping Tools-BE", "Scraping Tools-FE", ".venv"]: continue
            
            folder_path = os.path.join(data_dir, folder)
            files = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
            
            for file in files:
                file_path = os.path.join(folder_path, file)
                try:
                    df = pd.read_csv(file_path)
                    if 'Phone' in df.columns:
                        for _, row in df.iterrows():
                            phone = str(row['Phone']).strip()
                            if phone and phone.lower() not in ["n/a", "nan"]:
                                new_records.append({
                                    "Phone": phone,
                                    "Name": row.get('Name', '-'),
                                    "Business": row.get('Name', '-'),
                                    "Source": f"Scraper ({folder})",
                                    "Status": "Pending"
                                })
                except Exception as ex:
                    print(f"Error reading {file}: {ex}")

        if new_records:
            append_to_master(db, current_user.id, new_records)
            
        return {"status": "success", "synced_count": len(new_records)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/master-data", response_model=List[schemas.LeadResponse])
def get_master_data(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Lead).filter(models.Lead.owner_id == current_user.id).all()

# --- Midtrans & Subscription Endpoints ---

@app.post("/subscription/create-payment")
def create_payment(payment_req: schemas.PaymentRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Get package from database
    package = db.query(models.Package).filter(models.Package.name == payment_req.package_name).first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    
    amount = package.price
    order_id = f"VB-{current_user.id}-{package.name}-{int(time.time())}"
    
    # Simpan transaksi ke DB
    transaction = models.MidtransTransaction(
        order_id=order_id,
        gross_amount=amount,
        transaction_status="pending",
        owner_id=current_user.id
    )
    db.add(transaction)
    
    # Update user's package_type
    current_user.package_type = package.name
    db.commit()
    
    # Request ke Midtrans
    res = midtrans_client.create_transaction(
        order_id=order_id,
        amount=amount,
        item_name=f"{package.display_name} - {package.duration_days} Hari",
        customer_email=current_user.email
    )
    
    return res

@app.post("/payment/webhook")
async def midtrans_webhook(webhook_data: schemas.MidtransWebhook, db: Session = Depends(get_db)):
    # Verifikasi signature
    is_valid = midtrans_client.verify_signature(
        webhook_data.order_id,
        webhook_data.status_code,
        webhook_data.gross_amount,
        webhook_data.signature_key
    )
    
    if not is_valid:
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Update status transaksi
    transaction = db.query(models.MidtransTransaction).filter(models.MidtransTransaction.order_id == webhook_data.order_id).first()
    if transaction:
        transaction.transaction_status = webhook_data.transaction_status
        transaction.payment_type = webhook_data.payment_type
        
        # Jika sukses, update status langganan user
        if webhook_data.transaction_status in ["settlement", "capture"]:
            user = db.query(models.User).filter(models.User.id == transaction.owner_id).first()
            if user:
                user.subscription_status = "active"
                # Set expiry (30 hari dari sekarang)
                from datetime import timedelta
                user.expiry_date = datetime.utcnow() + timedelta(days=30)
                
                # Send Telegram notification for payment
                pkg_name = user.package_type or "basic"
                notif_msg = f"💰 <b>PEMBAYARAN BERHASIL!</b>\n\n📧 Email: {user.email}\n📦 Paket: {pkg_name.upper()}\n💵 Jumlah: Rp {int(float(webhook_data.gross_amount)):,}\n🔖 Order ID: {webhook_data.order_id}\n📅 Waktu: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                send_business_notification(notif_msg)
                
        db.commit()
        
    return {"message": "Webhook processed"}

# --- Owner Dashboard Endpoints ---

@app.get("/admin/users", response_model=List[schemas.UserResponse])
def admin_list_users(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return db.query(models.User).all()

@app.get("/admin/transactions", response_model=List[schemas.MidtransTransactionResponse])
def admin_list_transactions(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return db.query(models.MidtransTransaction).all()

# --- Package Endpoints ---

@app.on_event("startup")
def seed_packages():
    """Seed default packages on startup if they don't exist"""
    db = next(get_db())
    try:
        # Check if packages exist
        existing = db.query(models.Package).count()
        if existing == 0:
            packages = [
                models.Package(
                    name="basic",
                    display_name="Paket Basic",
                    price=150000,
                    max_senders=1,
                    duration_days=30
                ),
                models.Package(
                    name="advance",
                    display_name="Paket Advance",
                    price=350000,
                    max_senders=4,
                    duration_days=30
                )
            ]
            for pkg in packages:
                db.add(pkg)
            db.commit()
            print("✅ Default packages seeded successfully!")
    except Exception as e:
        print(f"⚠️ Package seeding error: {e}")
    finally:
        db.close()

@app.get("/packages", response_model=List[schemas.PackageResponse])
def list_packages(db: Session = Depends(get_db)):
    """List all active packages (public endpoint)"""
    return db.query(models.Package).filter(models.Package.is_active == True).all()

@app.get("/admin/packages", response_model=List[schemas.PackageResponse])
def admin_list_packages(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Admin: List all packages including inactive ones"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return db.query(models.Package).all()

@app.put("/admin/packages/{package_id}", response_model=schemas.PackageResponse)
def admin_update_package(package_id: int, pkg_data: schemas.PackageUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Admin: Update package details (price, max_senders, etc.)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    
    for key, value in pkg_data.dict(exclude_unset=True).items():
        setattr(package, key, value)
    
    db.commit()
    db.refresh(package)
    return package

@app.post("/admin/packages", response_model=schemas.PackageResponse)
def admin_create_package(pkg_data: schemas.PackageCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Admin: Create a new package"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check if package name already exists
    existing = db.query(models.Package).filter(models.Package.name == pkg_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Package with this name already exists")
    
    package = models.Package(**pkg_data.dict())
    db.add(package)
    db.commit()
    db.refresh(package)
    return package

@app.delete("/admin/packages/{package_id}")
def admin_delete_package(package_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Admin: Delete a package"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    
    db.delete(package)
    db.commit()
    return {"message": f"Package '{package.name}' deleted successfully"}

# --- Owner Account Constants ---
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "nawawimahinutsman@gmail.com")

def is_owner_account(user: models.User) -> bool:
    """Check if user is the owner account (always active)"""
    return user.email == OWNER_EMAIL

def check_subscription(user: models.User) -> bool:
    """Check if user has active subscription or is owner"""
    if is_owner_account(user):
        return True
    if user.role == "admin":
        return True
    return user.subscription_status == "active"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
