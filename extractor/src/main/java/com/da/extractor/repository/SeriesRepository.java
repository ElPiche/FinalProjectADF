package com.da.extractor.repository;

import com.da.extractor.entity.serie.SeriesElement;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface SeriesRepository extends MongoRepository<SeriesElement, String> {

}
