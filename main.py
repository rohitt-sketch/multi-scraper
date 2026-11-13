from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import quote
import sqlite3
import os
import hashlib
import hmac
from scrapers import youtube, tiktok

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Yahan apna asli email daalo, sirf yahi admin hoga
ADMIN_EMAIL = "joshirohitt@gmail.com"
DB_NAME = "scraper_v2.db"
SECRET_KEY = os.getenv("SESSION_SECRET", "multi-scraper-default-session-key")


# --- Security Helpers ---
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


# --- Database Setup ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password TEXT,
                status TEXT DEFAULT 'pending'
            )"""
        )
        conn.commit()


init_db()


# 1. Login/Register Page (Home)
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")


# 2. Register Route
@app.post("/register")
async def register(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    hashed_pw = hash_password(password)
    status = "approved" if email == ADMIN_EMAIL else "pending"

    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO users (email, password, status) VALUES (?, ?, ?)",
                (email, hashed_pw, status),
            )
            conn.commit()

        if status == "approved":
            response = RedirectResponse(url="/dashboard", status_code=303)
            response.set_cookie(key="user_session", value=sign_session(email), httponly=True, samesite="lax")
            return response
        else:
            msg = quote("Account ban gaya! Ab Admin approval ka wait karein.")
            return RedirectResponse(url=f"/?success={msg}", status_code=303)

    except sqlite3.IntegrityError:
        msg = quote("Yeh email pehle se registered hai!")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)


# 3. Login Route
@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT password, status FROM users WHERE email = ?", (email,))
        user = c.fetchone()

    if user and (user[0] == hash_password(password) or user[0] == password):
        status = user[1]
        if status == "pending":
            msg = quote("Aapka account abhi approve nahi hua hai. Admin se sampark karein.")
            return RedirectResponse(url=f"/?error={msg}", status_code=303)

        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=sign_session(email), httponly=True, samesite="lax")
        return response
    else:
        msg = quote("Galat email ya password!")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)


# 4. Secure Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user_email = get_current_user(request)
    if not user_email:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"user": user_email, "is_admin": user_email == ADMIN_EMAIL},
    )


# 5. Logout Route
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_session")
    return response


# 6. ADMIN APPROVAL PAGE
@app.get("/admin/approvals", response_class=HTMLResponse)
async def admin_approvals(request: Request):
    user_email = get_current_user(request)
    if user_email != ADMIN_EMAIL:
        return RedirectResponse(url="/dashboard", status_code=303)

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT email, status FROM users WHERE email != ?", (ADMIN_EMAIL,))
        all_users = c.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"users": all_users},
    )


# 7. APPROVE USER ACTION
@app.post("/admin/approve")
async def approve_user(request: Request, target_email: str = Form(...)):
    user_email = get_current_user(request)
    if user_email != ADMIN_EMAIL:
        return RedirectResponse(url="/dashboard", status_code=303)

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET status = 'approved' WHERE email = ?", (target_email,))
        conn.commit()

    return RedirectResponse(url="/admin/approvals", status_code=303)


# ==========================================
# SCRAPER API ROUTES
# ==========================================
@app.post("/scrape_youtube")
def api_scrape_youtube(request: Request, urls: str = Form(...)):
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized. Please login again."}, status_code=401)
    try:
        return {"results": youtube.scrape_data(urls)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/scrape_tiktok")
def api_scrape_tiktok(request: Request, urls: str = Form(...)):
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized. Please login again."}, status_code=401)
    try:
        return {"results": tiktok.scrape_data(urls)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/check_status")
def api_check_status(request: Request, urls: str = Form(...)):
    if not get_current_user(request):
        return JSONResponse({"error": "Unauthorized. Please login again."}, status_code=401)
    try:
        return {"results": tiktok.check_status(urls)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)