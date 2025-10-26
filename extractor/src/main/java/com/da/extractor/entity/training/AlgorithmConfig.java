package com.da.extractor.entity.training;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
public class AlgorithmConfig {

    private String name;

    private AlgorithmParameters parameters;
}
