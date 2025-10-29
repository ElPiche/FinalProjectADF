package com.da.extractor.service;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import jakarta.annotation.PostConstruct;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@Service
public class KbConfigReaderService {

    private final MongoTemplate mongoTemplate;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();


    public KbConfigReaderService(@Qualifier("knowledgeBaseMongoTemplate") MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @PostConstruct
    void start() {
        executor.submit(this::runStream);
    }

    private void runStream () {
        MongoCollection<Document> collection  = mongoTemplate.getCollection("kb_configs");
        List<Bson> pipeline = List.of(Aggregates.match(Filters.in("operationType", "insert", "update", "replace")));

        collection.watch(pipeline).forEach(document -> {
            IO.println("Change of type " + document.getOperationTypeString() + " detected in kb_configs collection");
        });
    }
}
