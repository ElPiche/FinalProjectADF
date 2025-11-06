package com.da.extractor.entity.logs.pipeline;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.boot.logging.LogLevel;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Date;

@Document("pipeline_flow_logs")
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
public class PipelineFlowLogEntry {

    @Id
    public String id;

    @Field("kb_id")
    public String kbId;

    @Field("log_level")
    public LogLevel logLevel;

    public String message;

    @Override
    public String toString() {
        return String.format("[KB ID: %s] - %s", kbId, message);
    }
}