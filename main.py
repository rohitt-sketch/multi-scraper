from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import quote
import sqlite3
import os
import hashlib
import hmac
from scrapers import youtube, tiktok

# App yahan define ho raha hai
app = FastAPI()
templates = Jinja2Templates(directory="templates")

DB_NAME = "scraper_v3.db"
SECRET_KEY = "my-super-secret-key-123"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def sign_session(email: str) -> str:
    sig = hmac.new(SECRET_KEY.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{email}|{sig}"

def get_current_user(request: Request):
    cookie_val = request.cookies.get("user_session")
    if not cookie_val or "|" not in cookie_val:
        return None
    email, sig = cookie_val.rsplit("|", 1)
    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected_sig):
        return email
    return None

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT)""")
        conn.commit()

init_db()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/register")
async def register(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    hashed_pw = hash_password(password)
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_pw))
            conn.commit()
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=sign_session(email), httponly=True)
        return response
    except sqlite3.IntegrityError:
        msg = quote("Yeh email pehle se registered hai!")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)

@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE email = ?", (email,))
        user = c.fetchone()
    
    if user and (user[0] == hash_password(password) or user[0] == password):
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=sign_session(email), httponly=True)
        return response
    else:
        msg = quote("Galat email ya password!")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user_email = get_current_user(request)
    if not user_email:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user_email})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_session")
    return response

@app.post("/scrape_youtube")
def api_scrape_youtube(request: Request, urls: str = Form(...)):
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        return {"results": youtube.scrape_data(urls)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/scrape_tiktok")
def api_scrape_tiktok(request: Request, urls: str = Form(...)):
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        return {"results": tiktok.scrape_data(urls)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/check_status")
def api_check_status(request: Request, urls: str = Form(...)):
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        return {"results": tiktok.check_status(urls)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)