__author__ = 'wasansae-ngow'

from config import Config
from pymongo import MongoClient

host = 'localhost'
port = 27017
db_name = 'my_database'
collection_name = 'intramanee_lov'
config_file_name = 'tools/stockcodeparser/lov.cfg'

# MongoDB connection
client = MongoClient(host, port)
db = client[db_name]
lov_collection = db[collection_name]

# Config file read
config_file = file(config_file_name)
conf = Config(config_file)

lov_collection.drop()
lov = []

for key in conf.keys():
    for lov_code in conf.get(key):
        if 'label' in lov_code:
            lov.append({'code': lov_code['code'], 'label': lov_code['label'],'group':key})
        else:
            lov.append({'code': lov_code['code'], 'label': lov_code['code'],'group':key})

result = lov_collection.insert(lov)
print 'Collection : ' + collection_name + ' is updated with ' + str(len(result)) + ' lov entries'