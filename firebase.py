from firebase_admin import credentials, firestore, initialize_app, storage

cred = credentials.Certificate("service-account-key.json")
initialize_app(cred, options={"storageBucket": "waha-ai-timestamper-4265a.appspot.com"})
bucket = storage.bucket()
db = firestore.client()
