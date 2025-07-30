
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import os
import json

load_dotenv()

if not firebase_admin._apps:
    firebase_cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    cred = credentials.Certificate(json.loads(firebase_cred_json))
    firebase_admin.initialize_app(cred)

db = firestore.client()