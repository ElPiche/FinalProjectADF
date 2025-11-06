package com.da.extractor.pipeline;

import com.da.extractor.entity.serie.Metadata;
import com.da.extractor.entity.serie.SeriesElement;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class FilterService {


    public List<SeriesElement> applyFilter(List<Map<String, Object>> data, PipeMetadata metadata) throws IllegalArgumentException{

        List<SeriesElement> seriesElements = new ArrayList<>();

        if(!data.stream().allMatch(res ->
                res.containsKey("timestamp") || res.containsKey("es_timestamp"))){

            throw new IllegalArgumentException("Query result has one or more rows without the required " +
                    "\"timestamp\" field");
        }

        for(Map<String, Object> row : data){
            for(String observedValue : metadata.getObservedValues()){
                if(row.containsKey(observedValue)){
                    Date ts =(Date) row.getOrDefault("es_timestamp", row.get("timestamp"));

                    Long val = Optional.of((Long) row.get(observedValue))
                            .orElseThrow(() -> new IllegalArgumentException("Observed value " + observedValue +
                                    "didn't provided for series at timestamp: " + ts.toString()));

                    seriesElements.add(new SeriesElement(null,
                            val,
                            ts,
                            new Metadata(metadata.getKbId(), observedValue, (short) metadata.getMode().ordinal()))
                    );
                }
            }
        }

//        IO.println("Filtered " + series.size() + " series for KB: " + kbId + " with mode: " + mode.ordinal());

        return seriesElements;
    }
}
