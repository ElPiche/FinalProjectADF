package com.da.extractor.pipeline;

import com.da.extractor.entity.serie.Metadata;
import com.da.extractor.entity.serie.SeriesElement;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class FilterService {

    public List<SeriesElement> applyFilter(List<Map<String, Object>> data, PipeMetadata metadata) {

        List<SeriesElement> seriesElements = new ArrayList<>();
        String timestampField = metadata.getTimestampField();

        for(Map<String, Object> row : data){
            for(String observedValue : metadata.getObservedValues()){
                if(row.containsKey(observedValue)){
                    var val = (double) row.get(observedValue);
                    Date ts = (Date) row.get(timestampField);
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
