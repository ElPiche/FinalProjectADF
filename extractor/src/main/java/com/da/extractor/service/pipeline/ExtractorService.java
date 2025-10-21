package com.da.extractor.service.pipeline;

import com.da.extractor.model.PipelineConfig;
import com.da.extractor.service.ElasticService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class ExtractorService {

    @Autowired
    ElasticService elasticService;

    @Autowired
    FilterService filterService;


    public void extractData(PipelineConfig config) throws Exception {
        // Lógica para extraer datos usando ElasticService y la configuración del pipeline
        String query = config.getQueryElastic();
        Map result = elasticService.executeQuery(query);

        filterService.applyFilter(result, config);
    }

}
