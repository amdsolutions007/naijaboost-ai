from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"Status": "NaijaBoost AI Backend is Online"}