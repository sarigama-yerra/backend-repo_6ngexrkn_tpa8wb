import os
import time
import base64
import hashlib
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents

app = FastAPI(title="Voting Simulation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Models (request/response) ----------

class SendOtpRequest(BaseModel):
    aadhaar: str

class VerifyOtpRequest(BaseModel):
    aadhaar: str
    otp: str

class VerifyFaceRequest(BaseModel):
    aadhaar: str
    image_base64: str  # "data:image/png;base64,..." or raw base64

class CastVoteRequest(BaseModel):
    aadhaar: str
    candidate_id: str

# ---------- Helpers ----------

def _now_ts() -> int:
    return int(time.time())


def _collection(name: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    return db[name]


def _sha256_of_base64_image(image_base64: str) -> str:
    # strip prefix if present
    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image")
    return hashlib.sha256(image_bytes).hexdigest()


def _ensure_seed_data():
    """Create a few demo candidates and voters if collections are empty"""
    voters = _collection("voter")
    candidates = _collection("candidate")

    if candidates.count_documents({}) == 0:
        candidates.insert_many([
            {"name": "Alice Johnson", "party": "Unity Party", "created_at": time.time(), "updated_at": time.time()},
            {"name": "Bob Singh", "party": "Progress Alliance", "created_at": time.time(), "updated_at": time.time()},
            {"name": "Carla Gomez", "party": "Green Front", "created_at": time.time(), "updated_at": time.time()},
        ])

    if voters.count_documents({}) == 0:
        voters.insert_many([
            {"aadhaar": "111122223333", "name": "Ravi Kumar", "phone": "+910000000001", "face_hash": None, "has_voted": False, "created_at": time.time(), "updated_at": time.time()},
            {"aadhaar": "444455556666", "name": "Anita Sharma", "phone": "+910000000002", "face_hash": None, "has_voted": False, "created_at": time.time(), "updated_at": time.time()},
            {"aadhaar": "777788889999", "name": "Mohit Patel", "phone": "+910000000003", "face_hash": None, "has_voted": False, "created_at": time.time(), "updated_at": time.time()},
        ])


@app.on_event("startup")
async def startup_event():
    if db is not None:
        _ensure_seed_data()


# ---------- Basic ----------
@app.get("/")
def read_root():
    return {"message": "Voting Simulation API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# ---------- Voting domain ----------

@app.get("/candidates")
def list_candidates():
    coll = _collection("candidate")
    docs = list(coll.find({}, {"name": 1, "party": 1}))
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"candidates": docs}


@app.post("/auth/send-otp")
def send_otp(payload: SendOtpRequest):
    voter = _collection("voter").find_one({"aadhaar": payload.aadhaar})
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")

    # Generate demo OTP
    otp = str(int(time.time()) % 900000 + 100000)  # pseudo 6-digit
    expires_at = _now_ts() + 300  # 5 minutes

    _collection("otprequest").insert_one({
        "aadhaar": payload.aadhaar,
        "otp": otp,
        "expires_at": expires_at,
        "verified": False,
        "created_at": time.time(),
        "updated_at": time.time(),
    })

    # In real life we'd send SMS. For demo, return the OTP for display
    masked = otp[:2] + "****"
    return {"message": "OTP sent (demo)", "otp_demo": otp, "masked": masked, "expires_at": expires_at, "voter_name": voter.get("name")}


@app.post("/auth/verify-otp")
def verify_otp(payload: VerifyOtpRequest):
    req = _collection("otprequest").find_one({
        "aadhaar": payload.aadhaar,
        "otp": payload.otp
    }, sort=[("created_at", -1)])
    if not req:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if req.get("expires_at", 0) < _now_ts():
        raise HTTPException(status_code=400, detail="OTP expired")

    _collection("otprequest").update_one({"_id": req["_id"]}, {"$set": {"verified": True, "updated_at": time.time()}})

    # Mark verification
    ver = _collection("verification").find_one({"aadhaar": payload.aadhaar})
    if ver:
        _collection("verification").update_one({"_id": ver["_id"]}, {"$set": {"otp_verified_at": _now_ts(), "updated_at": time.time()}})
    else:
        _collection("verification").insert_one({"aadhaar": payload.aadhaar, "otp_verified_at": _now_ts(), "face_verified_at": None, "created_at": time.time(), "updated_at": time.time()})

    return {"message": "OTP verified"}


@app.post("/auth/verify-face")
def verify_face(payload: VerifyFaceRequest):
    voter = _collection("voter").find_one({"aadhaar": payload.aadhaar})
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")

    face_hash = _sha256_of_base64_image(payload.image_base64)

    # Enroll if first time; verify if already enrolled
    if voter.get("face_hash") is None:
        _collection("voter").update_one({"_id": voter["_id"]}, {"$set": {"face_hash": face_hash, "updated_at": time.time()}})
        enrolled = True
        verified = True
    else:
        enrolled = False
        verified = (voter.get("face_hash") == face_hash)

    if not verified:
        raise HTTPException(status_code=400, detail="Face does not match. Please try again.")

    ver = _collection("verification").find_one({"aadhaar": payload.aadhaar})
    if ver:
        _collection("verification").update_one({"_id": ver["_id"]}, {"$set": {"face_verified_at": _now_ts(), "updated_at": time.time()}})
    else:
        _collection("verification").insert_one({"aadhaar": payload.aadhaar, "otp_verified_at": None, "face_verified_at": _now_ts(), "created_at": time.time(), "updated_at": time.time()})

    return {"message": "Face verified", "enrolled": enrolled}


@app.get("/status/{aadhaar}")
def status(aadhaar: str):
    voter = _collection("voter").find_one({"aadhaar": aadhaar})
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")
    ver = _collection("verification").find_one({"aadhaar": aadhaar})
    return {
        "aadhaar": aadhaar,
        "name": voter.get("name"),
        "has_voted": bool(voter.get("has_voted", False)),
        "otp_verified": bool(ver and ver.get("otp_verified_at")),
        "face_verified": bool(ver and ver.get("face_verified_at")),
    }


@app.post("/vote")
def cast_vote(payload: CastVoteRequest):
    voter = _collection("voter").find_one({"aadhaar": payload.aadhaar})
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")
    if voter.get("has_voted"):
        raise HTTPException(status_code=400, detail="Voter has already cast a vote")

    ver = _collection("verification").find_one({"aadhaar": payload.aadhaar})
    if not ver or not ver.get("otp_verified_at") or not ver.get("face_verified_at"):
        raise HTTPException(status_code=400, detail="Complete OTP and Face verification first")

    # Ensure candidate exists
    cand = _collection("candidate").find_one({"_id": {"$eq": _collection("candidate").database.client.get_default_database()["candidate"].with_options().codec_options.document_class}})
    # We can't query like that; simply check by ObjectId if valid
    from bson import ObjectId
    try:
        cand = _collection("candidate").find_one({"_id": ObjectId(payload.candidate_id)})
    except Exception:
        cand = None
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Record vote
    create_document("vote", {"aadhaar": payload.aadhaar, "candidate_id": payload.candidate_id})
    _collection("voter").update_one({"_id": voter["_id"]}, {"$set": {"has_voted": True, "updated_at": time.time()}})

    return {"message": "Vote recorded"}


@app.get("/results")
def results():
    from bson import ObjectId
    votes = _collection("vote")
    cands = _collection("candidate")

    pipeline = [
        {"$group": {"_id": "$candidate_id", "count": {"$sum": 1}}}
    ]
    agg = list(votes.aggregate(pipeline))

    # Candidate info map
    cand_map = {}
    for c in cands.find({}):
        cand_map[str(c["_id"])] = {"name": c.get("name"), "party": c.get("party")}

    out = []
    for a in agg:
        cand_id = a["_id"]
        info = cand_map.get(str(cand_id), {"name": "Unknown", "party": None})
        out.append({"candidate_id": str(cand_id), "name": info.get("name"), "party": info.get("party"), "votes": a.get("count", 0)})

    # Include zero-vote candidates
    voted_ids = {str(a["_id"]) for a in agg}
    for cid, info in cand_map.items():
        if cid not in voted_ids:
            out.append({"candidate_id": cid, "name": info.get("name"), "party": info.get("party"), "votes": 0})

    # Sort by votes desc
    out.sort(key=lambda x: x["votes"], reverse=True)
    return {"results": out}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
