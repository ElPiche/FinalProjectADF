package com.da.extractor.pipeline;

import com.da.extractor.entity.serie.Metadata;
import com.da.extractor.entity.serie.SeriesElement;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class FilterService {


    public List<SeriesElement> applyFilter(List<Map<String, Object>> data, PipeMetadata metadata) {

        List<SeriesElement> seriesElements = new ArrayList<>();

        for(Map<String, Object> row : data){
            for(String observedValue : metadata.getObservedValues()){
                if(row.containsKey(observedValue)){
                    Long val = row.get(observedValue) != null ? (Long) row.get(observedValue) : 0;
                    Date ts = (Date) row.getOrDefault("es_timestamp", row.get("timestamp"));
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
