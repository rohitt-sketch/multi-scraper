# 2. Register Route
@app.post("/register")
async def register(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    hashed_pw = hash_password(password)

    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            # Ab status ki zaroorat nahi hai, direct approved maan lo
            c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_pw))
            conn.commit()

        # Account ban gaya, direct login karke dashboard bhej do
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=sign_session(email), httponly=True, samesite="lax")
        return response

    except sqlite3.IntegrityError:
        msg = quote("Yeh email pehle se registered hai!")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)


# 3. Login Route
@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE email = ?", (email,))
        user = c.fetchone()

    if user and (user[0] == hash_password(password) or user[0] == password):
        # Password sahi hai, direct login karo
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="user_session", value=sign_session(email), httponly=True, samesite="lax")
        return response
    else:
        msg = quote("Galat email ya password!")
        return RedirectResponse(url=f"/?error={msg}", status_code=303)