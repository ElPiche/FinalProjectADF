package com.da.extractor.pipeline;

import org.springframework.stereotype.Component;

@Component
public class DataPipelineFactory {
    private final ExtractorService extractorService;
    private final FilterService filterService;
    private final LoaderService loaderService;

    public DataPipelineFactory(ExtractorService extractorService, FilterService filterService, LoaderService loaderService) {
        this.extractorService = extractorService;
        this.filterService = filterService;
        this.loaderService = loaderService;
    }

    public DataPipeline createPipeline(PipeMetadata metadata) {
        return new DataPipeline(extractorService, filterService, loaderService, metadata);
    }
}
