from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import quote
import hashlib
import hmac
import os
import libsql_client
from scrapers import youtube, tiktok, okru, dailymotion, vk

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ==========================================
# TURSO DATABASE CONFIGURATION
# ==========================================
# Apni keys yahan daalein (ya Render ke Environment Variables me daal dein)
TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "libsql://YOUR_DATABASE_URL_HERE")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "YOUR_TOKEN_HERE")

# Turso client banayein
client = libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN)

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
        # Turso se user check karein
        res = client.execute("SELECT email, status, is_admin FROM users WHERE email = ?", [email])
        if res.rows:
            user = res.rows[0]
            if user[1] == 'approved':
                return {"email": user[0], "is_admin": bool(user[2])}
    return None

def init_db():
    # Turso par table banayein
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
    except Exception as e:
        # Agar email pehle se hai toh error aayega
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
    users = res.rows # List of tuples
    return templates.TemplateResponse(request=request, name="admin.html", context={"users": users})

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

@app.post("/check_status")
def api_check_status(request: Request, urls: str = Form(...), platform: str = Form("tiktok")):
    if not get_current_user(request): return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        if platform == "okru": return {"results": okru.check_status(urls)}
        elif platform == "dailymotion": return {"results": dailymotion.check_status(urls)}
        elif platform == "youtube": return {"results": youtube.check_status(urls)}
        elif platform == "vk": return {"results": vk.check_status(urls)}
        else: return {"results": tiktok.check_status(urls)}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)