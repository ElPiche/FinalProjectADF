package com.da.extractor.pipeline;

import co.elastic.clients.elasticsearch.sql.Column;
import co.elastic.clients.elasticsearch.sql.QueryResponse;
import co.elastic.clients.json.JsonData;
import com.da.extractor.service.ElasticService;
import com.da.extractor.utils.Utils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

@Service
public class ExtractorService {

    @Autowired
    ElasticService elasticService;

    public void extractData(String elasticQuery,
                            Consumer<List<Map<String, Object>>> pageProcessor) throws Exception {

        String cursor = null;
        String lastCursor;
        List<Column> columns = new ArrayList<>();

        do{
            QueryResponse response = elasticService.executeQuery(elasticQuery, cursor);

            lastCursor = cursor;
            cursor = response.cursor();

            columns = !response.columns().isEmpty() ? response.columns() : columns;
            List<List<JsonData>> rows =  response.rows();

            // Crear lista unificada
            List<Map<String, Object>> data = new ArrayList<>();

            for (List<JsonData> row : rows) {
                Map<String, Object> rowMap = new HashMap<>();
                for (int i = 0; i < columns.size(); i++) {
                    Column column = columns.get(i);

                    Object value = row.get(i).to(Utils.getClassFromString(column.type()));
                    rowMap.put(column.name(), value);
                }
                data.add(rowMap);
            }

            pageProcessor.accept(data);

        }while (cursor != null);

        if(lastCursor != null) elasticService.clearCursor(lastCursor);
    }

}
