package com.da.extractor.service.pipeline;

import co.elastic.clients.elasticsearch.sql.Column;
import co.elastic.clients.elasticsearch.sql.QueryResponse;
import co.elastic.clients.json.JsonData;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.entity.serie.SerieElement;
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
            QueryResponse response = elasticService.executeQuery(elasticQuery, cursor);

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

            List<SerieElement> series = filterService.applyFilter(
                    data,
                    List.of("status_code_5xx_counter"),
                    Mode.TRAINING,
                    "1fbb07a4-favf-46ed-9eae-b8d1289c570c"
            );

            loaderService.loadSeries(series);


        }while (cursor != null);
    }

}
