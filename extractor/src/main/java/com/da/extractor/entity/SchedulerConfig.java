package com.da.extractor.entity;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Date;

@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
@Document("scheduler_configs")
public class SchedulerConfig {

    @Id
    private String id;

    @Field("kb_id")
    private String kbId;

    private int window;

    private String frequency;

    private String query;

    private Date from;

    @Field("last_run")
    private Date lastRun;
}
