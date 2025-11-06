package com.da.extractor.pipeline;

import com.da.extractor.entity.serie.SeriesElement;

import java.util.List;
import java.util.Map;

public class DataPipeline {
    private final ExtractorService extractorService;
    private final FilterService filterService;
    private final LoaderService loaderService;

    private final PipeMetadata metadata;

    public DataPipeline(ExtractorService extractorService,
                        FilterService filterService,
                        LoaderService loaderService,
                        PipeMetadata metadata) {
        this.extractorService = extractorService;
        this.filterService = filterService;
        this.loaderService = loaderService;
        this.metadata = metadata;
    }

    public void process(String query) throws Exception{
        extractorService.extractData(query, this::processPage);
    }

    private void processPage(List<Map<String, Object>> data) {
        List<SeriesElement> series = filterService.applyFilter(data, metadata);
        loaderService.loadSeries(series);
    }
}
