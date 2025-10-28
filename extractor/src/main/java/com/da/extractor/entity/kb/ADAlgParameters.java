package com.da.extractor.entity.kb;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.Collection;
import java.util.List;
import java.util.Map;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class ADAlgParameters{
    private Map<String, List<DimensionMetadataMap>> kvpParams;

    public List<String> getObservedValues(){
        return kvpParams.values()
                .stream()
                .flatMap(Collection::stream)
                .map(DimensionMetadataMap::getDimension)
                .distinct()
                .toList();
    }
}
