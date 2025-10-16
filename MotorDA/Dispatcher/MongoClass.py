import pymongo
from typing import Any, Dict, List, Optional

class MongoDispatcher:

    def __init__(self, mongo_uri, db_name, collection_name):

        try:

            self.client = pymongo.MongoClient(mongo_uri)

            self.db = self.client[db_name]

            self.collection = self.db[collection_name]

            print(f"Connected to MongoDB database: {db_name}, collection: {collection_name}")

        except Exception as e:

            print(f"Error connecting to MongoDB: {e}")

    def extract_data(self, query=None):

        if query is None:

            query = {}

        try:

            data = list(self.collection.find(query))

            return data
        
        except Exception as e:

            print(f"❌ Error al extraer datos: {e}")
            return []

    def get_record_by_id(self, record_id):
        try:
            
            record = self.collection.find_one({"KB_Config.Id": record_id})
           
            return record

        except Exception as e:
            print(f"❌ Error al obtener el registro: {e}")
            return None