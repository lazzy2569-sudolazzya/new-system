from fastapi import FastAPI

from app.routers import auth, categories, locations, products, stock, users

app = FastAPI(title="ERP API")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(categories.router)
app.include_router(locations.router)
app.include_router(products.router)
app.include_router(stock.router)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}
