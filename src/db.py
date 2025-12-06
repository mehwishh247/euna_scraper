from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
MONGO_DB = os.getenv('MONGO_DB', 'euna')

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

def init_db():
    '''Initialize the db & collections'''
    if 'opportunities' not in db.list_collection_names():
        db.create_collection('opportunities')

def insert_opportunities(opps):
    '''Insert list of dicts (opps) into db'''
    init_db()
    # Optionally deduplicate here
    if opps:
        db['opportunities'].insert_many(opps)
