package com.da.extractor.entity.training;

import lombok.*;

import java.util.List;

@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
public class AlgorithmConfig {

    private String name;

    private AlgorithmParameters parameters;
}
