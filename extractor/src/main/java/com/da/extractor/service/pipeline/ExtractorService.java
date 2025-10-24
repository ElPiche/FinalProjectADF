package com.da.extractor.service.pipeline;

import co.elastic.clients.elasticsearch.sql.Column;
import co.elastic.clients.elasticsearch.sql.QueryResponse;
import co.elastic.clients.json.JsonData;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.entity.serie.Serie;
import com.da.extractor.model.PipelineConfig;
import com.da.extractor.service.ElasticService;
import com.da.extractor.utils.Utils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class ExtractorService {

    @Autowired
    ElasticService elasticService;

    @Autowired
    FilterService filterService;

    @Autowired
    LoaderService loaderService;


    public void extractData(String elasticQuery) throws Exception {

        String cursor = null;
        List<Column> columns = new ArrayList<>();
        int page = 1;

        do{
            QueryResponse response = elasticService.executeQuery("SELECT DATE_TRUNC('HOUR', \"@timestamp\") " +
                            "AS es_timestamp, SUM(CASE WHEN CAST(response AS INTEGER) >= 500 AND CAST(response AS INTEGER) " +
                            "< 600 THEN 1 ELSE 0 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\"" +
                            " WHERE \"@timestamp\" >= '2025-10-01T00:00:00.000Z' AND \"@timestamp\" < '2025-11-01T00:00:00.000Z' " +
                            "GROUP BY es_timestamp ORDER BY es_timestamp",
                    cursor
            );

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

//            IO.println("Unified Data Page: " + page++);
//            IO.println(data);

            List<Serie> series = filterService.applyFilter(
                    data,
                    List.of("status_code_5xx_counter"),
                    Mode.TRAINING,
                    "sample_kb_id"
            );

            loaderService.loadSeries(series);


        }while (cursor != null);
    }

}
