package com.da.extractor.service.pipeline;

import com.da.extractor.entity.serie.SerieElement;
import com.da.extractor.entity.training.TrainConfig;
import com.da.extractor.repository.SeriesRepository;
import com.da.extractor.repository.TrainingConfigRepository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class LoaderService {
    final SeriesRepository seriesRepository;
    final TrainingConfigRepository trainingConfigRepository;

    public LoaderService(SeriesRepository seriesRepository, TrainingConfigRepository trainingConfigRepository) {
        this.seriesRepository = seriesRepository;
        this.trainingConfigRepository = trainingConfigRepository;
    }

    public void loadSeries(List<SerieElement> series){
        List<SerieElement> savedSeries = seriesRepository.saveAll(series);

        System.out.println("Loaded " + savedSeries.size() + " series into the database.");
    }

    public void loadTrainingConfig(TrainConfig trainConfig){
        var savedConfig = trainingConfigRepository.save(trainConfig);

        System.out.println("Loaded training config with id: " + savedConfig.getId());
    }
}
