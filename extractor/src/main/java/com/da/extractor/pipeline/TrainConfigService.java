package com.da.extractor.pipeline;

import org.springframework.stereotype.Service;

@Service
public class TrainConfigService {
    private final LoaderService loaderService;

    public TrainConfigService(LoaderService loaderService) {
        this.loaderService = loaderService;
    }



}
