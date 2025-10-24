package com.da.extractor.model;

import jakarta.validation.constraints.Null;
import lombok.*;

import java.util.Map;
import java.util.Optional;

@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
public class ElasticResponse {

    Map<String, Object> result;

    @Null
    @Getter(AccessLevel.NONE)
    String cursor;

    public Optional<String> getCursor() {
        return Optional.ofNullable(cursor);
    }
}
