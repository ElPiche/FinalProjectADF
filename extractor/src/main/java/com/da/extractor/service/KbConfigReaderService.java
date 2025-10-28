package com.da.extractor.service;

import co.elastic.clients.json.JsonpMapper;

import com.da.extractor.entity.kb.KbMongo;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.List;

@Service
public class KbConfigReaderService {

    @Autowired
    JsonpMapper jsonpMapper;

    @Autowired
    StreamingModeService streamingModeService;

    @Autowired
    BatchModeService batchModeService;

    private final MongoTemplate mongoTemplate;

    public KbConfigReaderService(@Qualifier("knowledgeBaseMongoTemplate") MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

//    public List<KbMongo> listAll() throws IllegalArgumentException, IOException
//    {
//        return kbConfigRepository.findAll();
//    }
//
//    public KbMongo getByKbId(String kbId) {
//        return kbConfigRepository.findByKbConfig_KbId(kbId)
//                .orElseThrow(() -> new IllegalArgumentException("KB Config no encontrada: " + kbId));
//    }

//    public void getAllConfigs() throws Exception {
//
//        List<KbMongo> kbMongoList = listAll();
//
//        for (KbMongo kbMongo : kbMongoList) {
//
//            streamingModeService.executeConfiguration(kbMongo);
//
//            batchModeService.executeConfiguration(kbMongo);
//
//        }
//
//    }

}
