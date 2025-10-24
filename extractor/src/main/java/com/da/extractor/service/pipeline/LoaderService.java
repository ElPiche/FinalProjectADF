package com.da.extractor.service.pipeline;

import com.da.extractor.entity.serie.Serie;
import com.da.extractor.repository.SeriesRepository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class LoaderService {
    final SeriesRepository seriesRepository;

    public LoaderService(SeriesRepository seriesRepository) {
        this.seriesRepository = seriesRepository;
    }

    void loadSeries(List<Serie> series){
        List<Serie> savedSeries = seriesRepository.saveAll(series);

        System.out.println("Loaded " + savedSeries.size() + " series into the database.");
    }
}
