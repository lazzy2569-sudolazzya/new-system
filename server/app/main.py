from fastapi import FastAPI

from app.routers import auth, users

app = FastAPI(title="ERP API")

app.include_router(auth.router)
app.include_router(users.router)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}
