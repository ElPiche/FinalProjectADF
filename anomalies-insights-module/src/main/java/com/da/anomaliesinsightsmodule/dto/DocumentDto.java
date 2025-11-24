package com.da.anomaliesinsightsmodule.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class DocumentDto {

    public String algorithm;
    public String metric;
    public String text;
    public String timestamp;
    public Double value;
    public String created_at;
    //public Double ZScore;
    //public Double Std;
    //public String kbName;
}
