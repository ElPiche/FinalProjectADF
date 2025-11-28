package com.da.extractor.entity.kb;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;

/**
 * Configuration for anomaly notifications.
 * Contains user emails to notify when anomalies are detected.
 */
@Getter
@Setter
@NoArgsConstructor
public class AnomalyConfig {
    
    @Field("user_emails")
    private List<String> userEmails;
}
