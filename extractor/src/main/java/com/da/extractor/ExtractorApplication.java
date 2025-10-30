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

        SchedulerService schedulerService = context.getBean(SchedulerService.class);


        System.out.println("Extractor Service Started...");


//        try {
//            schedulerService.createTask("Tarea de Extracción de Datos cada 5 segundos", 5000);
//            schedulerService.createTask("Tarea de Extracción de Datos cada 3 segundos", 3000);
//        } catch (Exception e) {
//            System.err.println("Error al correr el prgorama: " + e.getMessage());
//        }

        IO.println("Extractor Service Finished.");

    }
}
