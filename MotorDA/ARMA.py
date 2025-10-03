from pymongo import MongoClient

uri = "mongodb://admin:1q2w3E*@localhost:27017/"
client = MongoClient(uri)

try:

# start example code here

# end example code here
    client.admin.command("ping")

    print("Connected successfully")


    database = client["logsdb"]
    collection = database["grouped_response_code"]# other application code

    results = collection.find({})

    for document in results:
        print(" ")
        print(" ")
        print(document)

    client.close()

except Exception as e:

    raise Exception("The following error occurred: ", e)