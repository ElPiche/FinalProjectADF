package com.da.extractor.service;

import co.elastic.clients.json.JsonpMapper;

import com.da.extractor.entity.KbMongo;
import com.da.extractor.repository.KbConfigRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.List;

@Service
public class KbConfigReaderService {

    @Autowired
    KbConfigRepository kbConfigRepository;

    @Autowired
    JsonpMapper jsonpMapper;

    public List<KbMongo> listAll() throws IllegalArgumentException, IOException
    {
        return kbConfigRepository.findAll();
    }

    public KbMongo getByKbId(String kbId) {
        return kbConfigRepository.findByKbConfig_KbId(kbId)
                .orElseThrow(() -> new IllegalArgumentException("KB Config no encontrada: " + kbId));
    }

}
