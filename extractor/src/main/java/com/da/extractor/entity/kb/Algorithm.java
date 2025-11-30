package com.da.extractor.entity.kb;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Collection;
import java.util.List;
import java.util.Map;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class Algorithm {

    // New unified schema uses "name" instead of "alg_name"
    private String name;

    // New unified schema uses "parameters" instead of "alg_parameters"
    private List<AlgorithmParameter> parameters;
}
