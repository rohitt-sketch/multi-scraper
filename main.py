from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import quote
import hashlib
import hmac
import os
import io
import csv
import json
import libsql_client
from scrapers import youtube, tiktok, okru, dailymotion, vk, facebook, instagram, x

app = FastAPI()
templates = Jinja2Templates(directory="templates")

TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

if TURSO_URL.startswith("libsql://"):
    TURSO_URL = "https://" + TURSO_URL[len("libsql://"):]

client = libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_TOKEN)
SECRET_KEY = "my-super-secret-key-123"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def sign_session(email: str) -> str:
    sig = hmac.new(SECRET_KEY.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{email}|{sig}"

def get_current_user(request: Request):
    cookie_val = request.cookies.get("user_session")
    if not cookie_val or "|" not in cookie_val: return None
    email, sig = cookie_val.rsplit("|", 1)
    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()
    
    if hmac.compare_digest(sig, expected_sig):
        res = client.execute("SELECT email, status, is_admin FROM users WHERE email = ?", [email])
        if res.rows:
            user = res.rows[0]
            if user[1] == 'approved':
                return {"email": user[0], "is_admin": bool(user[2])}
    return None

def init_db():
    client.execute("""CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY, password TEXT, status TEXT DEFAULT 'pending', is_admin INTEGER DEFAULT 0
    )""")
    admin_email = 'joshiirohitt@gmail.com'
    admin_pass = 'WB@061329'
    res = client.execute("SELECT * FROM users WHERE email = ?", [admin_email])
    if not res.rows:
        client.execute("INSERT INTO users (email, password, status, is_admin) VALUES (?, ?, ?, ?)", 
                  [admin_email, hash_password(admin_pass), 'approved', 1])

init_db()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if get_current_user(request): return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/register")
async def register(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    try:
        client.execute("INSERT INTO users (email, password, status) VALUES (?, ?, 'pending')", [email, hash_password(password)])
        msg = quote("Registration successful! Please wait for admin approval.")
        return RedirectResponse(url=f"/?success={msg}", status_code=303)
    except Exception:
        msg = quote("This email is already registered!")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)

@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    res = client.execute("SELECT password, status FROM users WHERE email = ?", [email])
    if res.rows:
        user = res.rows[0]
        stored_password, status = user[0], user[1]
        if stored_password == hash_password(password) or stored_password == password:
            if status == 'pending':
                msg = quote("Your account is not approved yet. Please contact the admin.")
                return RedirectResponse(url=f"/?error={msg}", status_code=303)
            response = RedirectResponse(url="/dashboard", status_code=303)
            response.set_cookie(key="user_session", value=sign_session(email), httponly=True)
            return response
    msg = quote("Invalid email or password!")
    return RedirectResponse(url=f"/?error={msg}", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user_info = get_current_user(request)
    if not user_info: return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user_info["email"], "is_admin": user_info["is_admin"]})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_session")
    return response

@app.get("/admin/approvals", response_class=HTMLResponse)
async def admin_approvals(request: Request):
    user_info = get_current_user(request)
    if not user_info or not user_info["is_admin"]: return RedirectResponse(url="/dashboard", status_code=303)
    res = client.execute("SELECT email, status FROM users")
    return templates.TemplateResponse(request=request, name="admin.html", context={"users": res.rows})

@app.post("/admin/approve")
async def admin_approve(request: Request, target_email: str = Form(...)):
    user_info = get_current_user(request)
    if not user_info or not user_info["is_admin"]: return RedirectResponse(url="/dashboard", status_code=303)
    client.execute("UPDATE users SET status = 'approved' WHERE email = ?", [target_email])
    return RedirectResponse(url="/admin/approvals", status_code=303)

