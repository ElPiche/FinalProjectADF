package com.da.anomaliesinsightsmodule.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.Map;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class DocumentDto {

    // Core fields (common to all algorithms)
    public String algorithm;
    public String metric;
    public String text;
    public String timestamp;
    public Double value;
    public String created_at;
    
    // KB identification
    public String kb_name;
    
    // Bucket context fields (common to all bucket-aware algorithms)
    public String bucket_key;
    public String bucket_profile_id;
    
    // Algorithm-specific data (flexible - each algorithm can put whatever it needs here)
    // Examples: z_score, threshold, mean, std, cluster_id, distance, etc.
    public Map<String, Object> algorithm_details;
}
