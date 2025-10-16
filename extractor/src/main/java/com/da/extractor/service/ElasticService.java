package com.da.extractor.service;


import co.elastic.clients.elasticsearch.ElasticsearchClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class ElasticService {

    @Autowired
    ElasticsearchClient client;

    public String getClusterInfo() throws Exception {

        return client.info().toString();
    }

}
