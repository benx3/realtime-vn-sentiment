import os, torch
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from transformers import AutoTokenizer, AutoModelForSequenceClassification

app = FastAPI()
MODEL_DIR = os.getenv("MODEL_DIR","/app/models/phobert-sentiment-best")
MODEL_ID = os.getenv("MODEL_ID","wonrax/phobert-base-vietnamese-sentiment")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Load tokenizer/model (prefer local MODEL_DIR if present)
try:
    tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=False)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
except Exception:
    tok = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=False)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)

model.to(DEVICE).eval()

class PredictIn(BaseModel):
    texts: List[str]
    product_id: str | None = None
    category_id: str | None = None

@app.get("/healthz")
def healthz():
    return {"device": DEVICE, "model": MODEL_ID}

@app.post("/predict")
def predict(p: PredictIn):
    enc = tok(p.texts, truncation=True, padding=True, max_length=160, return_tensors="pt")
    enc = {k:v.to(DEVICE) for k,v in enc.items()}
    with torch.no_grad():
        logits = model(**enc).logits
        proba = torch.softmax(logits, dim=-1).cpu().tolist()
        pred = logits.argmax(dim=-1).cpu().tolist()
    return {"pred": pred, "proba": proba}
