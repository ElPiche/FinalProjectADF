package com.da.extractor.service.pipeline;

import com.da.extractor.entity.serie.Metadata;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.entity.serie.SerieElement;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class FilterService {


    public List<SerieElement> applyFilter(List<Map<String, Object>> data, List<String> observedValues, Mode mode, String kbId) {

        List<SerieElement> series = new ArrayList<>();

        for(Map<String, Object> row : data){
            for(String observedValue : observedValues){
                if(row.containsKey(observedValue)){
                    Long val = row.get(observedValue) != null ? (Long) row.get(observedValue) : 0;
                    Date ts = (Date) row.get("es_timestamp");
                    series.add(new SerieElement(null, val, ts, new Metadata(kbId, observedValue, (short) mode.ordinal())));
                }
            }
        }

        IO.println("Filtered " + series.size() + " series for KB: " + kbId + " with mode: " + mode.ordinal());

        return series;
    }
}
