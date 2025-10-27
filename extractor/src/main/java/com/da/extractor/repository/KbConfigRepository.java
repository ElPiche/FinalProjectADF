package com.da.extractor.repository;

import com.da.extractor.entity.kb.KbMongo;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface KbConfigRepository  extends MongoRepository<KbMongo, String> {

    //Optional<KbMongo> findKbConfigById(String id);

    //Optional<KbMongo> findByKbConfig_Id(String kbId);
    Optional<KbMongo> findByKbConfig_KbId(String kbId);
    //Optional<List<KbMongo>> findAllKbConfigDto();
}
