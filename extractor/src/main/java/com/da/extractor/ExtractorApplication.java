package com.da.extractor;

import com.da.extractor.entity.serie.Mode;
import com.da.extractor.pipeline.*;
import com.da.extractor.service.SchedulerService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.scheduling.annotation.EnableScheduling;

import java.util.List;


//@Slf4j
@SpringBootApplication
@EnableScheduling
public class ExtractorApplication{

    public static void main(String[] args) throws Exception {
        ApplicationContext context = SpringApplication.run(ExtractorApplication.class, args);
    }
}