# ==========================================
# SCRAPER ROUTES
# ==========================================
@app.post("/scrape_youtube")
def api_scrape_youtube(request: Request, urls: str = Form(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try: return {"results": youtube.scrape_data(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/scrape_tiktok")
def api_scrape_tiktok(request: Request, urls: str = Form(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try: return {"results": tiktok.scrape_data(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/scrape_okru")
def api_scrape_okru(request: Request, urls: str = Form(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try: return {"results": okru.scrape_data(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/scrape_dailymotion")
def api_scrape_dailymotion(request: Request, urls: str = Form(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try: return {"results": dailymotion.scrape_data(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/scrape_vk")
def api_scrape_vk(request: Request, urls: str = Form(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try: return {"results": vk.check_status(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/scrape_facebook")
def api_scrape_facebook(request: Request, urls: str = Form(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try: return {"results": facebook.scrape_data(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/scrape_instagram")
def api_scrape_instagram(request: Request, urls: str = Form(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try: return {"results": instagram.scrape_data(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/scrape_x")
def api_scrape_x(request: Request, urls: str = Form(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try: return {"results": x.scrape_data(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/check_status")
def api_check_status(request: Request, urls: str = Form(...), platform: str = Form("tiktok")):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        if platform == "okru": return {"results": okru.check_status(urls)}
        elif platform == "dailymotion": return {"results": dailymotion.check_status(urls)}
        elif platform == "youtube": return {"results": youtube.check_status(urls)}
        elif platform == "vk": return {"results": vk.check_status(urls)}
        elif platform == "facebook": return {"results": facebook.check_status(urls)}
        elif platform == "instagram": return {"results": instagram.check_status(urls)}
        elif platform == "x": return {"results": x.check_status(urls)}
        else: return {"results": tiktok.check_status(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

# ==========================================
# TELEGRAM JSON PARSER ROUTES
# ==========================================
def _extract_tg_text(msg):
    text = msg.get("text", "")
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, str): parts.append(item)
            elif isinstance(item, dict) and "text" in item: parts.append(item["text"])
        return "".join(parts)
    return str(text)

def _parse_tg_json(file_contents):
    try:
        data = json.loads(file_contents)
    except Exception as e:
        return None, None, f"Invalid JSON file: {str(e)}"

    messages = []
    if isinstance(data, dict) and "messages" in data:
        messages = data["messages"]
    elif isinstance(data, list):
        messages = data
    else:
        return None, None, "JSON format not recognized. Please upload Telegram export JSON."

    if not messages:
        return None, None, "No messages found in the JSON."

    headers = ["ID", "Date", "From", "Text"]
    has_media = any("media_type" in m for m in messages)
    has_reply = any("reply_to_message_id" in m for m in messages)
    
    if has_media: headers.append("Media Type")
    if has_reply: headers.append("Reply To")

    rows = []
    for msg in messages:
        if not isinstance(msg, dict): continue
        row = [
            msg.get("id", ""),
            msg.get("date", "").replace("T", " ")[:19],
            msg.get("from", "Unknown"),
            _extract_tg_text(msg)
        ]
        if has_media: row.append(msg.get("media_type", ""))
        if has_reply: row.append(msg.get("reply_to_message_id", ""))
        rows.append(row)

    return headers, rows, None

@app.post("/api/parse_telegram")
async def parse_telegram(request: Request, file: UploadFile = File(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    contents = await file.read()
    try:
        text_content = contents.decode("utf-8")
    except:
        return JSONResponse({"error": "File must be UTF-8 encoded text."}, status_code=400)

    headers, rows, error = _parse_tg_json(text_content)
    
    if error:
        return JSONResponse({"error": error}, status_code=400)
        
    return {"headers": headers, "rows": rows}

@app.post("/api/download_telegram_csv")
async def download_telegram_csv(request: Request, file: UploadFile = File(...)):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    contents = await file.read()
    try:
        text_content = contents.decode("utf-8")
    except:
        return JSONResponse({"error": "Invalid file encoding."}, status_code=400)

    headers, rows, error = _parse_tg_json(text_content)
    
    if error:
        return JSONResponse({"error": error}, status_code=400)
        
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    csv_data = output.getvalue()
    
    return StreamingResponse(
        iter([csv_data]), 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=telegram_export.csv"}
    )