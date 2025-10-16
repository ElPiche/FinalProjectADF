import pymongo
import json
from MongoClass import MongoDispatcher

#conexión a MongoDB KB
MongoURL = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
DBName = "logsdb"
CollectionName = "testLogsKB"

#conexión a MongoDB MotorDA pendiente
MongoURL_MotorDA = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
DBName_MotorDA = "logsDB"
CollectionName_MotorDA = "testLogsMotorDA"

#conexión a elasticSearch
ES_HOST = "http://localhost:9200"
ES_INDEX = "test_logs"

dispatcher = MongoDispatcher(MongoURL, DBName, CollectionName) #Esto arma la conexión a MongoDB

print("Documento por id:")
doc = dispatcher.get_record_by_id("8fbb07a4-f8f0-46ed-9eae-b8d4789c570c")
print(json.dumps(doc, default=str, indent=4))

#data = dispatcher.extract_data()
#for doc in data:
#    print(json.dumps(doc, default=str, indent=4))
#JSON reader extractor de config.
#switch ruteador