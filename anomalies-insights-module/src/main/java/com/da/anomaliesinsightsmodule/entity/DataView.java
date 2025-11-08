package com.da.anomaliesinsightsmodule.entity;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class DataView {
    private String name;
    private String title;
    private String timeFieldName;
    private boolean allowNoIndex;
}
