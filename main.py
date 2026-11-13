from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect('scraper.db')
    c = conn.cursor()
    # Users table banao agar nahi hai
    c.execute('''CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- Routes ---

# 1. Login/Register Page (Home)
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Agar pehle se logged in hai, toh direct dashboard bhej do
    if request.cookies.get("user_session"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})

# 2. Register Route
@app.post("/register")
async def register(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect('scraper.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
        conn.commit()
        conn.close()
        
        # Account ban gaya, ab direct login karke dashboard bhej do
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=email, httponly=True)
        return response
    except sqlite3.IntegrityError:
        # Agar email pehle se hai
        conn.close()
        return RedirectResponse(url="/?error=Yeh email pehle se registered hai!", status_code=303)

# 3. Login Route
@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect('scraper.db')
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    conn.close()

    if user and user[0] == password:
        # Password sahi hai
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=email, httponly=True)
        return response
    else:
        # Password galat hai
        return RedirectResponse(url="/?error=Galat email ya password!", status_code=303)

# 4. Secure Dashboard (Admin Panel)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Check karo ki user logged in hai ya nahi
    user_email = request.cookies.get("user_session")
    
    if not user_email:
        # Agar bina login ke aaya hai, toh dhakke maar ke bahar nikalo
        return RedirectResponse(url="/", status_code=303)
        
    # Agar logged in hai, toh dashboard dikhao
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user_email})

# 5. Logout Route
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_session")
    return response

# ==========================================
# YAHAN SE AAPKA PURANA SCRAPER CODE SHURU HOGA
# ==========================================
# @app.post("/scrape_youtube") ... (aapka purana code)
# @app.post("/scrape_tiktok") ... (aapka purana code)