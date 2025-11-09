package com.da.anomaliesinsightsmodule.service;

import co.elastic.clients.elasticsearch._types.OpType;
import co.elastic.clients.elasticsearch.core.IndexResponse;
import com.da.anomaliesinsightsmodule.dto.DocumentDto;
import com.da.anomaliesinsightsmodule.entity.IndexKbIdMapping;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Optional;


@Service
public class InsightsService {

    @Autowired
    ElasticsearchService elasticsearchService;

    @Autowired
    private KibanaService kibanaService;

    public void createKbMapping(IndexKbIdMapping kbIdMapping) throws Exception {

        //Crear mapeo
        elasticsearchService.createKbMapping(kbIdMapping);

        //crear indice
        elasticsearchService.createIndex(kbIdMapping.getIndexName());

        //crear dataview
        kibanaService.createDataView(kbIdMapping.getIndexName());

    }

    public IndexResponse uploadDocument(String kbId, DocumentDto doc) throws Exception {

        //Obtener nombre de indice atraves de mapeo
        Optional<IndexKbIdMapping> mappingOpt = elasticsearchService.getKbIdMapping(kbId);

        IndexKbIdMapping mapping = mappingOpt
                .orElseThrow(() -> new IllegalStateException("kb mapping not found: " + kbId));

        //subir documento.
        return elasticsearchService.indexAnomalyDocument(mapping.getIndexName(), doc);
    }

}
