package com.da.extractor.pipeline;

import com.da.extractor.entity.serie.Metadata;
import com.da.extractor.entity.serie.SeriesElement;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class FilterService {

    /**
     * Safely converts any Number type (Integer, Long, Float, Double) to double.
     * Handles null values by returning 0.0.
     */
    private double toDouble(Object value) {
        if (value == null) {
            return 0.0;
        }
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        // Fallback: try parsing as string
        try {
            return Double.parseDouble(value.toString());
        } catch (NumberFormatException e) {
            return 0.0;
        }
    }

    public List<SeriesElement> applyFilter(List<Map<String, Object>> data, PipeMetadata metadata) {

        List<SeriesElement> seriesElements = new ArrayList<>();
        String timestampField = metadata.getTimestampField();

        for(Map<String, Object> row : data){
            for(String observedValue : metadata.getObservedValues()){
                if(row.containsKey(observedValue)){
                    double val = toDouble(row.get(observedValue));
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
