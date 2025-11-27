db = db.getSiblingDB('knowledge_base');
db.kb_configs.deleteOne({name: 'Fire Test - ARMAX Request Count'});

var now = new Date();
var fromDate = new Date(now.getTime() - 72*60*60*1000);
var toDate = new Date(now.getTime() - 1*60*60*1000);

var result = db.kb_configs.insertOne({
    name: 'Fire Test - ARMAX Request Count',
    description: 'ARMAX algorithm fire test for request_count time series',
    change_flag: 0,
    elasticsearch_sql_query: 'SELECT "@timestamp" as es_timestamp, request_count, error_count, avg_response_time FROM "fire-test-armax-logs" WHERE "@timestamp" >= ' + "'" + String.fromCharCode(36) + "from'" + ' AND "@timestamp" < ' + "'" + String.fromCharCode(36) + "to'" + ' ORDER BY "@timestamp"',
    query_mode: { type: 'aggregated', timestamp_field: 'es_timestamp' },
    algorithm: {
        name: 'armax',
        parameters: [
            { dimension: 'request_count', is_active: true, metadata: [{ key: 'order', values: '[2,0,2]' }, { key: 'threshold_multiplier', values: '3.0' }] }
        ]
    },
    scheduling: {
        training_config: { type: 'static', from: fromDate.toISOString(), to: toDate.toISOString(), is_active: true },
        detection_config: { frequency: '*/1 * * * *', detection_window: 86400, is_active: true, from: fromDate.toISOString() }
    }
});
print('Inserted: ' + result.insertedId);
