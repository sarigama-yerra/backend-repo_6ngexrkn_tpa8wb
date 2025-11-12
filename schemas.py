"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List

# Voting system schemas

class Voter(BaseModel):
    """
    Voters collection schema
    Collection name: "voter"
    """
    aadhaar: str = Field(..., min_length=8, description="Aadhaar number (simulated)")
    name: str = Field(..., description="Full name")
    phone: str = Field(..., min_length=8, description="Phone number for OTP")
    face_hash: Optional[str] = Field(None, description="SHA256 hash of face image for verification")
    has_voted: bool = Field(False, description="Whether the voter has already cast a vote")

class Candidate(BaseModel):
    """
    Candidates collection schema
    Collection name: "candidate"
    """
    name: str = Field(..., description="Candidate name")
    party: Optional[str] = Field(None, description="Party or affiliation")

class Vote(BaseModel):
    """
    Votes collection schema
    Collection name: "vote"
    """
    aadhaar: str = Field(..., description="Aadhaar of voter who cast the vote")
    candidate_id: str = Field(..., description="ID of the candidate voted for")

class OtpRequest(BaseModel):
    """
    OTP requests collection schema
    Collection name: "otprequest"
    """
    aadhaar: str = Field(..., description="Voter Aadhaar")
    otp: str = Field(..., description="One-time password (simulated)")
    expires_at: int = Field(..., description="Unix timestamp for expiry")
    verified: bool = Field(False, description="Whether OTP was verified")

class Verification(BaseModel):
    """
    Temporary verification flags
    Collection name: "verification"
    """
    aadhaar: str = Field(...)
    otp_verified_at: Optional[int] = Field(None)
    face_verified_at: Optional[int] = Field(None)

# Example schemas kept for reference (not used by app)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
