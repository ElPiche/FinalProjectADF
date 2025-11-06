package com.da.extractor.pipeline;

import com.da.extractor.entity.serie.SeriesElement;
import com.da.extractor.entity.training.TrainConfig;
import com.da.extractor.repository.anomaly_detection.SeriesRepository;
import com.da.extractor.repository.anomaly_detection.TrainingConfigRepository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class LoaderService {
    final private SeriesRepository seriesRepository;
    final private TrainingConfigRepository trainingConfigRepository;

    public LoaderService(SeriesRepository seriesRepository, TrainingConfigRepository trainingConfigRepository) {
        this.seriesRepository = seriesRepository;
        this.trainingConfigRepository = trainingConfigRepository;
    }

    public void loadSeries(List<SeriesElement> series){
        List<SeriesElement> savedSeries = seriesRepository.saveAll(series);

        System.out.println("Loaded " + savedSeries.size() + " series into the database.");
    }
}
